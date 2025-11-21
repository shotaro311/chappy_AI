from datetime import datetime, timedelta, timezone

import pytest

from src.gcal.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config
from src.realtime.openai_realtime_client import RealtimeSession


@pytest.mark.asyncio
async def test_run_processes_tool_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    tool_call = {
        "name": "schedule_reminder",
        "arguments": {
            "title": "テスト予定",
            "datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "remind_before_minutes": 5,
        },
    }

    async with RealtimeSession(config, calendar, start_connection=False) as session:
        await session.run(tool_calls=[tool_call])

    events = calendar.list_upcoming()
    assert len(events) == 1
    assert events[0].title == "テスト予定"
