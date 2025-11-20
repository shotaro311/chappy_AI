"""Placeholder ChatGPT Realtime session controller."""
from __future__ import annotations

import asyncio
import os
from typing import Callable, Optional

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import AppConfig
from src.util.logging_utils import get_logger
from src.vad.vad_detector import VADDetector


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

    async def run(self, on_message: Optional[Callable[[str], None]] = None) -> None:
        self._logger.info("Realtime loop started (placeholder)")
        for _ in range(3):
            await asyncio.sleep(0)
            if on_message:
                on_message("placeholder-response")
        self._logger.info("Realtime loop finished")


__all__ = ["RealtimeSession"]
