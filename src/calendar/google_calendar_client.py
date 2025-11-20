"""In-memory calendar client stub following Google Calendar semantics."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.config.loader import AppConfig
from src.util.logging_utils import get_logger


@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    reminder_minutes: int = 10
    event_id: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class GoogleCalendarClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._logger = get_logger(__name__)
        self._events: Dict[str, CalendarEvent] = {}

    def upsert_event(
        self,
        title: str,
        start: datetime,
        duration_minutes: int = 30,
        reminder_override: Optional[int] = None,
    ) -> CalendarEvent:
        reminder = reminder_override or self._config.calendar.reminder_minutes_default
        event = CalendarEvent(
            title=title,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            reminder_minutes=reminder,
        )
        self._events[event.event_id] = event
        self._logger.info("Scheduled event '%s' at %s", title, start.isoformat())
        return event

    def delete_event(self, event_id: str) -> None:
        if event_id in self._events:
            deleted = self._events.pop(event_id)
            self._logger.info("Deleted event '%s'", deleted.title)

    def list_upcoming(self) -> List[CalendarEvent]:
        now = datetime.utcnow()
        return [evt for evt in self._events.values() if evt.start >= now]


__all__ = ["GoogleCalendarClient", "CalendarEvent"]
