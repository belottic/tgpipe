"""Telegram address book, blocks, lookup by phone number."""

from __future__ import annotations

from typing import Annotated

import typer
from telethon import utils
from telethon.tl import functions, types

from ..client import connected
from ..models import Ok
from ..resolve import resolve
from ..runtime import run, state
from ..serialize import contact as ser_contact
from ..serialize import entity as ser_entity

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_contacts() -> None:
    """List the contacts in the Telegram address book."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(functions.contacts.GetContactsRequest(hash=0))
            users = getattr(result, "users", [])
            state.emit_all([ser_contact(u, raw=state.raw) for u in users])

    run(_run())


@app.command("add")
def add(
    phone: Annotated[str, typer.Option("--phone", help="+39...")],
    first_name: Annotated[str, typer.Option("--first-name")],
    last_name: Annotated[str, typer.Option("--last-name")] = "",
) -> None:
    """Add a contact to the address book."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(
                functions.contacts.ImportContactsRequest(
                    contacts=[
                        types.InputPhoneContact(
                            client_id=0, phone=phone,
                            first_name=first_name, last_name=last_name,
                        )
                    ]
                )
            )
            users = getattr(result, "users", [])
            if not users:
                state.emit(
                    Ok(ok=False, action="add",
                       details={"message": "number not on Telegram, or restrictive privacy settings",
                                "phone": phone})
                )
                return
            state.emit_all([ser_entity(u, raw=state.raw) for u in users])

    run(_run())


@app.command("delete")
def delete(chat: Annotated[str, typer.Argument(help="@username, id or phone number")]) -> None:
    """Remove a contact from the address book."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            await client(functions.contacts.DeleteContactsRequest(id=[ent]))
            state.emit(Ok(action="contacts delete",
                          details={"id": utils.get_peer_id(ent)}))

    run(_run())


@app.command("block")
def block(chat: Annotated[str, typer.Argument()]) -> None:
    """Block a user."""
    run(_toggle_block(chat, True))


@app.command("unblock")
def unblock(chat: Annotated[str, typer.Argument()]) -> None:
    """Unblock a user."""
    run(_toggle_block(chat, False))


async def _toggle_block(chat: str, blocking: bool) -> None:
    async with connected() as client:
        ent = await resolve(client, chat)
        request = (
            functions.contacts.BlockRequest if blocking
            else functions.contacts.UnblockRequest
        )
        await client(request(id=ent))
        state.emit(Ok(action="block" if blocking else "unblock",
                      details={"id": utils.get_peer_id(ent)}))


@app.command("blocked")
def blocked(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 100,
) -> None:
    """List blocked users."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(functions.contacts.GetBlockedRequest(offset=0, limit=limit))
            users = getattr(result, "users", [])
            state.emit_all([ser_contact(u, blocked=True, raw=state.raw) for u in users])

    run(_run())


@app.command("resolve")
def resolve_contact(
    target: Annotated[str, typer.Argument(help="+39..., @username or id")],
) -> None:
    """Resolve a phone number, a username or an id into its entity."""

    async def _run() -> None:
        async with connected() as client:
            state.emit(ser_entity(await resolve(client, target), raw=state.raw))

    run(_run())
