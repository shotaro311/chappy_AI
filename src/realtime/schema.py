"""Pydantic models describing Realtime tool-call payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReminderArguments(BaseModel):
    """Function-call arguments for calendar reminders."""

    title: str
    scheduled_at: datetime = Field(alias="datetime")
    remind_before_minutes: int | None = None


class ReminderToolCall(BaseModel):
    """Wrapper describing a Realtime tool call payload."""

    name: Literal["create_calendar_event", "schedule_reminder"]
    arguments: ReminderArguments


__all__ = ["ReminderArguments", "ReminderToolCall"]
