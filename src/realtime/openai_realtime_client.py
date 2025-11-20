"""ChatGPT Realtime session controller (scaffolding)."""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterable, Callable, Iterable, Mapping, Optional

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
    ) -> None:
        self._config = config
        self._calendar = calendar_client
        self._vad = vad
        self._logger = get_logger(__name__)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for RealtimeSession")
        self._api_key = api_key
        self._running = False
        self._state = SessionState()

    async def __aenter__(self) -> "RealtimeSession":
        self._logger.info("Opening realtime session to %s", self._config.realtime.endpoint)
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._running:
            self._logger.info("Closing realtime session")
            self._running = False

    async def stream_text(self, text: str) -> None:
        self._logger.debug("Streaming text: %s", text)
        await asyncio.sleep(0)

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
            start=args.datetime,
            reminder_override=args.remind_before_minutes,
        )
        self._logger.info("Registered reminder '%s'", event.title)


__all__ = ["RealtimeSession"]
