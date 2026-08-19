"""Authentication: the only place in the program where a prompt may exist,
and only behind the explicit --interactive flag."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from telethon import errors
from telethon.sessions import StringSession

from ..client import build_client, connected
from ..errors import AuthFailed, NotAuthorized, PasswordRequired, UsageError
from ..models import AuthStatus, LoginRequest, Ok
from ..output import note
from ..runtime import run, state
from ..serialize import entity

app = typer.Typer(no_args_is_help=True)


# --- state of the two-step login -------------------------------------------


def _state_path() -> Path:
    return state.settings.login_state_path


def _save_login_state(phone: str, phone_code_hash: str) -> None:
    path = _state_path()
    path.write_text(
        json.dumps({"phone": phone, "phone_code_hash": phone_code_hash}),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _load_login_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _clear_login_state() -> None:
    _state_path().unlink(missing_ok=True)


def _read_stdin_value(value: str | None) -> str | None:
    """'-' means: read it from stdin (a single line)."""
    if value == "-":
        line = sys.stdin.readline().strip()
        return line or None
    return value


# --- comandi ---------------------------------------------------------------


@app.command("login-start")
def login_start(
    phone: Annotated[
        str | None,
        typer.Option("--phone", envvar="TGPIPE_PHONE", help="Phone number in +39... form"),
    ] = None,
    force_sms: Annotated[
        bool, typer.Option("--sms", help="Force delivery by SMS instead of in-app")
    ] = False,
) -> None:
    """Step 1: ask Telegram to send the code and store the phone_code_hash."""

    async def _run() -> None:
        number = phone or state.settings.phone
        if not number:
            raise UsageError(
                "a phone number is required: --phone +39... (or TGPIPE_PHONE in .env)"
            )

        async with connected(require_auth=False) as client:
            if await client.is_user_authorized():
                me = await client.get_me()
                note("session already active: no code sent")
                state.emit(AuthStatus(authorized=True, user=entity(me)))
                return

            sent = await client.send_code_request(number, force_sms=force_sms)
            _save_login_state(number, sent.phone_code_hash)
            state.emit(
                LoginRequest(
                    phone=number,
                    phone_code_hash=sent.phone_code_hash,
                    type=type(sent.type).__name__.replace("SentCodeType", "").lower()
                    if sent.type
                    else None,
                    next_type=type(sent.next_type).__name__.replace("SentCodeType", "").lower()
                    if sent.next_type
                    else None,
                    timeout=getattr(sent, "timeout", None),
                )
            )
            note("code sent. Next: tgpipe auth login --code <code>")

    run(_run())


@app.command("login")
def login(
    code: Annotated[
        str | None,
        typer.Option("--code", envvar="TGPIPE_CODE", help="The code you received ('-' for stdin)"),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", envvar="TGPIPE_PASSWORD", help="2FA password ('-' for stdin)"),
    ] = None,
    phone: Annotated[
        str | None, typer.Option("--phone", envvar="TGPIPE_PHONE")
    ] = None,
    phone_code_hash: Annotated[
        str | None,
        typer.Option("--phone-code-hash", help="If omitted, it is read from step 1"),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-i", help="Classic prompted flow, in one go"),
    ] = False,
    qr: Annotated[
        bool, typer.Option("--qr", help="Log in by QR code: no code to type")
    ] = False,
) -> None:
    """Step 2: complete the login. Without --interactive it never asks anything."""
    if qr and interactive:
        raise UsageError("--qr and --interactive are mutually exclusive")

    if qr:
        run(_login_qr())
    elif interactive:
        run(_login_interactive(phone))
    else:
        run(
            _login_noninteractive(
                code=_read_stdin_value(code),
                password=_read_stdin_value(password),
                phone=phone,
                phone_code_hash=phone_code_hash,
            )
        )


async def _finish(client: Any) -> None:
    _clear_login_state()
    me = await client.get_me()
    state.emit(AuthStatus(authorized=True, user=entity(me),
                          session_path=str(state.settings.session_path)))


async def _login_noninteractive(
    *, code: str | None, password: str | None,
    phone: str | None, phone_code_hash: str | None,
) -> None:
    settings = state.settings
    saved = _load_login_state()
    number = phone or settings.phone or saved.get("phone")
    code_hash = phone_code_hash or saved.get("phone_code_hash")
    code = code or settings.code
    password = password or (
        settings.password.get_secret_value() if settings.password else None
    )

    async with connected(require_auth=False) as client:
        if await client.is_user_authorized():
            await _finish(client)
            return

        if not code:
            raise UsageError(
                "the code is required: --code <code> (or TGPIPE_CODE). "
                "If you have not requested it yet: tgpipe auth login-start --phone +39..."
            )
        if not number or not code_hash:
            raise UsageError(
                "login context missing: run "
                "'tgpipe auth login-start --phone +39...' first, on the same session"
            )

        try:
            await client.sign_in(phone=number, code=code, phone_code_hash=code_hash)
        except errors.SessionPasswordNeededError:
            if not password:
                raise PasswordRequired() from None
            await client.sign_in(password=password)
        await _finish(client)


async def _login_interactive(phone: str | None) -> None:
    async with connected(require_auth=False) as client:
        if await client.is_user_authorized():
            await _finish(client)
            return

        number = phone or state.settings.phone or typer.prompt("Phone number (+39...)")
        sent = await client.send_code_request(number)
        code = typer.prompt("Code received")
        try:
            await client.sign_in(
                phone=number, code=code, phone_code_hash=sent.phone_code_hash
            )
        except errors.SessionPasswordNeededError:
            pw = typer.prompt("2FA password", hide_input=True)
            await client.sign_in(password=pw)
        await _finish(client)


async def _login_qr() -> None:
    async with connected(require_auth=False) as client:
        if await client.is_user_authorized():
            await _finish(client)
            return

        qr_login = await client.qr_login()
        _print_qr(qr_login.url)
        note("scan the QR from Telegram: Settings -> Devices -> Link Desktop Device")
        try:
            await qr_login.wait(timeout=120)
        except errors.SessionPasswordNeededError:
            pw = state.settings.password
            if not pw:
                raise PasswordRequired() from None
            await client.sign_in(password=pw.get_secret_value())
        except TimeoutError:
            raise AuthFailed("the QR expired without being scanned: run the command again") from None
        await _finish(client)


def _print_qr(url: str) -> None:
    """QR on stderr: stdout stays reserved for data."""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(out=sys.stderr, invert=True)
    except Exception:
        note(f"cannot render the QR, open this link from your phone:\n{url}")


@app.command("status")
def status() -> None:
    """Report whether the session is valid. Exit 0 if authenticated, 4 if not."""

    async def _run() -> None:
        async with connected(require_auth=False) as client:
            authorized = await client.is_user_authorized()
            me = await client.get_me() if authorized else None
            state.emit(
                AuthStatus(
                    authorized=authorized,
                    user=entity(me),
                    session_path=str(state.settings.session_path),
                )
            )
            if not authorized:
                raise NotAuthorized()

    run(_run())


@app.command("whoami")
def whoami() -> None:
    """The user behind the current session."""

    async def _run() -> None:
        async with connected() as client:
            state.emit(entity(await client.get_me(), raw=state.raw))

    run(_run())


@app.command("logout")
def logout(
    keep_file: Annotated[
        bool, typer.Option("--keep-file", help="Do not delete the session file")
    ] = False,
) -> None:
    """Terminate the session on Telegram's side and remove the local file."""

    async def _run() -> None:
        settings = state.settings
        async with connected(require_auth=False) as client:
            done = await client.log_out() if await client.is_user_authorized() else False
        if not keep_file and not settings.session_string:
            Path(str(settings.session_path)).unlink(missing_ok=True)
            Path(f"{settings.session_path}-journal").unlink(missing_ok=True)
        _clear_login_state()
        state.emit(Ok(action="logout", details={"revoked": done}))

    run(_run())


@app.command("export-session")
def export_session(
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm: the string grants full access to the account"),
    ] = False,
) -> None:
    """Print a StringSession reusable on another machine or in CI.

    WARNING: this is equivalent to a credential with full account access.
    """
    if not yes:
        raise UsageError(
            "a StringSession grants full access to your Telegram account: "
            "retry with --yes if you understand that. Treat it like a password: "
            "never commit it, never paste it into a chat."
        )

    async def _run() -> None:
        async with connected() as client:
            note("this string is worth full access to the account")
            state.emit(Ok(action="export-session",
                          details={"session_string": StringSession.save(client.session)}))

    run(_run())


@app.command("import-session")
def import_session(
    string: Annotated[
        str,
        typer.Option("--string", envvar="TGPIPE_SESSION_STRING",
                     help="StringSession produced by export-session ('-' for stdin)"),
    ],
) -> None:
    """Write a StringSession into the local session file: zero-interaction login."""

    async def _run() -> None:
        value = _read_stdin_value(string)
        if not value:
            raise UsageError("empty session string")

        settings = state.settings
        source = build_client(settings.model_copy(update={"session_string": None}))
        # open the StringSession and pour it into the local session file
        from telethon import TelegramClient

        temp = TelegramClient(
            StringSession(value),
            settings.api_id,
            settings.api_hash.get_secret_value(),
        )
        await temp.connect()
        try:
            if not await temp.is_user_authorized():
                raise AuthFailed("the StringSession provided is not authenticated")
            auth_key, dc_id = temp.session.auth_key, temp.session.dc_id
            server = temp.session.server_address
            port = temp.session.port
        finally:
            await temp.disconnect()

        source.session.set_dc(dc_id, server, port)
        source.session.auth_key = auth_key
        source.session.save()
        os.chmod(str(settings.session_path), 0o600)

        async with connected() as client:
            state.emit(
                AuthStatus(
                    authorized=True,
                    user=entity(await client.get_me()),
                    session_path=str(settings.session_path),
                )
            )

    run(_run())
