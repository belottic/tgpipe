"""Typed exceptions, exit codes, and translation of Telethon errors.

Rule: errors go to stderr as JSON, never to stdout.
"""

from __future__ import annotations

import json
import sys
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    GENERIC = 1
    USAGE = 2
    NOT_FOUND = 3
    NOT_AUTHORIZED = 4
    FLOOD_WAIT = 5
    FORBIDDEN = 6
    INTERRUPTED = 130


class TgpipeError(Exception):
    exit_code: ExitCode = ExitCode.GENERIC
    type: str = "error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = {k: v for k, v in details.items() if v is not None}

    def payload(self) -> dict[str, Any]:
        err: dict[str, Any] = {"type": self.type, "message": self.message}
        if self.details:
            err["details"] = self.details
        return {"error": err}


class ConfigError(TgpipeError):
    exit_code = ExitCode.USAGE
    type = "config"


class UsageError(TgpipeError):
    exit_code = ExitCode.USAGE
    type = "usage"


class EntityNotFound(TgpipeError):
    exit_code = ExitCode.NOT_FOUND
    type = "entity_not_found"


class NotAuthorized(TgpipeError):
    exit_code = ExitCode.NOT_AUTHORIZED
    type = "not_authorized"

    def __init__(
        self,
        message: str = "session missing or expired: run 'tgpipe auth login-start' and then 'tgpipe auth login'",
        **details: Any,
    ) -> None:
        super().__init__(message, **details)


class PasswordRequired(TgpipeError):
    exit_code = ExitCode.NOT_AUTHORIZED
    type = "password_required"

    def __init__(
        self,
        message: str = "the account has two-step verification: retry with --password (or TGPIPE_PASSWORD)",
        **details: Any,
    ) -> None:
        super().__init__(message, **details)


class AuthFailed(TgpipeError):
    exit_code = ExitCode.NOT_AUTHORIZED
    type = "auth_failed"


class FloodWaitExceeded(TgpipeError):
    exit_code = ExitCode.FLOOD_WAIT
    type = "flood_wait"


class Forbidden(TgpipeError):
    exit_code = ExitCode.FORBIDDEN
    type = "forbidden"


class SessionBusy(TgpipeError):
    """Another tgpipe process is already using this session file."""

    exit_code = ExitCode.GENERIC
    type = "session_busy"

    def __init__(self, session: str | None = None) -> None:
        super().__init__(
            "the session is already in use by another tgpipe process. "
            "Telethon keeps a transaction open on the session file, so only "
            "one command at a time can use it: wait for the other one to "
            "finish (typically 'messages watch', which keeps listening) or "
            "give this command a session of its own with TGPIPE_SESSION_PATH",
            session=session,
        )


# --- translation from Telethon errors --------------------------------------

_FORBIDDEN_NAMES = {
    "ChatWriteForbiddenError",
    "ChatAdminRequiredError",
    "ChannelPrivateError",
    "UserPrivacyRestrictedError",
    "UserBannedInChannelError",
    "MessageDeleteForbiddenError",
    "ChatSendMediaForbiddenError",
    "ChatRestrictedError",
    "UserNotParticipantError",
    "TakeoutRequiredError",
}

_NOT_FOUND_NAMES = {
    "UsernameNotOccupiedError",
    "UsernameInvalidError",
    "PeerIdInvalidError",
    "ChannelInvalidError",
    "UserIdInvalidError",
    "MessageIdsEmptyError",
    "InviteHashInvalidError",
    "InviteHashExpiredError",
}

_NOT_AUTHORIZED_NAMES = {
    "AuthKeyUnregisteredError",
    "AuthKeyInvalidError",
    "AuthKeyDuplicatedError",
    "SessionExpiredError",
    "SessionRevokedError",
    "UserDeactivatedError",
    "UserDeactivatedBanError",
    "UnauthorizedError",
}

_AUTH_FAILED_NAMES = {
    "PhoneCodeInvalidError",
    "PhoneCodeExpiredError",
    "PhoneCodeEmptyError",
    "PhoneNumberInvalidError",
    "PhoneNumberBannedError",
    "PhoneNumberUnoccupiedError",
    "PasswordHashInvalidError",
    "PhoneNumberFloodError",
}


def translate(exc: BaseException) -> TgpipeError:
    """Map any exception onto a TgpipeError with a sensible exit code."""
    if isinstance(exc, TgpipeError):
        return exc

    from telethon import errors as tg

    if isinstance(exc, tg.FloodWaitError):
        return FloodWaitExceeded(
            f"Telegram requires a wait of {exc.seconds}s "
            "(raise --flood-max-wait to absorb it automatically)",
            seconds=exc.seconds,
        )
    if isinstance(exc, tg.SessionPasswordNeededError):
        return PasswordRequired()

    name = type(exc).__name__
    message = str(exc) or name

    # two processes on the same session file: sqlite's raw error
    # ("database is locked") says nothing useful about what to do
    if name == "OperationalError" and "locked" in message.lower():
        return SessionBusy()

    if name in _FORBIDDEN_NAMES:
        return Forbidden(message, telethon_error=name)
    if name in _NOT_FOUND_NAMES:
        return EntityNotFound(message, telethon_error=name)
    if name in _NOT_AUTHORIZED_NAMES:
        return NotAuthorized(message, telethon_error=name)
    if name in _AUTH_FAILED_NAMES:
        return AuthFailed(message, telethon_error=name)

    # get_entity raises ValueError when it cannot resolve a peer
    if isinstance(exc, ValueError) and "entity" in message.lower():
        return EntityNotFound(message)

    if isinstance(exc, tg.RPCError):
        return TgpipeError(message, telethon_error=name)

    return TgpipeError(message, exception=name)


def emit_error(exc: TgpipeError) -> None:
    print(json.dumps(exc.payload(), ensure_ascii=False), file=sys.stderr, flush=True)
