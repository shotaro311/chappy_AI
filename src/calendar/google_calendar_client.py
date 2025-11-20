"""Google Calendar API client with graceful in-memory fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config.loader import AppConfig
from src.util.logging_utils import get_logger

_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    reminder_minutes: int = 10
    event_id: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class GoogleCalendarClient:
    """Talks to Google Calendar when credentials exist, otherwise stores events locally."""

    def __init__(self, config: AppConfig, *, calendar_id: str | None = None) -> None:
        self._config = config
        self._calendar_id = calendar_id or "primary"
        self._logger = get_logger(__name__)
        self._memory_events: Dict[str, CalendarEvent] = {}
        self._service = self._build_service_if_possible()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert_event(
        self,
        title: str,
        start: datetime,
        duration_minutes: int = 30,
        reminder_override: Optional[int] = None,
    ) -> CalendarEvent:
        reminder = reminder_override or self._config.calendar.reminder_minutes_default
        end = start + timedelta(minutes=duration_minutes)
        event = CalendarEvent(title=title, start=start, end=end, reminder_minutes=reminder)

        if self._service:
            body = self._build_event_body(event)
            try:  # pragma: no cover - requires network
                response = (
                    self._service.events()
                    .insert(calendarId=self._calendar_id, body=body)
                    .execute()
                )
                event.event_id = response.get("id", event.event_id)
            except HttpError as exc:  # fallback to memory but log error
                self._logger.warning("Google Calendar insert failed: %s", exc)
                self._service = None
        self._memory_events[event.event_id] = event
        self._logger.info("Scheduled event '%s' at %s", title, start.isoformat())
        return event

    def delete_event(self, event_id: str) -> None:
        if self._service:
            try:  # pragma: no cover - requires network
                self._service.events().delete(
                    calendarId=self._calendar_id, eventId=event_id
                ).execute()
            except HttpError as exc:
                self._logger.warning("Google Calendar delete failed: %s", exc)
                self._service = None
        if event_id in self._memory_events:
            deleted = self._memory_events.pop(event_id)
            self._logger.info("Deleted event '%s'", deleted.title)

    def list_upcoming(self) -> List[CalendarEvent]:
        if self._service:
            try:  # pragma: no cover - requires network
                now_iso = datetime.now(timezone.utc).isoformat()
                events_result = (
                    self._service.events()
                    .list(
                        calendarId=self._calendar_id,
                        timeMin=now_iso,
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=50,
                    )
                    .execute()
                )
                items = events_result.get("items", [])
                return [self._from_api_item(item) for item in items]
            except HttpError as exc:
                self._logger.warning("Google Calendar list failed: %s", exc)
                self._service = None
        # fall back to memory cache
        now = datetime.utcnow()
        return [evt for evt in self._memory_events.values() if evt.start >= now]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_service_if_possible(self):  # pragma: no cover - depends on env/network
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        if not (client_id and client_secret and refresh_token):
            self._logger.info("Google credentials not provided. Using in-memory calendar")
            return None
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=_TOKEN_URI,
        )
        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            self._logger.info("Google Calendar API client initialized")
            return service
        except Exception as exc:
            self._logger.warning("Failed to build Google Calendar service: %s", exc)
            return None

    def _build_event_body(self, event: CalendarEvent) -> Dict[str, object]:
        start_iso = _ensure_iso(event.start)
        end_iso = _ensure_iso(event.end)
        return {
            "summary": event.title,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": event.reminder_minutes},
                ],
            },
        }

    def _from_api_item(self, item: Dict[str, object]) -> CalendarEvent:
        start_iso = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
        end_iso = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        reminders = item.get("reminders", {}).get("overrides", [])
        reminder_minutes = reminders[0]["minutes"] if reminders else self._config.calendar.reminder_minutes_default
        return CalendarEvent(
            title=item.get("summary", "(untitled)"),
            start=start,
            end=end,
            reminder_minutes=reminder_minutes,
            event_id=item.get("id", ""),
        )


def _ensure_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


__all__ = ["GoogleCalendarClient", "CalendarEvent"]
