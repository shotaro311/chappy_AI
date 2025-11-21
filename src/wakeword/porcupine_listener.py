"""Porcupine-based wake-word loop."""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable, Sequence

import numpy as np

import pvporcupine

from src.audio.input_stream import AudioInputStream
from src.config.loader import AppConfig

logger = logging.getLogger(__name__)


class WakeWordListener:
    def __init__(
        self,
        config: AppConfig,
        audio_stream: AudioInputStream,
        keyword_paths: Sequence[str] | None = None,
        keywords: Sequence[str] | None = None,
        model_path: str | None = None,
    ) -> None:
        access_key = os.getenv("PORCUPINE_ACCESS_KEY")
        if not access_key:
            raise RuntimeError("PORCUPINE_ACCESS_KEY is required")
        self._audio_stream = audio_stream
        if not keyword_paths and not keywords:
            keywords = ["porcupine"]

        # 使う .ppn と model の言語が一致しない場合は初期化で落ちるため、先に簡易チェック。
        if keyword_paths and not model_path:
            joined = " ".join(keyword_paths)
            if "_ja_" in joined:
                raise RuntimeError(
                    "Japanese .ppn を使うには日本語モデル porcupine_params_ja.pv が必要です。"
                    " assets/models/ に配置するか PORCUPINE_MODEL_PATH で指定してください。"
                )

        # 感度設定（0.7）
        num_keywords = len(keyword_paths or keywords or [])
        sensitivities = [0.7] * num_keywords

        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=list(keyword_paths or []),
            keywords=list(keywords or []),
            model_path=model_path,
            sensitivities=sensitivities,
        )
        self._frame_length = self._porcupine.frame_length
        self._wake_event = threading.Event()

        logger.info(f"Porcupine initialized with sensitivity={sensitivities}")

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
            logger.info(f"Wake word detected! keyword_index={keyword_index}")
            self._wake_event.set()

    def close(self) -> None:
        self._porcupine.delete()


__all__ = ["WakeWordListener"]
