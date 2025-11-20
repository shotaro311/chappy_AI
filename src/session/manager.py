"""Session manager wires wake-word, audio I/O, and realtime session."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable, Optional

from src.audio.input_stream import AudioInputStream
from src.realtime.openai_realtime_client import RealtimeSession


class SessionManager:
    def __init__(self, audio_input: AudioInputStream, realtime: RealtimeSession) -> None:
        self._audio = audio_input
        self._realtime = realtime

    async def run(self) -> None:
        await self._realtime.run(audio_source=self._audio_frames())

    async def _audio_frames(self) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _on_frame(frame: bytes) -> None:
            queue.put_nowait(frame)

        self._audio.open(_on_frame)
        try:
            while True:
                frame = await queue.get()
                yield frame
        finally:
            self._audio.close()
