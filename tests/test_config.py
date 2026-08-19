import pytest

from tgpipe.config import Settings
from tgpipe.errors import ConfigError


def _clean_env(monkeypatch, tmp_path):
    for name in list(__import__("os").environ):
        if name.startswith(("TGPIPE_", "TELEGRAM_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    # without this the tests would read the project's real .env and session
    monkeypatch.setenv("TGPIPE_HOME", str(tmp_path))


def test_complete_env_file(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    settings = Settings()
    assert settings.api_id == 1
    assert settings.api_hash.get_secret_value() == "abc"
    assert settings.output_format == "json"


def test_telegram_prefix_accepted(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TELEGRAM_API_ID=2\nTELEGRAM_API_HASH=xyz\n")
    assert Settings().api_id == 2


def test_env_takes_precedence_over_the_file(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    monkeypatch.setenv("TGPIPE_API_ID", "999")
    assert Settings().api_id == 999


def test_api_hash_does_not_leak_in_repr(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=segretissimo\n")
    assert "segretissimo" not in repr(Settings())


def test_incomplete_config_gives_an_actionable_message(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    from tgpipe import config

    config.get_settings.cache_clear()
    with pytest.raises(ConfigError) as excinfo:
        config.get_settings()
    message = excinfo.value.message
    assert "TGPIPE_API_ID" in message
    assert "TGPIPE_TGPIPE" not in message
    assert excinfo.value.exit_code == 2
    config.get_settings.cache_clear()


def test_invalid_format(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(
        "TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\nTGPIPE_FORMAT=yaml\n"
    )
    with pytest.raises(Exception):
        Settings()


# --- anchoring to the project root -----------------------------------------


def test_home_from_an_explicit_variable(monkeypatch, tmp_path):
    from tgpipe.config import project_home

    monkeypatch.setenv("TGPIPE_HOME", str(tmp_path))
    assert project_home() == tmp_path.resolve()


def test_home_is_the_checkout_root(monkeypatch):
    from tgpipe.config import project_home

    monkeypatch.delenv("TGPIPE_HOME", raising=False)
    home = project_home()
    assert (home / "pyproject.toml").is_file()
    assert (home / "tgpipe" / "config.py").is_file()


def test_session_anchored_to_home_not_to_the_cwd(monkeypatch, tmp_path):
    """The CLI must find the session even when run from another directory."""
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    altrove = tmp_path / "altrove"
    altrove.mkdir()
    monkeypatch.chdir(altrove)

    from tgpipe.config import load_settings

    settings = load_settings()
    assert settings.session_path == tmp_path / "tgpipe.session"
    assert settings.login_state_path == tmp_path / ".tgpipe-login.json"


def test_absolute_session_path_respected(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    scelta = tmp_path / "altrove" / "mia.session"
    (tmp_path / ".env").write_text(
        f"TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\nTGPIPE_SESSION_PATH={scelta}\n"
    )

    from tgpipe.config import load_settings

    assert load_settings().session_path == scelta


def test_download_dir_stays_relative_to_the_cwd(monkeypatch, tmp_path):
    """Output files belong where the user is working, not in the project."""
    _clean_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")

    from tgpipe.config import load_settings

    assert not load_settings().download_dir.is_absolute()


def test_error_message_says_where_it_looked(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    from tgpipe.config import load_settings

    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert str(tmp_path / ".env") in excinfo.value.message
