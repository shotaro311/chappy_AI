import asyncio

import pytest

from src.calendar.google_calendar_client import GoogleCalendarClient
from src.config.loader import load_config
from src.realtime.openai_realtime_client import RealtimeSession
from src.session.manager import SessionManager


class FakeAudioInput:
    def __init__(self):
        self.callback = None
        self.closed = False

    def open(self, callback, frame_samples=None):
        self.callback = callback

    def close(self):
        self.closed = True


class DummyRealtime(RealtimeSession):
    async def run(self, audio_source=None, **kwargs):  # type: ignore[override]
        if audio_source is None:
            return
        async for _ in audio_source:
            break


@pytest.mark.asyncio
async def test_session_manager_closes_audio(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config(app_env="pc.dev")
    calendar = GoogleCalendarClient(config, use_in_memory=True)
    realtime = DummyRealtime(config, calendar)
    audio = FakeAudioInput()
    manager = SessionManager(audio, realtime)

    async def _feed_frames():
        await asyncio.sleep(0)
        audio.callback(b"1234")
        await asyncio.sleep(0)

    task = asyncio.create_task(_feed_frames())
    await manager.run()
    await task
    assert audio.closed
