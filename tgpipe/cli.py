"""CLI entry point."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer

from . import __version__
from .config import OutputFormat
from .errors import ExitCode, TgpipeError, emit_error, translate
from .runtime import configure_logging, state

app = typer.Typer(
    name="tgpipe",
    help="Non-interactive Telegram client for a personal account. "
    "stdout carries data only: logs and errors go to stderr.",
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=False,
)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_options(
    fmt: Annotated[
        str,
        typer.Option(
            "--format", "-f",
            help="json (default) | jsonl (streaming) | table (human eyes only)",
            envvar="TGPIPE_FORMAT",
        ),
    ] = "json",
    nulls: Annotated[
        bool, typer.Option("--nulls/--no-nulls", help="Include null fields in the output")
    ] = False,
    raw: Annotated[
        bool, typer.Option("--raw", help="Attach the raw Telethon dict under 'raw'")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Verbose logging on stderr")
    ] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Version")
    ] = False,
) -> None:
    if fmt not in ("json", "jsonl", "table"):
        raise typer.BadParameter(f"unknown format: {fmt!r} (json | jsonl | table)")
    state.fmt = fmt  # type: ignore[assignment]
    state.include_nulls = nulls
    state.raw = raw
    state.verbose = verbose
    configure_logging(verbose)


from .commands import account, auth, chats, contacts, export, feed, media, messages  # noqa: E402

app.add_typer(auth.app, name="auth", help="Login, session, identity")
app.add_typer(chats.app, name="chats", help="Chats, groups, channels, members")
app.add_typer(messages.app, name="messages", help="Read, search and send messages")
app.add_typer(media.app, name="media", help="Download photos, videos and documents")
app.add_typer(export.app, name="export", help="Resumable export of chats and media")
app.add_typer(contacts.app, name="contacts", help="Address book, blocks, phone lookup")
app.add_typer(account.app, name="account", help="Active sessions on the account")
feed.register(app)  # digest / inbox / mentions stay top-level


@app.command("schema")
def schema(
    record: Annotated[
        str | None,
        typer.Argument(help="Record name; omitted = all of them"),
    ] = None,
) -> None:
    """Print the JSON Schema of the emitted records: the output contract.

    docs/SCHEMA.md is generated from here, so it cannot drift from the code.
    """
    import json

    from .models import SCHEMA_RECORDS

    if record is None:
        payload = {name: model.model_json_schema() for name, model in SCHEMA_RECORDS.items()}
    else:
        model = SCHEMA_RECORDS.get(record)
        if model is None:
            raise typer.BadParameter(
                f"unknown record: {record!r} ({', '.join(sorted(SCHEMA_RECORDS))})"
            )
        payload = model.model_json_schema()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def allow_negative_ids(command: Any) -> None:
    """Let -1001234567890 be an argument rather than an option.

    Group and channel ids are negative, so Click would read them as short
    options and the id printed by 'chats list' would not be reusable as an
    argument. The setting is not inherited from the parent context, it has to
    be set on every command in the tree. No collision is possible: the short
    options here are all letters, the ids all digits.
    """
    command.ignore_unknown_options = True
    for child in getattr(command, "commands", {}).values():
        allow_negative_ids(child)


def main() -> None:
    try:
        command = typer.main.get_command(app)
        allow_negative_ids(command)
        command()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        error = translate(exc)
        emit_error(error)
        sys.exit(int(error.exit_code))


if __name__ == "__main__":
    main()
