"""Entry point for the wake-word powered voice assistant."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from src.audio.input_stream import AudioInputStream
from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import AppConfig, load_config
from src.realtime.openai_realtime_client import RealtimeSession
from src.session.manager import SessionManager
from src.util.logging_utils import configure_logging, get_logger
from src.vad.vad_detector import VADDetector
from src.wakeword.porcupine_listener import WakeWordListener


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pc.dev.yaml", help="Path to env config yaml")
    parser.add_argument("--dry-run", action="store_true", help="Skip realtime connection")
    return parser.parse_args()


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    config_path = Path(args.config)
    env_name = config_path.stem
    return load_config(app_env=env_name, config_dir=config_path.parent)


def _discover_keyword_paths() -> list[str]:
    model_dir = Path(__file__).resolve().parent.parent / "assets" / "models"
    return [str(path) for path in model_dir.glob("*.ppn")]


def _build_audio_input(config: AppConfig) -> AudioInputStream | None:
    logger = get_logger(__name__)
    try:
        return AudioInputStream(config)
    except RuntimeError as exc:
        logger.error("Audio input unavailable: %s", exc)
        return None


def _build_vad(config: AppConfig) -> VADDetector | None:
    logger = get_logger(__name__)
    try:
        return VADDetector(config)
    except RuntimeError as exc:
        logger.warning("VAD disabled: %s", exc)
        return None


def _build_wake_listener(config: AppConfig, audio_input: AudioInputStream) -> WakeWordListener | None:
    logger = get_logger(__name__)
    keyword_paths = _discover_keyword_paths()
    keywords_env = os.getenv("PORCUPINE_KEYWORDS")
    keywords: list[str] = []
    if keywords_env:
        keywords = [kw.strip() for kw in keywords_env.split(",") if kw.strip()]
    if not keyword_paths and not keywords:
        keywords = ["porcupine"]  # free built-in keyword
        logger.info("Using built-in Porcupine keyword: %s", keywords[0])
    elif keyword_paths:
        logger.info("Using Porcupine keyword files: %s", keyword_paths)
    else:
        logger.info("Using Porcupine built-in keywords: %s", ", ".join(keywords))

    model_path = os.getenv("PORCUPINE_MODEL_PATH")
    if not model_path and keyword_paths:
        first = Path(keyword_paths[0]).name
        if "_ja_" in first:
            candidate = Path(__file__).resolve().parent.parent / "assets" / "models" / "porcupine_params_ja.pv"
            if candidate.exists():
                model_path = str(candidate)
                logger.info("Detected JA keyword. Using model file: %s", model_path)
            else:
                logger.error("Japanase keyword detected but porcupine_params_ja.pv not found. Please download and place it under assets/models or set PORCUPINE_MODEL_PATH.")

    try:
        return WakeWordListener(
            config,
            audio_input,
            keyword_paths=keyword_paths,
            keywords=keywords,
            model_path=model_path,
        )
    except RuntimeError as exc:
        logger.warning("Wake word disabled: %s", exc)
        return None


async def _run(config: AppConfig, dry_run: bool) -> None:
    logger = get_logger(__name__)
    calendar_client = GoogleCalendarClient(config)
    if dry_run:
        logger.info("Dry run complete. Loaded config for mode %s", config.mode)
        return
    audio_input = _build_audio_input(config)
    if not audio_input:
        return

    wake_listener = _build_wake_listener(config, audio_input)

    try:
        while True:
            if wake_listener:
                logger.info("Waiting for wake word ...")
                await asyncio.to_thread(wake_listener.wait_for_wake_word)
                logger.info("Wake word detected. Starting realtime session")
            else:
                logger.info("Wake word disabled. Starting realtime session immediately")

            vad = _build_vad(config)

            try:
                async with RealtimeSession(config, calendar_client, vad) as session:
                    manager = SessionManager(audio_input, session)
                    await manager.run()
            except Exception:
                logger.exception("Realtime session failed")
            finally:
                logger.info("Session finished. Returning to wake loop")
    finally:
        if wake_listener:
            wake_listener.close()
        audio_input.close()


def main() -> None:
    args = _parse_args()
    config = _resolve_config(args)
    log_level = config.logging.level if config.logging else "INFO"
    configure_logging(log_level)
    api_key = os.getenv("OPENAI_API_KEY")
    dry_run = args.dry_run or not api_key
    if not api_key:
        get_logger(__name__).warning("OPENAI_API_KEY not set. Falling back to --dry-run mode")
    asyncio.run(_run(config, dry_run))


if __name__ == "__main__":
    main()
