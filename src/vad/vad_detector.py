"""Simple wrapper around webrtcvad to compute idle timeouts."""
from __future__ import annotations

import time
from dataclasses import dataclass

from src.config.loader import AppConfig

try:  # pragma: no cover - optional dependency
    import webrtcvad
except Exception:  # pragma: no cover
    webrtcvad = None  # type: ignore


@dataclass
class VADState:
    last_speech_time: float


class VADDetector:
    def __init__(self, config: AppConfig, aggressiveness: int = 2) -> None:
        if webrtcvad is None:  # pragma: no cover - runtime guard
            raise RuntimeError("webrtcvad is required for VADDetector")
        self._config = config
        self._vad = webrtcvad.Vad(aggressiveness)
        self.state = VADState(last_speech_time=time.monotonic())

    def update(self, frame: bytes, sample_rate: int) -> None:
        is_speech = self._vad.is_speech(frame, sample_rate)
        if is_speech:
            self.state.last_speech_time = time.monotonic()

    def should_end_session(self) -> bool:
        now = time.monotonic()
        idle = now - self.state.last_speech_time
        return idle > self._config.timeouts.session_timeout_sec


__all__ = ["VADDetector", "VADState"]
