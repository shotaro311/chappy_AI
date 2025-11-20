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

import websockets
from websockets import WebSocketClientProtocol

from src.audio.output_stream import AudioOutputStream
from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import AppConfig
from src.realtime.schema import ReminderToolCall
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
        connect: bool = True,
    ) -> None:
        self._config = config
        self._calendar = calendar_client
        self._vad = vad
        self._logger = get_logger(__name__)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for RealtimeSession")
        self._api_key = api_key
        self._ws: WebSocketClientProtocol | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._running = False
        self._connect = connect
        self._output = self._safe_build_output_stream(config)
        self._state = SessionState()

    async def __aenter__(self) -> "RealtimeSession":
        if self._connect:
            url = self._build_ws_url()
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                # Explicit beta header per API docs
                "OpenAI-Beta": "realtime=v1",
            }
            self._logger.info("Opening realtime session to %s", url)
            self._ws = await websockets.connect(url, extra_headers=headers)
            await self._send_session_update()
            self._recv_task = asyncio.create_task(self._recv_loop())
            if self._output:
                with contextlib.suppress(Exception):
                    self._output.open()
        else:
            self._logger.info("Realtime connection skipped (connect=False)")
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
        if self._ws:
            await self._ws.close()
            self._ws = None
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
        if self._vad.should_end_session():
            self._running = False
            raise SessionTimeoutError("No speech detected")

    async def _run_audio_loop(self, audio_source: AsyncIterable[bytes] | None) -> None:
        if not audio_source:
            await asyncio.sleep(0)
            return
        async for frame in audio_source:
            if not self._running:
                break
            self.ingest_audio_frame(frame)
            await self._append_audio(frame)
            # Yield control to avoid starving receiver
            await asyncio.sleep(0)

    def _process_tool_calls(self, tool_calls: Iterable[Mapping[str, object]] | None) -> None:
        if not tool_calls:
            return
        for payload in tool_calls:
            tool_call = ReminderToolCall.model_validate(payload)
            self._handle_reminder_call(tool_call)

    def _handle_reminder_call(self, tool_call: ReminderToolCall) -> None:
        args = tool_call.arguments
        event = self._calendar.upsert_event(
            title=args.title,
            start=args.scheduled_at,
            reminder_override=args.remind_before_minutes,
        )
        self._logger.info("Registered reminder '%s'", event.title)

    # ---------------- internal helpers ----------------

    def _build_ws_url(self) -> str:
        endpoint = self._config.realtime.endpoint.rstrip("/")
        # attach model as query param
        return f"{endpoint}?model={self._config.realtime.model}"

    def _safe_build_output_stream(self, config: AppConfig) -> AudioOutputStream | None:
        try:
            return AudioOutputStream(config)
        except Exception:
            # 音声出力デバイスが無い環境では黙って無効化
            return None

    async def _send_session_update(self) -> None:
        # server_vad で自動コミットさせ、入力/出力の PCM16 を明示
        payload = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": self._config.realtime.server_vad_idle_timeout_sec * 1000,
                },
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "modalities": ["text", "audio"],
                "instructions": "You are a concise Japanese assistant that manages calendar reminders.",
            },
        }
        await self._send_json(payload)

    async def _append_audio(self, frame: bytes) -> None:
        if not frame:
            return
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

    async def _handle_event(self, event: Mapping[str, object]) -> None:
        event_type = event.get("type", "")
        if event_type == "input_audio_buffer.committed":
            # サーバーが音声入力を1発話として確定 → 応答生成を明示
            await self._send_response_create()
            return
        if event_type in ("response.text.delta", "response.output_text.delta", "response.output_text.done"):
            delta = event.get("delta") or event.get("text")
            if delta:
                self._logger.info("AI: %s", delta)
            return
        if event_type in ("response.audio.delta", "response.output_audio.delta"):
            audio_base64 = event.get("audio")
            if audio_base64 and self._output:
                try:
                    self._output.play(base64.b64decode(audio_base64))
                except Exception:
                    # 再生失敗しても処理は継続
                    self._logger.debug("Audio playback skipped (device issue)")
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


__all__ = ["RealtimeSession"]
