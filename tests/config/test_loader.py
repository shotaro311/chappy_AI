from src.config.loader import load_config


def test_load_config_merges_environment_settings():
    config = load_config(app_env="pc.dev")
    assert config.audio.input_device == "Mac 内蔵マイク"
    assert config.audio.sample_rate == 16000
    assert config.mode == "pc.dev"
