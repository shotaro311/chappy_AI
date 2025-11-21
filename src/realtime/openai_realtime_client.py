"""ChatGPT Realtime session controller (websocket implementation)."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterable, Callable, Iterable, Mapping, Optional

import numpy as np
from websockets.asyncio.client import ClientConnection, connect

from src.audio.output_stream import AudioOutputStream
from src.gcal.google_calendar_client import GoogleCalendarClient
from src.config.loader import AppConfig
from src.realtime.schema import CalendarToolCall, ReminderArguments, DeleteEventArguments, ListEventsArguments
from src.util.logging_utils import get_logger
from src.vad.vad_detector import VADDetector


class SessionTimeoutError(RuntimeError):
    """Raised when the VAD decides the user stopped speaking."""


@dataclass
class SessionState:
    started_at: float = field(default_factory=time.monotonic)
    last_activity_at: float = field(default_factory=time.monotonic)


class RealtimeSession:
    def __init__(
        self,
        config: AppConfig,
        calendar_client: GoogleCalendarClient,
        vad: Optional[VADDetector] = None,
        *,
        start_connection: bool = True,
    ) -> None:
        self._config = config
        self._calendar = calendar_client
        self._vad = vad
        self._logger = get_logger(__name__)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for RealtimeSession")
        self._api_key = api_key
        self._ws: ClientConnection | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._running = False
        self._start_connection = start_connection
        self._output = self._safe_build_output_stream(config)
        # Realtime API は 24kHz 想定なので送信用にリサンプルする
        self._target_sample_rate = 24_000
        self._target_sample_rate = 24_000
        self._state = SessionState()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._audio_player_task: asyncio.Task[None] | None = None
        self._speech_started_at: float | None = None
        self._force_commit_after_sec = 2.0
        self._last_audio_activity: float | None = None
        self._silence_timeout_sec = config.realtime.silence_timeout_sec
        self._silence_monitor_task: asyncio.Task[None] | None = None
        self._ai_is_responding: bool = False  # Track if AI is currently responding
        self._is_playing: bool = False  # Track if audio is currently being played

    async def __aenter__(self) -> "RealtimeSession":
        if self._start_connection:
            url = self._build_ws_url()
            headers = [
                ("Authorization", f"Bearer {self._api_key}"),
                # Explicit beta header per API docs
                ("OpenAI-Beta", "realtime=v1"),
            ]
            self._logger.info("Opening realtime session to %s", url)
            self._ws = await connect(url, additional_headers=headers)
            await self._send_session_update()
            self._recv_task = asyncio.create_task(self._recv_loop())
            self._silence_monitor_task = asyncio.create_task(self._silence_monitor_loop())
            if self._output:
                try:
                    self._output.open()
                    self._logger.info("AudioOutputStream opened successfully")
                except Exception as e:
                    self._logger.error("Failed to open AudioOutputStream: %s", e, exc_info=True)
                    # If output stream fails to open, disable audio output
                    self._output = None
                if self._output:
                    self._audio_player_task = asyncio.create_task(self._player_loop())
        else:
            self._logger.info("Realtime connection skipped (start_connection=False)")
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None
        if self._silence_monitor_task:
            self._silence_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._silence_monitor_task
            self._silence_monitor_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._audio_player_task:
            self._audio_player_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._audio_player_task
            self._audio_player_task = None
        if self._output:
            self._output.close()
        if self._running:
            self._logger.info("Closing realtime session")
            self._running = False

    async def stream_text(self, text: str) -> None:
        self._logger.debug("Streaming text: %s", text)
        await self._send_json(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        await self._send_json(
            {
                "type": "response.create",
                "response": {"modalities": ["text"], "instructions": "Respond conversationally."},
            }
        )

    async def register_reminder(self, title: str, iso_datetime: str) -> None:
        from datetime import datetime

        start = datetime.fromisoformat(iso_datetime)
        self._calendar.upsert_event(title=title, start=start)
        self._logger.info("Registered reminder '%s'", title)

    async def run(
        self,
        *,
        audio_source: AsyncIterable[bytes] | None = None,
        tool_calls: Iterable[Mapping[str, object]] | None = None,
        on_message: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._logger.info("Realtime loop started")
        try:
            self._process_tool_calls(tool_calls)
            await self._run_audio_loop(audio_source)
            if on_message:
                on_message("session-idle")
        except SessionTimeoutError as exc:
            self._logger.info("Session stopped: %s", exc)
        finally:
            self._logger.info("Realtime loop finished")

    def ingest_audio_frame(self, frame: bytes) -> None:
        if not self._vad:
            return
        self._vad.update(frame, self._config.audio.sample_rate)
        self._state.last_activity_at = time.monotonic()
        # Local VAD timeout check is disabled because it doesn't account for AI response time.
        # We rely on _silence_monitor_loop instead.
        # if self._vad.should_end_session():
        #     self._running = False
        #     raise SessionTimeoutError("No speech detected")

    async def _run_audio_loop(self, audio_source: AsyncIterable[bytes] | None) -> None:
        if not audio_source:
            await asyncio.sleep(0)
            return
        
        async for frame in audio_source:
            if not self._running:
                break
            self.ingest_audio_frame(frame)
            await self._append_audio(frame)
            
            # Force commit if speech is too long (handling noisy environments)
            if self._speech_started_at:
                elapsed = time.monotonic() - self._speech_started_at
                if elapsed > self._force_commit_after_sec:
                    self._logger.info("Force committing audio after %.1fs", elapsed)
                    await self._send_json({"type": "input_audio_buffer.commit"})
                    self._speech_started_at = None

            # Yield control to avoid starving receiver
            await asyncio.sleep(0)

    def _process_tool_calls(self, tool_calls: Iterable[Mapping[str, object]] | None) -> None:
        if not tool_calls:
            return
        for payload in tool_calls:
            tool_call = CalendarToolCall.model_validate(payload)
            if tool_call.name == "schedule_reminder":
                self._handle_reminder_call(tool_call.arguments)
            elif tool_call.name == "delete_calendar_event":
                self._handle_delete_call(tool_call.arguments)
            elif tool_call.name == "list_calendar_events":
                self._handle_list_call(tool_call.arguments)

    def _handle_reminder_call(self, args: ReminderArguments) -> None:
        event = self._calendar.upsert_event(
            title=args.title,
            start=args.scheduled_at,
            reminder_override=args.remind_before_minutes,
        )
        self._logger.info("Registered reminder '%s'", event.title)
        asyncio.create_task(self.stream_text(f"予定「{event.title}」を登録しました。"))

    def _handle_delete_call(self, args: DeleteEventArguments) -> None:
        event = self._calendar.find_event_by_title(args.title)
        if event:
            self._calendar.delete_event(event.event_id)
            self._logger.info("Deleted event '%s'", event.title)
            asyncio.create_task(self.stream_text(f"予定「{event.title}」を削除しました。"))
        else:
            self._logger.info("Event '%s' not found for deletion", args.title)
            asyncio.create_task(self.stream_text(f"予定「{args.title}」が見つかりませんでした。"))

    def _handle_list_call(self, args: ListEventsArguments) -> None:
        from datetime import datetime, timedelta, timezone
        
        if args.date:
            try:
                start_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_date = start_date + timedelta(days=1)
                events = self._calendar.list_events(start_date, end_date)
                date_str = args.date
            except ValueError:
                asyncio.create_task(self.stream_text("日付の形式が正しくありません。"))
                return
        else:
            events = self._calendar.list_upcoming()
            date_str = "今後"

        if not events:
            msg = f"{date_str}の予定はありません。"
        else:
            lines = [f"{e.start.strftime('%H:%M')} {e.title}" for e in events]
            msg = f"{date_str}の予定は{len(events)}件あります。\n" + "\n".join(lines)
        
        asyncio.create_task(self.stream_text(msg))

    # ---------------- internal helpers ----------------

    def _build_ws_url(self) -> str:
        endpoint = self._config.realtime.endpoint.rstrip("/")
        # attach model as query param
        return f"{endpoint}?model={self._config.realtime.model}"

    def _safe_build_output_stream(self, config: AppConfig) -> AudioOutputStream | None:
        try:
            # Realtime API uses 24kHz audio, so use 24kHz for output
            return AudioOutputStream(config, output_sample_rate=24_000)
        except Exception as e:
            self._logger.warning("Failed to initialize AudioOutputStream: %s", e)
            # 音声出力デバイスが無い環境では黙って無効化
            return None

    async def _send_session_update(self) -> None:
        # server_vad で自動コミットさせ、入力/出力の PCM16 を明示
        payload = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.6,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": int(self._config.realtime.server_vad_idle_timeout_sec * 1000),
                },
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "modalities": ["text", "audio"],
                "instructions": "You are a concise Japanese assistant that manages calendar reminders.",
                "tools": [
                    {
                        "type": "function",
                        "name": "schedule_reminder",
                        "description": "Schedule a calendar reminder.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "datetime": {"type": "string", "description": "ISO 8601 datetime"},
                                "remind_before_minutes": {"type": "integer"},
                            },
                            "required": ["title", "datetime"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "delete_calendar_event",
                        "description": "Delete a calendar event by title.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Title of the event to delete"},
                            },
                            "required": ["title"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "list_calendar_events",
                        "description": "List calendar events for a specific date or range.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "YYYY-MM-DD date to list events for. If omitted, lists upcoming events."},
                            },
                        },
                    },
                ],
            },
        }
        await self._send_json(payload)

    async def _append_audio(self, frame: bytes) -> None:
        if not frame:
            return
        frame = self._resample_if_needed(frame)
        await self._send_json(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(frame).decode("ascii"),
            }
        )

    async def _send_response_create(self) -> None:
        # テキストと音声両方を要求
        await self._send_json(
            {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Respond briefly in Japanese and keep calendar context.",
                },
            }
        )

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    event = json.loads(raw)
                except Exception:
                    self._logger.debug("Non-JSON frame: %s", raw)
                    continue
                await self._handle_event(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Realtime receive loop failed")
            self._running = False

    async def _silence_monitor_loop(self) -> None:
        """Monitor silence and auto-close session after timeout."""
        self._logger.info("Silence monitor loop started")
        try:
            while self._running:
                await asyncio.sleep(1)  # Check every second
                
                # Check if we should timeout
                # We only timeout if:
                # 1. AI is NOT generating a response
                # 2. We are NOT playing back audio
                # 3. Silence duration has exceeded the limit
                if (
                    self._last_audio_activity is not None
                    and not self._ai_is_responding
                    and not self._is_playing
                    and self._audio_queue.empty()
                ):
                    silence_duration = time.monotonic() - self._last_audio_activity
                    if silence_duration > self._silence_timeout_sec:
                        self._logger.info("Session auto-closing after %.1fs of silence", silence_duration)
                        self._running = False
                        break
        except asyncio.CancelledError:
            self._logger.info("Silence monitor loop cancelled")
        except Exception:
            self._logger.exception("Silence monitor loop failed")
        finally:
            self._logger.info("Silence monitor loop finished")

    async def _handle_event(self, event: Mapping[str, object]) -> None:
        event_type = event.get("type", "")
        if event_type == "input_audio_buffer.speech_started":
            self._logger.info("Event: speech_started (Interruption detected)")
            self._speech_started_at = time.monotonic()
            self._last_audio_activity = time.monotonic()
            
            # Interruption handling:
            # 1. Clear local audio queue to stop playback immediately
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.task_done()
                except asyncio.QueueEmpty:
                    break
            
            # 2. Send cancel to server to stop generation
            if self._ai_is_responding:
                self._logger.info("Cancelling AI response due to interruption")
                await self._send_json({"type": "response.cancel"})
            
            return
        if event_type == "input_audio_buffer.speech_stopped":
            self._logger.debug("Event: speech_stopped")
            self._speech_started_at = None
            self._last_audio_activity = time.monotonic()  # Start silence timer
            return
        if event_type == "input_audio_buffer.committed":
            self._logger.info("Event: input_audio_buffer.committed (ID: %s)", event.get("item_id"))
            self._speech_started_at = None
            self._last_audio_activity = time.monotonic()  # Reset on commit
            # サーバーが音声入力を1発話として確定 → 応答生成を明示
            await self._send_response_create()
            return
        if event_type == "response.created":
            self._logger.info("Event: response.created (ID: %s)", event.get("response", {}).get("id"))
            self._ai_is_responding = True
            return
        if event_type == "response.done":
            self._logger.info("Event: response.done")
            self._ai_is_responding = False
            self._last_audio_activity = time.monotonic()  # Reset silence timer after AI finishes
            return
        if event_type in ("response.text.delta", "response.output_text.delta", "response.output_text.done"):
            delta = event.get("delta") or event.get("text")
            if delta:
                self._logger.info("AI: %s", delta)
            return
        # Audio transcript events (for text display of audio responses)
        if event_type == "response.audio_transcript.delta":
            delta = event.get("delta")
            if delta:
                self._logger.info("AI: %s", delta)
            return
        if event_type == "response.audio_transcript.done":
            transcript = event.get("transcript")
            if transcript:
                self._logger.info("AI (full): %s", transcript)
            return
        if event_type in ("response.audio.delta", "response.output_audio.delta"):
            # Log raw event to see actual structure
            self._logger.debug("RAW AUDIO EVENT: %s", dict(event))
            audio_base64 = event.get("audio") or event.get("delta")
            self._logger.debug("Received audio delta event, has_audio=%s, has_output=%s", bool(audio_base64), bool(self._output))
            if audio_base64 and self._output:
                try:
                    # Queue audio for playback to avoid blocking the websocket loop
                    audio_bytes = base64.b64decode(audio_base64)
                    self._audio_queue.put_nowait(audio_bytes)
                    self._logger.debug("Queued %d bytes of audio (queue size now: %d)", len(audio_bytes), self._audio_queue.qsize())
                except Exception as exc:
                    self._logger.warning("Failed to queue audio: %s", exc)
            return
        if event_type == "error":
            self._logger.error("Realtime error: %s", event)
        else:
            # Noise-level debug for unfamiliar events
            self._logger.debug("Event: %s", event_type)

    async def _send_json(self, payload: Mapping[str, object]) -> None:
        if not self._ws:
            return
        async with self._send_lock:
            await self._ws.send(json.dumps(payload))

    def _resample_if_needed(self, frame: bytes) -> bytes:
        """Resample PCM16 mono to 24kHz if input is at a lower rate (e.g., 16k)."""
        src_rate = self._config.audio.sample_rate
        dst_rate = self._target_sample_rate
        if src_rate == dst_rate:
            return frame
        data = np.frombuffer(frame, dtype=np.int16)
        ratio = dst_rate / src_rate
        dst_len = int(len(data) * ratio)
        if dst_len <= 0:
            return frame
        x = np.arange(len(data))
        x_new = np.linspace(0, len(data) - 1, dst_len)
        resampled = np.interp(x_new, x, data).astype(np.int16)
        return resampled.tobytes()

    async def _player_loop(self) -> None:
        """Background task to play queued audio chunks."""
        if not self._output:
            return
        self._logger.info("Audio player loop started")
        try:
            while True:
                self._logger.debug("Waiting for audio chunk from queue (size=%d)", self._audio_queue.qsize())
                chunk = await self._audio_queue.get()
                self._logger.debug("Got audio chunk of %d bytes, playing...", len(chunk))
                try:
                    self._is_playing = True
                    # Run blocking play in a thread to avoid blocking the event loop
                    await asyncio.to_thread(self._output.play, chunk)
                    self._logger.debug("Audio chunk played successfully")
                    # Update activity time after playback to reset silence timer
                    self._last_audio_activity = time.monotonic()
                except Exception as exc:
                    self._logger.warning("Audio playback failed: %s", exc)
                finally:
                    self._is_playing = False
                    self._audio_queue.task_done()
        except asyncio.CancelledError:
            self._logger.info("Audio player loop cancelled")
        except Exception:
            self._logger.exception("Audio player loop failed")
        finally:
            self._logger.info("Audio player loop finished")


__all__ = ["RealtimeSession"]
