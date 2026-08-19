"""History iteration, shared by messages / feed / export.

Telethon has no `min_date`: for --since we iterate backwards and stop at the
first message older than the threshold. The limit has to be applied here,
after filtering, or it would count the discarded messages too.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from telethon import TelegramClient
from telethon.tl import types

from .errors import UsageError

MEDIA_FILTERS: dict[str, Any] = {
    "photo": types.InputMessagesFilterPhotos,
    "video": types.InputMessagesFilterVideo,
    "media": types.InputMessagesFilterPhotoVideo,
    "document": types.InputMessagesFilterDocument,
    "file": types.InputMessagesFilterDocument,
    "audio": types.InputMessagesFilterMusic,
    "music": types.InputMessagesFilterMusic,
    "voice": types.InputMessagesFilterVoice,
    "gif": types.InputMessagesFilterGif,
    "url": types.InputMessagesFilterUrl,
    "link": types.InputMessagesFilterUrl,
    "sticker": types.InputMessagesFilterDocument,
    "pinned": types.InputMessagesFilterPinned,
    "mention": types.InputMessagesFilterMyMentions,
    "contact": types.InputMessagesFilterContacts,
    "geo": types.InputMessagesFilterGeo,
    "round": types.InputMessagesFilterRoundVideo,
}


def media_filter(name: str | None) -> Any | None:
    if not name:
        return None
    try:
        return MEDIA_FILTERS[name.lower()]
    except KeyError:
        raise UsageError(
            f"unknown type: {name!r}. Available: {', '.join(sorted(MEDIA_FILTERS))}"
        ) from None


async def iter_history(
    client: TelegramClient,
    entity: Any,
    *,
    limit: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset_id: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    ids: list[int] | None = None,
    search: str | None = None,
    filter: Any | None = None,
    from_user: Any | None = None,
    reverse: bool = False,
) -> AsyncIterator[types.Message]:
    """Filtered history. With `ids` every other search criterion is ignored."""
    if ids:
        messages = await client.get_messages(entity, ids=ids)
        for msg in messages:
            if msg is not None:
                yield msg
        return

    kwargs: dict[str, Any] = {
        "offset_id": offset_id,
        "min_id": min_id,
        "max_id": max_id,
        "reverse": reverse,
    }
    if search:
        kwargs["search"] = search
    if filter is not None:
        kwargs["filter"] = filter
    if from_user is not None:
        kwargs["from_user"] = from_user

    # the starting point: going backwards it is `until`, forwards it is `since`
    boundary = since if reverse else until
    if boundary is not None:
        kwargs["offset_date"] = boundary

    # with date filters we apply the limit ourselves, after discarding
    date_filtered = since is not None or until is not None
    if limit is not None and not date_filtered:
        kwargs["limit"] = limit

    yielded = 0
    async for msg in client.iter_messages(entity, **kwargs):
        date = msg.date
        if date is not None:
            if reverse:
                if until is not None and date > until:
                    return
                if since is not None and date < since:
                    continue
            else:
                if since is not None and date < since:
                    return
                if until is not None and date > until:
                    continue
        yield msg
        yielded += 1
        if limit is not None and yielded >= limit:
            return
