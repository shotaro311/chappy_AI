"""Session manager wires wake-word, audio I/O, and realtime session."""
from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator, Callable, Optional

from src.audio.input_stream import AudioInputStream
from src.realtime.openai_realtime_client import RealtimeSession
from src.util.reminder_scheduler import ReminderScheduler
from src.util.logging_utils import get_logger


class SessionManager:
    def __init__(
        self,
        audio_input: AudioInputStream,
        realtime: RealtimeSession,
        scheduler: Optional[ReminderScheduler] = None,
    ) -> None:
        self._audio = audio_input
        self._realtime = realtime
        self._scheduler = scheduler
        self._active = False

    async def run(self) -> None:
        self._active = True
        notification_task = None
        if self._scheduler:
            notification_task = asyncio.create_task(self._notification_loop())

        try:
            await self._realtime.run(audio_source=self._audio_frames())
        finally:
            if notification_task:
                notification_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await notification_task
            self._active = False
            self._audio.close()

    async def _audio_frames(self) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _on_frame(frame: bytes) -> None:
            queue.put_nowait(frame)

        self._audio.open(_on_frame)
        # Give time for audio stream to initialize
        await asyncio.sleep(0.1)
        try:
            while self._active:
                frame = await queue.get()
                yield frame
        finally:
            self._audio.close()

    async def _notification_loop(self) -> None:
        logger = get_logger(__name__)
        logger.info("Notification loop started")
        while self._active:
            try:
                # Check every 30 seconds
                await asyncio.sleep(30)
                if not self._scheduler:
                    continue
                
                events = self._scheduler.collect()
                for event in events:
                    msg = f"リマインダー: {event.title}の時間です。"
                    logger.info("Triggering notification: %s", msg)
                    await self._realtime.stream_text(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Notification loop error")
