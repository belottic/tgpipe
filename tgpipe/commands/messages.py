"""Reading, searching, sending and managing messages."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from telethon import utils
from telethon.tl import functions, types

from ..client import connected
from ..errors import UsageError
from ..history import iter_history, media_filter
from ..models import Ok
from ..parsing import parse_date, parse_ids
from ..resolve import resolve
from ..runtime import run, state
from ..serialize import draft as ser_draft
from ..serialize import entity as ser_entity
from ..serialize import message as ser_message

app = typer.Typer(no_args_is_help=True)

_PARSE_MODES = {"md": "md", "markdown": "md", "html": "html", "none": None, "plain": None}


def _parse_mode(value: str) -> Any:
    if value not in _PARSE_MODES:
        raise UsageError(f"unknown parse-mode: {value!r} (md | html | none)")
    return _PARSE_MODES[value]


@app.command("history")
def history(
    chat: Annotated[str, typer.Argument(help="@username, id, title or 'me'")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="0 = no limit")] = 50,
    everything: Annotated[bool, typer.Option("--all", help="Same as --limit 0")] = False,
    offset_id: Annotated[
        int, typer.Option("--offset-id", help="Start before this id (pagination)")
    ] = 0,
    min_id: Annotated[int, typer.Option("--min-id")] = 0,
    max_id: Annotated[int, typer.Option("--max-id")] = 0,
    ids: Annotated[
        str | None, typer.Option("--ids", help="Specific ids: '1,2,5-8'")
    ] = None,
    since: Annotated[str | None, typer.Option("--since", help="ISO or relative (-24h)")] = None,
    until: Annotated[str | None, typer.Option("--until")] = None,
    from_user: Annotated[str | None, typer.Option("--from-user")] = None,
    kind: Annotated[str | None, typer.Option("--type", help="photo, video, url, voice, ...")] = None,
    reverse: Annotated[
        bool, typer.Option("--reverse", help="Oldest to newest")
    ] = False,
    with_chat: Annotated[
        bool, typer.Option("--with-chat", help="Include the chat entity in every record")
    ] = False,
) -> None:
    """History of a chat.

    To paginate, pass the last record's id as --offset-id: no separate cursor
    is needed.
    """

    # validate before connecting: a bad argument does not deserve a network
    # round-trip
    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")
    wanted_ids = parse_ids(ids) or None
    kind_filter = media_filter(kind)

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            sender = await resolve(client, from_user) if from_user else None
            chat_record = ser_entity(ent) if with_chat else None

            async def _stream():
                async for msg in iter_history(
                    client, ent,
                    limit=None if (everything or limit <= 0) else limit,
                    since=window_start, until=window_end,
                    offset_id=offset_id, min_id=min_id, max_id=max_id,
                    ids=wanted_ids,
                    filter=kind_filter, from_user=sender, reverse=reverse,
                ):
                    yield ser_message(msg, chat=chat_record, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Testo da cercare")],
    chat: Annotated[
        str | None, typer.Option("--chat", help="If omitted, searches every chat")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    since: Annotated[str | None, typer.Option("--since")] = None,
    until: Annotated[str | None, typer.Option("--until")] = None,
    from_user: Annotated[str | None, typer.Option("--from-user")] = None,
    kind: Annotated[str | None, typer.Option("--type")] = None,
) -> None:
    """Search messages in a chat, or everywhere without --chat."""

    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")
    kind_filter = media_filter(kind)

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat) if chat else None
            sender = await resolve(client, from_user) if from_user else None
            chats: dict[int, Any] = {}

            async def _stream():
                async for msg in iter_history(
                    client, ent,
                    limit=None if limit <= 0 else limit,
                    since=window_start, until=window_end,
                    search=query, filter=kind_filter, from_user=sender,
                ):
                    chat_record = None
                    if ent is None:
                        # global search: every line must say which chat it belongs to
                        peer = utils.get_peer_id(msg.peer_id) if msg.peer_id else 0
                        if peer not in chats:
                            chats[peer] = ser_entity(await msg.get_chat())
                        chat_record = chats[peer]
                    yield ser_message(msg, chat=chat_record, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


@app.command("send")
def send(
    chat: Annotated[str, typer.Argument()],
    text: Annotated[str | None, typer.Option("--text", "-t")] = None,
    text_file: Annotated[
        Path | None, typer.Option("--text-file", help="Read the text from a file")
    ] = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read the text from stdin")] = False,
    files: Annotated[
        list[Path] | None, typer.Option("--file", help="Attachment (repeatable)")
    ] = None,
    reply_to: Annotated[int | None, typer.Option("--reply-to", help="Id of the message to reply to")] = None,
    parse_mode: Annotated[str, typer.Option("--parse-mode", help="md | html | none")] = "md",
    silent: Annotated[bool, typer.Option("--silent", help="Send without a notification")] = False,
    no_webpage: Annotated[bool, typer.Option("--no-webpage", help="No link preview")] = False,
    force_document: Annotated[
        bool, typer.Option("--as-document", help="Send media as files, uncompressed")
    ] = False,
    schedule: Annotated[
        str | None, typer.Option("--schedule", help="Scheduled send: ISO or relative")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be sent, without sending")
    ] = False,
) -> None:
    """Send a message, with or without attachments."""
    sources = sum(1 for s in (text is not None, text_file is not None, stdin) if s)
    if sources > 1:
        raise UsageError("--text, --text-file and --stdin are mutually exclusive")

    body = text
    if text_file is not None:
        body = text_file.read_text(encoding="utf-8")
    elif stdin:
        body = sys.stdin.read()

    attachments = list(files or [])
    if not body and not attachments:
        raise UsageError("nothing to send: one of --text, --text-file, --stdin or --file is required")
    for path in attachments:
        if not path.exists():
            raise UsageError(f"file not found: {path}")

    mode = _parse_mode(parse_mode)
    schedule_at = parse_date(schedule, what="--schedule")

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            target = ser_entity(ent)

            if dry_run:
                state.emit(
                    Ok(
                        ok=True,
                        action="send (dry-run)",
                        details={
                            "chat_id": target.id,
                            "chat": target.name,
                            "text": body,
                            "files": [str(p) for p in attachments],
                            "reply_to": reply_to,
                            "schedule": schedule,
                        },
                    )
                )
                return

            common: dict[str, Any] = {
                "reply_to": reply_to,
                "parse_mode": mode,
                "silent": silent or None,
                "schedule": schedule_at,
            }
            if attachments:
                result = await client.send_file(
                    ent,
                    attachments if len(attachments) > 1 else attachments[0],
                    caption=body or None,
                    force_document=force_document,
                    **common,
                )
            else:
                result = await client.send_message(
                    ent, body, link_preview=not no_webpage, **common
                )

            sent = result if isinstance(result, list) else [result]
            state.emit_all([ser_message(m, chat=target) for m in sent])

    run(_run())


@app.command("forward")
def forward(
    ids: Annotated[str, typer.Option("--ids", help="Ids to forward: '1,2,5-8'")],
    source: Annotated[str, typer.Option("--from", help="Source chat")],
    dest: Annotated[str, typer.Option("--to", help="Destination chat")],
    silent: Annotated[bool, typer.Option("--silent")] = False,
    drop_author: Annotated[
        bool, typer.Option("--drop-author", help="Forward without crediting the author")
    ] = False,
) -> None:
    """Forward messages from one chat to another."""
    message_ids = parse_ids(ids)
    if not message_ids:
        raise UsageError("--ids contains no valid id")

    async def _run() -> None:
        async with connected() as client:
            src = await resolve(client, source)
            dst = await resolve(client, dest)
            result = await client.forward_messages(
                dst, message_ids, src, silent=silent or None,
                drop_author=drop_author or None,
            )
            sent = result if isinstance(result, list) else [result]
            target = ser_entity(dst)
            state.emit_all([ser_message(m, chat=target) for m in sent if m])

    run(_run())


@app.command("edit")
def edit(
    chat: Annotated[str, typer.Argument()],
    message_id: Annotated[int, typer.Argument(help="Message id")],
    text: Annotated[str | None, typer.Option("--text", "-t")] = None,
    text_file: Annotated[Path | None, typer.Option("--text-file")] = None,
    parse_mode: Annotated[str, typer.Option("--parse-mode")] = "md",
    no_webpage: Annotated[bool, typer.Option("--no-webpage")] = False,
) -> None:
    """Edit the text of one of your own messages."""
    body = text_file.read_text(encoding="utf-8") if text_file else text
    if body is None:
        raise UsageError("the new text is required: --text or --text-file")

    mode = _parse_mode(parse_mode)

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            result = await client.edit_message(
                ent, message_id, body,
                parse_mode=mode, link_preview=not no_webpage,
            )
            state.emit(ser_message(result, chat=ser_entity(ent)))

    run(_run())


@app.command("delete")
def delete(
    chat: Annotated[str, typer.Argument()],
    ids: Annotated[str, typer.Option("--ids", help="'1,2,5-8'")],
    revoke: Annotated[
        bool, typer.Option("--revoke/--no-revoke", help="Delete for everyone, not just you")
    ] = True,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm: this cannot be undone")] = False,
) -> None:
    """Delete messages."""
    message_ids = parse_ids(ids)
    if not message_ids:
        raise UsageError("--ids contains no valid id")
    if len(message_ids) > 10 and not yes:
        raise UsageError(
            f"you are about to irreversibly delete {len(message_ids)} messages: "
            "retry with --yes"
        )

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            result = await client.delete_messages(ent, message_ids, revoke=revoke)
            # Telegram accepts the request even for messages it then does not
            # remove (service messages, for one): pts_count says how many it
            # actually deleted. Reporting a bare "ok" would be a lie a script
            # would build wrong conclusions on.
            affected = sum(getattr(r, "pts_count", 0) or 0 for r in result)
            details: dict[str, Any] = {
                "chat_id": utils.get_peer_id(ent),
                "requested": message_ids,
                "deleted": affected,
                "revoke": revoke,
            }
            if affected < len(message_ids):
                missing = len(message_ids) - affected
                how_many = (
                    "1 message not removed" if missing == 1
                    else f"{missing} messages not removed"
                )
                details["note"] = (
                    f"{how_many}: Telegram does not delete service messages "
                    "(joins, pins, title changes) nor already-deleted ones"
                )
            state.emit(Ok(ok=affected > 0, action="delete", details=details))

    run(_run())


@app.command("pin")
def pin(
    chat: Annotated[str, typer.Argument()],
    message_id: Annotated[int, typer.Argument()],
    notify: Annotated[bool, typer.Option("--notify", help="Notify the members")] = False,
) -> None:
    """Pin a message to the top of the chat."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client.pin_message(ent, message_id, notify=notify)
            state.emit(Ok(action="pin", details={"chat_id": utils.get_peer_id(ent),
                                                 "message_id": message_id}))

    run(_run())


@app.command("unpin")
def unpin(
    chat: Annotated[str, typer.Argument()],
    message_id: Annotated[int | None, typer.Argument(help="Omitted = unpin all")] = None,
) -> None:
    """Unpin a message."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client.unpin_message(ent, message_id)
            state.emit(Ok(action="unpin", details={"chat_id": utils.get_peer_id(ent),
                                                   "message_id": message_id}))

    run(_run())


@app.command("react")
def react(
    chat: Annotated[str, typer.Argument()],
    message_id: Annotated[int, typer.Argument()],
    emoji: Annotated[
        str | None, typer.Option("--emoji", help="Omitted = remove the reaction")
    ] = None,
    big: Annotated[bool, typer.Option("--big", help="Big animation")] = False,
) -> None:
    """Add (or remove) a reaction on a message."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            reaction = [types.ReactionEmoji(emoticon=emoji)] if emoji else []
            await client(
                functions.messages.SendReactionRequest(
                    peer=ent, msg_id=message_id, reaction=reaction, big=big or None,
                )
            )
            state.emit(Ok(action="react", details={"chat_id": utils.get_peer_id(ent),
                                                   "message_id": message_id,
                                                   "emoji": emoji}))

    run(_run())


@app.command("drafts")
def drafts(
    chat: Annotated[str | None, typer.Option("--chat", help="Only this chat")] = None,
) -> None:
    """List saved drafts."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat) if chat else None

            async def _stream():
                async for dft in client.iter_drafts(ent):
                    if getattr(dft, "is_empty", False):
                        continue
                    yield ser_draft(dft.entity, dft, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


@app.command("scheduled")
def scheduled(chat: Annotated[str, typer.Argument()]) -> None:
    """List the scheduled messages in a chat."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            target = ser_entity(ent)
            messages = await client.get_messages(ent, scheduled=True)
            state.emit_all([ser_message(m, chat=target, raw=state.raw) for m in messages])

    run(_run())


@app.command("unschedule")
def unschedule(
    chat: Annotated[str, typer.Argument()],
    ids: Annotated[str, typer.Option("--ids")],
) -> None:
    """Cancel scheduled messages."""
    message_ids = parse_ids(ids)
    if not message_ids:
        raise UsageError("--ids contains no valid id")

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client(
                functions.messages.DeleteScheduledMessagesRequest(peer=ent, id=message_ids)
            )
            state.emit(Ok(action="unschedule",
                          details={"chat_id": utils.get_peer_id(ent), "ids": message_ids}))

    run(_run())


@app.command("watch")
def watch(
    chats: Annotated[
        list[str] | None, typer.Argument(help="Chats to follow (empty = all of them)")
    ] = None,
) -> None:
    """JSONL stream of incoming messages, until you interrupt it."""

    async def _run() -> None:
        from telethon import events

        async with connected() as client:
            targets = [await resolve(client, c) for c in (chats or [])]
            emitter = state.emitter
            known: dict[int, Any] = {}

            @client.on(events.NewMessage(chats=targets or None))
            async def _handler(event: Any) -> None:
                peer = utils.get_peer_id(event.message.peer_id)
                if peer not in known:
                    known[peer] = ser_entity(await event.get_chat())
                emitter.one(ser_message(event.message, chat=known[peer], raw=state.raw))

            await client.run_until_disconnected()

    run(_run())
