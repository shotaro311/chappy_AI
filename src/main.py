"""Entry point for the wake-word powered voice assistant."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import AppConfig, load_config
from src.realtime.openai_realtime_client import RealtimeSession
from src.util.logging_utils import configure_logging, get_logger
from src.vad.vad_detector import VADDetector


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pc.dev.yaml", help="Path to env config yaml")
    parser.add_argument("--dry-run", action="store_true", help="Skip realtime connection")
    return parser.parse_args()


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    config_path = Path(args.config)
    env_name = config_path.stem
    return load_config(app_env=env_name, config_dir=config_path.parent)


async def _run(config: AppConfig, dry_run: bool) -> None:
    logger = get_logger(__name__)
    calendar_client = GoogleCalendarClient(config)
    vad = None
    if not dry_run:
        try:
            vad = VADDetector(config)
        except RuntimeError as exc:
            logger.warning("VAD disabled: %s", exc)
    if dry_run:
        logger.info("Dry run complete. Loaded config for mode %s", config.mode)
        return
    async with RealtimeSession(config, calendar_client, vad) as session:
        await session.run()


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
