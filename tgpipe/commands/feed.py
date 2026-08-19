"""Cross-chat views: digest, inbox, mentions.

These are top-level commands because they answer the question asked most
often ("what did I miss?") without forcing a chats list plus N calls to
history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import typer
from telethon import TelegramClient, utils
from telethon.tl import types

from ..client import connected
from ..errors import UsageError
from ..history import iter_history
from ..models import InboxEntry
from ..parsing import parse_csv, parse_date
from ..resolve import resolve
from ..runtime import run, state
from ..serialize import entity as ser_entity
from ..serialize import message as ser_message

_KINDS = ("user", "bot", "group", "channel")


def _matches_kind(entity_kind: str, wanted: str | None) -> bool:
    return wanted is None or entity_kind == wanted


async def _selected_dialogs(
    client: TelegramClient,
    *,
    since: datetime | None,
    kind: str | None,
    only: set[int],
    exclude: set[int],
    include_archived: bool,
) -> list[Any]:
    """Candidate dialogs, stopping as soon as we fall out of the time window.

    iter_dialogs yields pinned dialogs first and the rest by recency: the
    first non-pinned dialog older than `since` guarantees every later one is
    too, so that is where we can break.
    """
    selected = []
    async for dlg in client.iter_dialogs(archived=None if include_archived else False):
        if since is not None and dlg.date is not None and dlg.date < since:
            if not dlg.pinned:
                break
            continue
        chat_id = utils.get_peer_id(dlg.entity)
        if only and chat_id not in only:
            continue
        if chat_id in exclude:
            continue
        record = ser_entity(dlg.entity)
        if record is None or not _matches_kind(record.kind, kind):
            continue
        selected.append(dlg)
    return selected


async def _ids_of(client: TelegramClient, values: list[str]) -> set[int]:
    return {utils.get_peer_id(await resolve(client, v)) for v in values}


def digest(
    since: Annotated[
        str, typer.Option("--since", help="Start of the window: -24h, -7d, 2026-08-01")
    ] = "-24h",
    until: Annotated[str | None, typer.Option("--until")] = None,
    chats: Annotated[
        str | None, typer.Option("--chats", help="Only these chats, comma separated")
    ] = None,
    exclude: Annotated[str | None, typer.Option("--exclude", help="Exclude these chats")] = None,
    kind: Annotated[str | None, typer.Option("--type", help=", ".join(_KINDS))] = None,
    limit_per_chat: Annotated[
        int, typer.Option("--limit-per-chat", help="0 = no limit")
    ] = 100,
    unread_only: Annotated[
        bool, typer.Option("--unread-only", help="Only chats with unread messages")
    ] = False,
    incoming_only: Annotated[
        bool, typer.Option("--incoming-only", help="Exclude your own messages")
    ] = False,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
) -> None:
    """Every message received in the window, grouped by chat.

    Each line stands alone: the `chat` object sits inside the record rather
    than being implied by the ordering, so the stream can be processed line
    by line.
    """
    if kind and kind not in _KINDS:
        raise UsageError(f"unknown type: {kind!r} ({', '.join(_KINDS)})")

    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")

    async def _run() -> None:
        async with connected() as client:
            only = await _ids_of(client, parse_csv(chats))
            skip = await _ids_of(client, parse_csv(exclude))
            dialogs = await _selected_dialogs(
                client, since=window_start, kind=kind, only=only,
                exclude=skip, include_archived=include_archived,
            )

            async def _stream():
                for dlg in dialogs:
                    if unread_only and not dlg.unread_count:
                        continue
                    chat_record = ser_entity(dlg.entity)
                    async for msg in iter_history(
                        client, dlg.entity,
                        limit=None if limit_per_chat <= 0 else limit_per_chat,
                        since=window_start, until=window_end,
                    ):
                        if incoming_only and getattr(msg, "out", False):
                            continue
                        yield ser_message(msg, chat=chat_record, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


def inbox(
    limit_chats: Annotated[int, typer.Option("--limit-chats", "-n")] = 30,
    preview: Annotated[
        int, typer.Option("--preview", "-p", help="How many recent messages per chat")
    ] = 3,
    folder: Annotated[int | None, typer.Option("--folder")] = None,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
    mentions_only: Annotated[
        bool, typer.Option("--mentions-only", help="Only chats with unread mentions")
    ] = False,
) -> None:
    """Overview of unread chats with their latest messages, in a single call."""

    async def _run() -> None:
        async with connected() as client:
            kwargs: dict[str, Any] = {}
            if folder is not None:
                kwargs["folder"] = folder
            elif include_archived:
                kwargs["archived"] = None
            else:
                kwargs["archived"] = False

            entries: list[InboxEntry] = []
            async for dlg in client.iter_dialogs(**kwargs):
                mentions = getattr(dlg, "unread_mentions_count", 0) or 0
                unread = dlg.unread_count or 0
                if mentions_only and not mentions:
                    continue
                if not mentions_only and not unread:
                    continue

                chat_record = ser_entity(dlg.entity)
                messages = []
                if preview > 0:
                    fetched = await client.get_messages(
                        dlg.entity, limit=min(preview, unread or preview)
                    )
                    messages = [
                        ser_message(m, raw=state.raw) for m in fetched if m is not None
                    ]
                entries.append(
                    InboxEntry(
                        entity=chat_record,  # type: ignore[arg-type]
                        unread_count=unread,
                        unread_mentions=mentions,
                        archived=bool(getattr(dlg, "archived", False)),
                        last_messages=messages,
                    )
                )
                if limit_chats > 0 and len(entries) >= limit_chats:
                    break

            state.emit_all(entries)

    run(_run())


def mentions(
    since: Annotated[str | None, typer.Option("--since", help="e.g. -7d")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Per chat; 0 = no limit")] = 50,
    all_chats: Annotated[
        bool,
        typer.Option(
            "--all-chats",
            help="Scan every chat instead of just unread mentions. Much slower.",
        ),
    ] = False,
) -> None:
    """Messages that mention you or reply to you.

    By default it only looks at chats with unread mentions, which is fast.
    With --all-chats it scans everything: correct, but slow on large accounts.
    """

    window_start = parse_date(since, what="--since")

    async def _run() -> None:
        async with connected() as client:
            async def _stream():
                async for dlg in client.iter_dialogs(archived=None):
                    pending = getattr(dlg, "unread_mentions_count", 0) or 0
                    if not all_chats and not pending:
                        continue
                    if all_chats and window_start and dlg.date and dlg.date < window_start:
                        if not dlg.pinned:
                            break
                        continue

                    chat_record = ser_entity(dlg.entity)
                    per_chat = pending if (not all_chats and pending) else (
                        None if limit <= 0 else limit
                    )
                    async for msg in iter_history(
                        client, dlg.entity, limit=per_chat, since=window_start,
                        filter=types.InputMessagesFilterMyMentions,
                    ):
                        yield ser_message(msg, chat=chat_record, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


def register(app: typer.Typer) -> None:
    app.command("digest")(digest)
    app.command("inbox")(inbox)
    app.command("mentions")(mentions)
