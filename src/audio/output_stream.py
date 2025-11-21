"""Speaker output abstraction."""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.config.loader import AppConfig

try:  # pragma: no cover - optional dependency
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None  # type: ignore


class AudioOutputStream:
    def __init__(self, config: AppConfig, output_sample_rate: int | None = None) -> None:
        if sd is None:  # pragma: no cover - runtime guard
            raise RuntimeError("sounddevice is required for AudioOutputStream")
        self._config = config
        # Allow overriding output sample rate (e.g., for 24kHz Realtime API audio)
        self._output_sample_rate = output_sample_rate or config.audio.sample_rate
        self._stream: Optional[sd.OutputStream] = None  # type: ignore[attr-defined]

    def open(self) -> None:
        print(f"[AudioOutputStream] Opening stream: rate={self._output_sample_rate}, device={self._config.audio.output_device}")
        self._stream = sd.OutputStream(  # type: ignore[attr-defined]
            channels=self._config.audio.channels,
            samplerate=self._output_sample_rate,
            dtype=np.int16,
            device=self._config.audio.output_device,
        )
        self._stream.start()
        print("[AudioOutputStream] Stream started")

    def play(self, pcm: bytes) -> None:
        if not self._stream:
            raise RuntimeError("AudioOutputStream is not open")
        array = np.frombuffer(pcm, dtype=np.int16)
        print(f"[AudioOutputStream] Playing {len(array)} samples")
        self._stream.write(array)

    def close(self) -> None:
        if self._stream:
            print("[AudioOutputStream] Closing stream")
            self._stream.stop()
            self._stream.close()
            self._stream = None


__all__ = ["AudioOutputStream"]
