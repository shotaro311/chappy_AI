from datetime import datetime, timedelta, timezone

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config


def test_upsert_and_list_in_memory(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

    config = load_config(app_env="pc.dev")
    client = GoogleCalendarClient(config, use_in_memory=True)

    start = datetime(2025, 11, 20, 10, 0, tzinfo=timezone.utc)
    client.upsert_event("テスト", start=start, duration_minutes=45, reminder_override=15)

    # Use reference_time to test with a fixed time point
    reference = start - timedelta(hours=1)
    events = client.list_upcoming(reference_time=reference)
    assert len(events) == 1
    assert events[0].title == "テスト"
    assert events[0].reminder_minutes == 15

    client.delete_event(events[0].event_id)
    assert client.list_upcoming(reference_time=reference) == []
