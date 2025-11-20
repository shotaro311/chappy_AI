"""Centralized logger factory."""
from __future__ import annotations

import logging
from typing import Final

_LOG_FORMAT: Final = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    if logging.getLogger().handlers:
        logging.getLogger().setLevel(level)
        return
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]
