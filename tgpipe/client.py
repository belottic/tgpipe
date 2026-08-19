"""Creation and lifecycle of the Telethon client.

client.start() appears nowhere: it is the function that prompts behind your
back. Here we use connect() + is_user_authorized(), so a command run without a
session fails cleanly instead of hanging on a prompt.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Settings, get_settings
from .errors import NotAuthorized


def build_client(settings: Settings | None = None) -> TelegramClient:
    settings = settings or get_settings()
    session = (
        StringSession(settings.session_string.get_secret_value())
        if settings.session_string
        else str(settings.session_path)
    )
    return TelegramClient(
        session,
        settings.api_id,
        settings.api_hash.get_secret_value(),
        device_model=settings.device_model,
        app_version=settings.app_version,
        flood_sleep_threshold=settings.flood_max_wait,
        request_retries=settings.connection_retries,
        connection_retries=settings.connection_retries,
        timeout=settings.request_timeout,
    )


@asynccontextmanager
async def connected(
    *, require_auth: bool = True, settings: Settings | None = None
) -> AsyncIterator[TelegramClient]:
    """A connected client. With require_auth=True it exits with code 4 if the
    session is missing or expired, without ever asking the user anything."""
    settings = settings or get_settings()
    client = build_client(settings)
    await client.connect()
    try:
        if require_auth and not await client.is_user_authorized():
            raise NotAuthorized(session=str(settings.session_path))
        yield client
    finally:
        await client.disconnect()
