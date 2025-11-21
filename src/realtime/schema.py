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


class DeleteEventArguments(BaseModel):
    """Function-call arguments for deleting calendar events."""

    title: str = Field(description="Title of the event to delete. If multiple events match, the first one will be deleted.")


class ListEventsArguments(BaseModel):
    """Function-call arguments for listing calendar events."""

    date: str | None = Field(default=None, description="Date to list events for (YYYY-MM-DD). If not provided, lists upcoming events.")


class CalendarToolCall(BaseModel):
    """Wrapper describing a Realtime tool call payload."""

    name: Literal["create_calendar_event", "schedule_reminder", "delete_calendar_event", "list_calendar_events"]
    arguments: ReminderArguments | DeleteEventArguments | ListEventsArguments


__all__ = ["ReminderArguments", "DeleteEventArguments", "ListEventsArguments", "CalendarToolCall"]
