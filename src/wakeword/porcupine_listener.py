"""Porcupine-based wake-word loop."""
from __future__ import annotations

import os
import threading
from typing import Iterable, Sequence

import numpy as np

import pvporcupine

from src.audio.input_stream import AudioInputStream
from src.config.loader import AppConfig


class WakeWordListener:
    def __init__(
        self,
        config: AppConfig,
        audio_stream: AudioInputStream,
        keyword_paths: Sequence[str] | None = None,
    ) -> None:
        access_key = os.getenv("PORCUPINE_ACCESS_KEY")
        if not access_key:
            raise RuntimeError("PORCUPINE_ACCESS_KEY is required")
        self._audio_stream = audio_stream
        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=list(keyword_paths or []),
        )
        self._frame_length = self._porcupine.frame_length
        self._wake_event = threading.Event()

    def wait_for_wake_word(self) -> None:
        self._wake_event.clear()
        self._audio_stream.open(
            self._process_frame,
            frame_samples=self._frame_length,
        )
        self._wake_event.wait()
        self._audio_stream.close()

    def _process_frame(self, pcm: bytes) -> None:
        frame = np.frombuffer(pcm, dtype=np.int16)
        keyword_index = self._porcupine.process(frame)
        if keyword_index >= 0:
            self._wake_event.set()

    def close(self) -> None:
        self._porcupine.delete()


__all__ = ["WakeWordListener"]
