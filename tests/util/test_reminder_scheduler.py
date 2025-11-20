from datetime import datetime, timedelta, timezone

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config
from src.util.reminder_scheduler import ReminderScheduler


def test_scheduler_detects_due_events():
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    scheduler = ReminderScheduler(calendar)

    now = datetime(2025, 11, 20, 9, 0, tzinfo=timezone.utc)
    event_start = now + timedelta(minutes=9)
    calendar.upsert_event(title="会議", start=event_start, reminder_override=10)

    due = scheduler.collect(reference=now)
    assert len(due) == 1
    assert due[0].title == "会議"
