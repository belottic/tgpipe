"""Configuration: read from CLI flags, the environment, the project .env, defaults.

Credentials and the session are anchored to the **project root**, not to the
current directory, so the CLI (and the skill) work from anywhere. Output files
stay relative to the cwd, which is where whoever ran the command expects them.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

OutputFormat = Literal["json", "jsonl", "table"]


def project_home() -> Path:
    """Where .env, the session and the login state live.

    In order: an explicit TGPIPE_HOME, then the checkout root (recognised by
    the pyproject.toml sitting next to the package), and finally the cwd as a
    last resort for non-editable installs.
    """
    if override := os.environ.get("TGPIPE_HOME"):
        return Path(override).expanduser().resolve()
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return Path.cwd()


class Settings(BaseSettings):
    """tgpipe settings.

    Precedence: CLI arguments > environment variables > .env > defaults.
    For api_id/api_hash the TELEGRAM_ prefix is accepted too, since that is the
    convention used by the Telethon examples.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TGPIPE_",
        extra="ignore",
    )

    api_id: int = Field(
        validation_alias=AliasChoices("TGPIPE_API_ID", "TELEGRAM_API_ID"),
        description="api_id from https://my.telegram.org",
    )
    api_hash: SecretStr = Field(
        validation_alias=AliasChoices("TGPIPE_API_HASH", "TELEGRAM_API_HASH"),
        description="api_hash from https://my.telegram.org",
    )

    session_path: Path = Path("tgpipe.session")
    session_string: SecretStr | None = None
    login_state_path: Path = Path(".tgpipe-login.json")

    output_format: OutputFormat = Field(
        default="json",
        validation_alias=AliasChoices("TGPIPE_FORMAT", "TGPIPE_OUTPUT_FORMAT"),
    )
    download_dir: Path = Path("downloads")

    flood_max_wait: int = Field(default=60, ge=0)
    request_timeout: int = Field(default=30, gt=0)
    connection_retries: int = Field(default=3, ge=0)

    # used only by the non-interactive login flow
    phone: str | None = None
    code: str | None = None
    password: SecretStr | None = None

    device_model: str = "tgpipe"
    app_version: str = "0.1.0"


def _secure(path: Path) -> None:
    """Tighten permissions to 0600. Silent if the file does not exist yet."""
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except OSError:
        pass


def load_settings(home: Path | None = None) -> Settings:
    from .errors import ConfigError

    home = home or project_home()
    try:
        settings = Settings(_env_file=home / ".env")  # type: ignore[call-arg]
    except Exception as exc:  # ValidationError and friends
        raise ConfigError(_explain(exc, home)) from exc

    # relative session and login paths anchor to the project root; absolute
    # ones were chosen deliberately by the user
    if not settings.session_path.is_absolute():
        settings.session_path = home / settings.session_path
    if not settings.login_state_path.is_absolute():
        settings.login_state_path = home / settings.login_state_path

    for path in (settings.session_path, home / ".env", settings.login_state_path):
        _secure(path)
    return settings


@functools.cache
def get_settings() -> Settings:
    return load_settings()


def _explain(exc: Exception, home: Path) -> str:
    """Turn a pydantic ValidationError into something actionable."""
    from pydantic import ValidationError

    if not isinstance(exc, ValidationError):
        return str(exc)

    missing = [
        ".".join(str(p) for p in err["loc"])
        for err in exc.errors()
        if err["type"] == "missing"
    ]
    if missing:
        # with validation_alias the loc is already the environment variable name
        names = ", ".join(
            m.upper() if m.upper().startswith(("TGPIPE_", "TELEGRAM_"))
            else f"TGPIPE_{m.upper()}"
            for m in missing
        )
        return (
            f"incomplete configuration: missing {names}. "
            f"Expected in {home / '.env'} or in the environment. "
            "Create the values at https://my.telegram.org -> API development tools"
        )
    problems = "; ".join(
        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
    return f"invalid configuration: {problems}"
