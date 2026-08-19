"""Chats, groups, channels: listing, detail, members, actions."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from telethon import utils
from telethon.tl import functions, types

from ..client import connected
from ..errors import UsageError
from ..models import Ok
from ..resolve import parse_link, resolve
from ..runtime import run, state
from ..serialize import dialog as ser_dialog
from ..serialize import entity as ser_entity
from ..serialize import entity_full, folder as ser_folder
from ..serialize import member as ser_member

app = typer.Typer(no_args_is_help=True)

_KINDS = ("user", "bot", "group", "channel")

_PARTICIPANT_FILTERS = {
    "admins": types.ChannelParticipantsAdmins,
    "bots": types.ChannelParticipantsBots,
    "kicked": types.ChannelParticipantsKicked,
    "banned": types.ChannelParticipantsBanned,
}


@app.command("list")
def list_chats(
    limit: Annotated[int, typer.Option("--limit", "-n", help="0 = all of them")] = 50,
    archived: Annotated[
        bool, typer.Option("--archived/--not-archived", help="Only (or never) archived ones")
    ] = False,
    everything: Annotated[
        bool, typer.Option("--all", help="Include archived chats too")
    ] = False,
    kind: Annotated[
        str | None, typer.Option("--type", help=f"Filter by type: {', '.join(_KINDS)}")
    ] = None,
    query: Annotated[
        str | None, typer.Option("--query", "-q", help="Filter by substring in the title")
    ] = None,
    folder: Annotated[int | None, typer.Option("--folder", help="Folder id")] = None,
) -> None:
    """List your own dialogs (chats, groups, channels)."""
    if kind and kind not in _KINDS:
        raise UsageError(f"unknown type: {kind!r} ({', '.join(_KINDS)})")

    async def _run() -> None:
        async with connected() as client:
            kwargs: dict[str, Any] = {"limit": None if limit <= 0 else limit}
            if folder is not None:
                kwargs["folder"] = folder
            elif everything:
                kwargs["archived"] = None
            else:
                kwargs["archived"] = archived

            needle = query.casefold() if query else None

            async def _stream():
                count = 0
                async for dlg in client.iter_dialogs(**kwargs):
                    record = ser_dialog(dlg, raw=state.raw)
                    if kind and record.entity.kind != kind:
                        continue
                    if needle and needle not in (record.entity.name or "").casefold():
                        continue
                    yield record
                    count += 1
                    if limit > 0 and count >= limit:
                        return

            await state.emit_stream(_stream())

    run(_run())


@app.command("info")
def info(chat: Annotated[str, typer.Argument(help="@username, id, title or 'me'")]) -> None:
    """Detail of a chat, enriched with the fields only the Full request carries."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            full: Any = None
            try:
                if isinstance(ent, types.Channel):
                    full = await client(functions.channels.GetFullChannelRequest(ent))
                elif isinstance(ent, types.Chat):
                    full = await client(functions.messages.GetFullChatRequest(ent.id))
                elif isinstance(ent, types.User):
                    full = await client(functions.users.GetFullUserRequest(ent))
            except Exception:
                full = None
            record = entity_full(full, ent, raw=state.raw) if full else ser_entity(ent, raw=state.raw)
            state.emit(record)

    run(_run())


@app.command("members")
def members(
    chat: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit", "-n", help="0 = all of them")] = 200,
    query: Annotated[str | None, typer.Option("--query", "-q", help="Search by name")] = None,
    kind: Annotated[
        str | None,
        typer.Option("--filter", help=f"{', '.join(_PARTICIPANT_FILTERS)}"),
    ] = None,
) -> None:
    """List the members of a group or channel."""
    if kind and kind not in _PARTICIPANT_FILTERS:
        raise UsageError(
            f"unknown filter: {kind!r} ({', '.join(_PARTICIPANT_FILTERS)})"
        )

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            kwargs: dict[str, Any] = {"limit": None if limit <= 0 else limit}
            if query:
                kwargs["search"] = query
            if kind:
                kwargs["filter"] = _PARTICIPANT_FILTERS[kind]()

            async def _stream():
                async for user in client.iter_participants(ent, **kwargs):
                    yield ser_member(user, raw=state.raw)

            await state.emit_stream(_stream())

    run(_run())


@app.command("join")
def join(target: Annotated[str, typer.Argument(help="@username or t.me link")]) -> None:
    """Join a channel or group, invite links included."""

    async def _run() -> None:
        async with connected() as client:
            link = parse_link(target)
            if link and link[0] == "invite":
                result = await client(functions.messages.ImportChatInviteRequest(link[1]))
                chats = getattr(result, "chats", [])
                state.emit(ser_entity(chats[0]) if chats else Ok(action="join"))
                return
            ent = await resolve(client, target)
            await client(functions.channels.JoinChannelRequest(ent))
            state.emit(ser_entity(ent))

    run(_run())


@app.command("leave")
def leave(
    chat: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm leaving")] = False,
) -> None:
    """Leave a group or channel (or delete the conversation)."""
    if not yes:
        raise UsageError("irreversible operation: retry with --yes")

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client.delete_dialog(ent)
            state.emit(Ok(action="leave", details={"chat_id": utils.get_peer_id(ent)}))

    run(_run())


@app.command("archive")
def archive(chat: Annotated[str, typer.Argument()]) -> None:
    """Move the chat to the archive."""
    run(_set_folder(chat, 1, "archive"))


@app.command("unarchive")
def unarchive(chat: Annotated[str, typer.Argument()]) -> None:
    """Bring the chat back from the archive to the main list."""
    run(_set_folder(chat, 0, "unarchive"))


async def _set_folder(chat: str, folder: int, action: str) -> None:
    async with connected() as client:
        ent = await resolve(client, chat)
        await client.edit_folder(ent, folder=folder)
        state.emit(Ok(action=action, details={"chat_id": utils.get_peer_id(ent)}))


@app.command("folders")
def folders() -> None:
    """List the configured folders (dialog filters)."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(functions.messages.GetDialogFiltersRequest())
            filters = getattr(result, "filters", result)
            records = [
                ser_folder(f, raw=state.raw)
                for f in filters
                if not isinstance(f, types.DialogFilterDefault)
            ]
            state.emit_all(records)

    run(_run())


@app.command("mark-read")
def mark_read(
    chat: Annotated[str, typer.Argument()],
    mentions: Annotated[
        bool, typer.Option("--mentions/--no-mentions", help="Clear unread mentions too")
    ] = True,
) -> None:
    """Mark the chat as read."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client.send_read_acknowledge(ent, clear_mentions=mentions)
            state.emit(Ok(action="mark-read", details={"chat_id": utils.get_peer_id(ent)}))

    run(_run())


def rank_search_results(result: Any, limit: int) -> list[Any]:
    """contacts.Search results in relevance order, honouring the limit.

    `users` and `chats` also contain entities merely referenced by the results,
    so emitting them all ignores the limit and loses the ranking. The real
    ranking is in my_results + results, which are Peers and need remapping.
    """
    by_id = {
        utils.get_peer_id(e): e
        for e in (*getattr(result, "users", []), *getattr(result, "chats", []))
    }
    found: list[Any] = []
    seen: set[int] = set()
    for peer in (*getattr(result, "my_results", []), *getattr(result, "results", [])):
        peer_id = utils.get_peer_id(peer)
        entity = by_id.get(peer_id)
        if entity is None or peer_id in seen:
            continue
        seen.add(peer_id)
        found.append(entity)
        if limit > 0 and len(found) >= limit:
            break
    return found


@app.command("search-public")
def search_public(
    query: Annotated[str, typer.Argument(help="Text to search for")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
) -> None:
    """Search public users and channels across all of Telegram."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(
                functions.contacts.SearchRequest(q=query, limit=limit)
            )
            found = rank_search_results(result, limit)
            state.emit_all([ser_entity(e, raw=state.raw) for e in found])

    run(_run())
