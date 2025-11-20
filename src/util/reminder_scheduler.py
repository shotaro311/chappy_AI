"""Utility to detect upcoming reminders based on calendar events."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator, List

from src.calendar.google_calendar_client import CalendarEvent, GoogleCalendarClient
from src.util.logging_utils import get_logger


class ReminderScheduler:
    """Builds a queue of events that should trigger reminders."""

    def __init__(
        self,
        calendar_client: GoogleCalendarClient,
        *,
        lookahead_minutes: int = 15,
    ) -> None:
        self._calendar = calendar_client
        self._lookahead = lookahead_minutes
        self._logger = get_logger(__name__)

    def iter_due_events(self, reference: datetime | None = None) -> Iterator[CalendarEvent]:
        """Yield events whose reminder window has started."""

        ref = reference or datetime.now(timezone.utc)
        for event in self._calendar.list_upcoming(reference_time=ref):
            start = _ensure_timezone(event.start)
            reminder_delta = timedelta(minutes=event.reminder_minutes)
            reminder_start = start - reminder_delta
            if reminder_start <= ref <= start and self._is_within_lookahead(ref, reminder_start):
                yield event

    def _is_within_lookahead(self, reference: datetime, reminder_start: datetime) -> bool:
        return reminder_start >= reference - timedelta(minutes=self._lookahead)

    def collect(self, reference: datetime | None = None) -> List[CalendarEvent]:
        """Collect due events into a list (useful for polling loops)."""

        events = list(self.iter_due_events(reference))
        if events:
            self._logger.info("%d reminder(s) ready for notification", len(events))
        return events


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo:
        return value
    return value.replace(tzinfo=timezone.utc)


__all__ = ["ReminderScheduler"]
