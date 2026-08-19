"""Resolving a CHAT argument into a Telegram entity.

Accepted forms:
  me | self | saved            -> Saved Messages
  @username                    -> explicit username, searched across Telegram
  123456 | -1001234567890      -> id (marked form included)
  https://t.me/xxx | t.me/xxx | t.me/+HASH | t.me/joinchat/HASH
  +391234567890                -> phone number (must be a contact)
  "Chat title"                 -> matched against the user's **own** dialogs

The ordering for bare strings is deliberate: own dialogs first, the rest of
Telegram second. Someone typing `Project` means their own "Project" chat, not
a public bot with the same name; `@Project` exists for that. On a write
command the difference is not academic.
"""

from __future__ import annotations

import re
from typing import Any

from telethon import TelegramClient, utils

from .errors import EntityNotFound, UsageError

_SELF = {"me", "self", "saved", "saved messages"}
_LINK = re.compile(
    r"^(?:https?://)?(?:t(?:elegram)?\.me|telegram\.dog)/(?P<rest>.+)$", re.IGNORECASE
)
_PHONE = re.compile(r"^\+\d{6,15}$")
_NUMERIC = re.compile(r"^-?\d+$")

_NOT_FOUND_ERRORS = {
    "UsernameNotOccupiedError", "UsernameInvalidError", "PeerIdInvalidError",
    "ChannelInvalidError", "UserIdInvalidError",
}


def parse_link(value: str) -> tuple[str, str] | None:
    """Return ('invite', hash) or ('username', name) for a t.me link."""
    match = _LINK.match(value.strip())
    if not match:
        return None
    rest = match.group("rest").split("?")[0].strip("/")
    if rest.startswith("+"):
        return ("invite", rest[1:])
    if rest.startswith("joinchat/"):
        return ("invite", rest[len("joinchat/"):])
    # t.me/channel/123 -> only the channel matters to us
    return ("username", rest.split("/")[0].lstrip("@"))


async def _lookup(client: TelegramClient, candidate: Any) -> Any | None:
    try:
        return await client.get_entity(candidate)
    except (ValueError, TypeError):
        return None
    except Exception as exc:
        if type(exc).__name__ in _NOT_FOUND_ERRORS:
            return None
        raise


async def _dialog_matches(client: TelegramClient, needle: str) -> tuple[list, list]:
    """(exact matches, partial matches) against the user's own dialog titles."""
    lowered = needle.casefold()
    exact: list[Any] = []
    partial: list[Any] = []
    async for dialog in client.iter_dialogs():
        name = (utils.get_display_name(dialog.entity) or "").casefold()
        if not name:
            continue
        if name == lowered:
            exact.append(dialog.entity)
        elif lowered in name:
            partial.append(dialog.entity)
    return exact, partial


def _ambiguous(needle: str, matches: list[Any]) -> EntityNotFound:
    return EntityNotFound(
        f"{needle!r} matches {len(matches)} chats: use the numeric id "
        "(find it with 'tgpipe chats list')",
        matches=[
            {"id": utils.get_peer_id(e), "name": utils.get_display_name(e)}
            for e in matches[:10]
        ],
    )


async def resolve(client: TelegramClient, value: str) -> Any:
    """CHAT -> Telethon entity. Raises EntityNotFound if it does not resolve."""
    if value is None or not str(value).strip():
        raise UsageError("no chat given")

    raw = str(value).strip()
    if raw.casefold() in _SELF:
        return await client.get_me()

    if link := parse_link(raw):
        kind, payload = link
        if kind == "invite":
            raise UsageError(
                f"{raw!r} is an invite link: use 'tgpipe chats join' to join, "
                "then refer to the chat by id or title"
            )
        raw = "@" + payload

    # a numeric id and a phone number are unambiguous
    if _NUMERIC.match(raw):
        if (found := await _lookup(client, int(raw))) is not None:
            return found
        raise EntityNotFound(f"no chat with id {raw}", query=str(value))

    if _PHONE.match(raw):
        if (found := await _lookup(client, raw)) is not None:
            return found
        raise EntityNotFound(
            f"no user for the number {raw}: it must be one of your contacts",
            query=str(value),
        )

    # @name: explicit username, searched across all of Telegram
    if raw.startswith("@"):
        if (found := await _lookup(client, raw.lstrip("@"))) is not None:
            return found
        raise EntityNotFound(f"no username {raw}", query=str(value))

    # bare string: own chats first, the rest of Telegram second
    exact, partial = await _dialog_matches(client, raw)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise _ambiguous(raw, exact)

    if (found := await _lookup(client, raw)) is not None:
        return found

    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise _ambiguous(raw, partial)

    raise EntityNotFound(
        f"no chat matches {value!r}. Try the numeric id "
        "(see 'tgpipe chats list') or @username",
        query=str(value),
    )


async def resolve_many(client: TelegramClient, values: list[str]) -> list[Any]:
    return [await resolve(client, value) for value in values]
