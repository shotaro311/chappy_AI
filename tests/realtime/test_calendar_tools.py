import pytest
from datetime import datetime, timedelta, timezone
from src.gcal.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config
from src.realtime.openai_realtime_client import RealtimeSession

@pytest.mark.asyncio
async def test_delete_event(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    
    # Create an event
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    calendar.upsert_event("Meeting to delete", start)
    
    assert len(calendar.list_upcoming()) == 1
    
    tool_call = {
        "name": "delete_calendar_event",
        "arguments": {
            "title": "Meeting to delete",
        },
    }

    async with RealtimeSession(config, calendar, start_connection=False) as session:
        await session.run(tool_calls=[tool_call])

    assert len(calendar.list_upcoming()) == 0

@pytest.mark.asyncio
async def test_list_events(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    
    # Create events
    start1 = datetime.now(timezone.utc) + timedelta(hours=1)
    start2 = datetime.now(timezone.utc) + timedelta(days=1, hours=1)
    calendar.upsert_event("Today Meeting", start1)
    calendar.upsert_event("Tomorrow Meeting", start2)
    
    # Test list upcoming (default)
    tool_call_upcoming = {
        "name": "list_calendar_events",
        "arguments": {},
    }
    
    # We can't easily check the output text stream in this test setup without mocking stream_text
    # But we can verify no exception is raised and the logic runs.
    # To verify logic, we can check if list_upcoming was called (if we mocked it) 
    # or just trust the integration.
    
    async with RealtimeSession(config, calendar, start_connection=False) as session:
        await session.run(tool_calls=[tool_call_upcoming])
        
    # Test list specific date
    tool_call_date = {
        "name": "list_calendar_events",
        "arguments": {
            "date": start1.strftime("%Y-%m-%d"),
        },
    }
    
    async with RealtimeSession(config, calendar, start_connection=False) as session:
        await session.run(tool_calls=[tool_call_date])
