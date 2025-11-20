from src.config.loader import load_config
from src.wakeword.porcupine_listener import WakeWordListener


class FakeAudioInputStream:
    def __init__(self) -> None:
        self.open_frame_samples = None
        self.closed = False

    def open(self, callback, *, frame_samples=None):
        self.open_frame_samples = frame_samples
        callback(b"\x00" * frame_samples * 2)

    def close(self):
        self.closed = True


class FakePorcupine:
    frame_length = 512

    def process(self, frame):
        return 0

    def delete(self):
        pass


class FakePorcupineModule:
    def __init__(self) -> None:
        self.instance = FakePorcupine()

    def create(self, **kwargs):
        return self.instance


def test_wait_for_wake_word_uses_porcu_frame_length(monkeypatch):
    monkeypatch.setenv("PORCUPINE_ACCESS_KEY", "dummy")
    fake_module = FakePorcupineModule()
    monkeypatch.setattr(
        "src.wakeword.porcupine_listener.pvporcupine", fake_module, False
    )

    config = load_config(app_env="pc.dev")
    audio = FakeAudioInputStream()
    listener = WakeWordListener(config, audio)

    listener.wait_for_wake_word()

    assert audio.open_frame_samples == fake_module.instance.frame_length
