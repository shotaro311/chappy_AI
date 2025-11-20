from datetime import datetime, timezone

import pytest

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config
from src.realtime.openai_realtime_client import RealtimeSession


@pytest.mark.asyncio
async def test_run_processes_tool_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    tool_call = {
        "name": "create_calendar_event",
        "arguments": {
            "title": "テスト予定",
            "datetime": datetime(2025, 11, 21, 10, 0, tzinfo=timezone.utc).isoformat(),
            "remind_before_minutes": 5,
        },
    }

    async with RealtimeSession(config, calendar, connect=False) as session:
        await session.run(tool_calls=[tool_call])

    events = calendar.list_upcoming()
    assert len(events) == 1
    assert events[0].title == "テスト予定"
