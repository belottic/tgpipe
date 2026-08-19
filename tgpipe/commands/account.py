"""Active account sessions: security hygiene."""

from __future__ import annotations

from typing import Annotated

import typer
from telethon.tl import functions

from ..client import connected
from ..errors import UsageError
from ..models import Ok
from ..runtime import run, state
from ..serialize import auth_session as ser_auth_session

app = typer.Typer(no_args_is_help=True)


@app.command("sessions")
def sessions() -> None:
    """List the devices authorised on the account."""

    async def _run() -> None:
        async with connected() as client:
            result = await client(functions.account.GetAuthorizationsRequest())
            state.emit_all(
                [ser_auth_session(a, raw=state.raw) for a in result.authorizations]
            )

    run(_run())


@app.command("terminate-session")
def terminate_session(
    session_hash: Annotated[int, typer.Option("--hash", help="The 'hash' field from 'account sessions'")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm")] = False,
) -> None:
    """Terminate a single session."""
    if not yes:
        raise UsageError("irreversible operation: retry with --yes")
    if session_hash == 0:
        raise UsageError("hash 0 is the current session: use 'tgpipe auth logout'")

    async def _run() -> None:
        async with connected() as client:
            done = await client(
                functions.account.ResetAuthorizationRequest(hash=session_hash)
            )
            state.emit(Ok(ok=bool(done), action="terminate-session",
                          details={"hash": session_hash}))

    run(_run())


@app.command("terminate-others")
def terminate_others(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm")] = False,
) -> None:
    """Terminate every other session, keeping only this one."""
    if not yes:
        raise UsageError(
            "this will disconnect all your other devices: retry with --yes"
        )

    async def _run() -> None:
        async with connected() as client:
            await client(functions.auth.ResetAuthorizationsRequest())
            state.emit(Ok(action="terminate-others"))

    run(_run())
