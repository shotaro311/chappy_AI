"""Microphone input abstraction."""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from src.config.loader import AppConfig
from src.util.logging_utils import get_logger

try:  # pragma: no cover - optional dependency
    import sounddevice as sd
except Exception:  # pragma: no cover - gracefully fail during tests
    sd = None  # type: ignore


class AudioInputStream:
    def __init__(self, config: AppConfig, frame_duration_ms: int = 30) -> None:
        if sd is None:  # pragma: no cover - runtime guard
            raise RuntimeError("sounddevice is required for AudioInputStream")
        self._config = config
        self._logger = get_logger(__name__)
        self._default_frame_samples = int(config.audio.sample_rate * frame_duration_ms / 1000)
        self._active_frame_samples = self._default_frame_samples
        self._stream: Optional[sd.InputStream] = None  # type: ignore[attr-defined]
        self._callback: Optional[Callable[[bytes], None]] = None

    def open(self, callback: Callable[[bytes], None], *, frame_samples: Optional[int] = None) -> None:
        self._callback = callback
        blocksize = frame_samples or self._default_frame_samples
        self._active_frame_samples = blocksize
        self._logger.info(
            "Opening mic stream: rate=%sHz, channels=%s, block=%s, device=%s",
            self._config.audio.sample_rate,
            self._config.audio.channels,
            self._active_frame_samples,
            self._config.audio.input_device or "default",
        )

        def _sd_callback(indata, frames, time, status):  # pragma: no cover - hardware callback
            if status:
                self._logger.warning("sounddevice status: %s", status)
                return
            if self._callback:
                self._callback(indata.copy().tobytes())
            else:
                self._logger.warning("Mic callback called but no callback set")

        self._stream = sd.InputStream(  # type: ignore[attr-defined]
            channels=self._config.audio.channels,
            samplerate=self._config.audio.sample_rate,
            blocksize=self._active_frame_samples,
            callback=_sd_callback,
            dtype=np.int16,
            device=self._config.audio.input_device,
        )
        self._stream.start()

    def close(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


__all__ = ["AudioInputStream"]
