"""Configuration loader that merges base + environment specific YAML files."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


class AudioConfig(BaseModel):
    sample_rate: int = 16_000
    channels: int = 1
    input_device: str | None = None
    output_device: str | None = None


class TimeoutConfig(BaseModel):
    utterance_timeout_sec: int = Field(ge=1, default=5)
    session_timeout_sec: int = Field(ge=1, default=10)


class RealtimeConfig(BaseModel):
    model: str = "gpt-realtime"
    endpoint: str
    max_session_minutes: int = 60
    refresh_threshold_minutes: int = 30
    server_vad_idle_timeout_sec: int = 10


class CalendarConfig(BaseModel):
    reminder_minutes_default: int = 10
    notification_method: str = "push"
    polling_interval_fallback_min: int = 5


class LoggingConfig(BaseModel):
    level: str = "INFO"


class AppConfig(BaseModel):
    audio: AudioConfig
    timeouts: TimeoutConfig
    realtime: RealtimeConfig
    calendar: CalendarConfig
    logging: LoggingConfig | None = None
    mode: str = "dev"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def load_config(app_env: str | None = None, *, config_dir: Path | None = None) -> AppConfig:
    """Load configuration for the provided environment (defaults to APP_ENV)."""

    load_dotenv()
    config_path = config_dir or DEFAULT_CONFIG_DIR
    env_name = app_env or os.getenv("APP_ENV", "pc.dev")

    base_config = _load_yaml(config_path / "base.yaml")
    env_file = config_path / f"{env_name}.yaml"
    env_config: Dict[str, Any] = {}
    if env_file.exists():
        env_config = _load_yaml(env_file)

    merged = _deep_merge(base_config, env_config)
    merged.setdefault("mode", env_name)

    return AppConfig.model_validate(merged)


__all__ = [
    "AudioConfig",
    "TimeoutConfig",
    "RealtimeConfig",
    "CalendarConfig",
    "LoggingConfig",
    "AppConfig",
    "load_config",
]
