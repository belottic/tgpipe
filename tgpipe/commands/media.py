"""Media downloads, in bulk and resumable."""

from __future__ import annotations

import glob
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from telethon import utils

from ..client import connected
from ..errors import UsageError
from ..history import iter_history, media_filter
from ..parsing import parse_csv, parse_date, parse_ids, parse_size
from ..resolve import resolve
from ..runtime import run, state
from ..serialize import download as ser_download
from ..serialize import media_kind

app = typer.Typer(no_args_is_help=True)

DEFAULT_TEMPLATE = "{chat}/{date}_{id}{ext}"
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_component(value: str, fallback: str = "_") -> str:
    """File names come from Telegram: they are not trusted.

    No separators, no directory traversal, no reserved names.
    """
    cleaned = _UNSAFE.sub("_", (value or "").strip()).strip(". ")
    cleaned = cleaned.replace("..", "_")
    return (cleaned or fallback)[:120]


def build_path(
    template: str, out: Path, *, chat: str, msg_id: int, date: datetime | None,
    name: str | None, kind: str | None, ext_hint: str | None = None,
) -> Path:
    stem, ext = ("", "")
    if name:
        safe_name = safe_component(name)
        stem, _, suffix = safe_name.rpartition(".")
        if stem:
            ext = f".{suffix}"
        else:
            stem, ext = safe_name, ""
    if not ext and ext_hint:
        # photos have no file name: with no extension Telethon adds one
        # downstream and the "already downloaded" check would miss it
        ext = ext_hint if ext_hint.startswith(".") else f".{ext_hint}"
    fields = {
        "chat": safe_component(chat, "chat"),
        "id": msg_id,
        "date": date.strftime("%Y-%m-%d") if date else "no-date",
        "datetime": date.strftime("%Y-%m-%dT%H%M%S") if date else "no-date",
        "year": date.strftime("%Y") if date else "0000",
        "month": date.strftime("%m") if date else "00",
        "name": stem or f"media_{msg_id}",
        "ext": ext,
        "type": kind or "media",
    }
    try:
        rendered = template.format(**fields)
    except KeyError as exc:
        raise UsageError(
            f"unknown placeholder in the template: {exc}. "
            f"Available: {', '.join('{' + k + '}' for k in fields)}"
        ) from None

    parts = [safe_component(p) for p in Path(rendered).parts if p not in ("/", "..")]
    if not parts:
        raise UsageError(f"template {template!r} produces an empty path")
    return out.joinpath(*parts)


# for these the declared size is not the size of the bytes saved
_SIZE_UNRELIABLE = {"photo", "webpage", "sticker"}


def find_existing(path: Path, size: int | None, kind: str | None = None) -> Path | None:
    """The already-downloaded file, if there is one.

    Two Telegram asymmetries make this less obvious than it looks.

    The extension is chosen by Telethon at download time and cannot be
    predicted up front (a web preview saves the photo it contains, and the
    media type does not say so): so we look at what is actually sitting
    there, matching on the stem.

    And for photos `file.size` reports the largest of the progressive
    variants, which is not what ends up on disk: demanding an exact match
    would mean never recognising the file and re-downloading it on every run,
    which is precisely what --skip-existing and --resume exist to avoid. For
    those types a non-empty file is enough.
    """
    candidates: list[Path] = [path] if path.is_file() else []
    parent = path.parent
    if parent.is_dir():
        pattern = glob.escape(path.stem) + ".*"
        candidates += sorted(c for c in parent.glob(pattern) if c.is_file())

    lenient = size is None or (kind in _SIZE_UNRELIABLE)
    for candidate in candidates:
        actual = candidate.stat().st_size
        if actual == size or (lenient and actual > 0):
            return candidate
    return None


@app.command("download")
def download(
    chat: Annotated[str, typer.Argument()],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Destination directory")] = None,
    ids: Annotated[str | None, typer.Option("--ids", help="'1,2,5-8'")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="0 = no limit")] = 0,
    types_: Annotated[
        str | None, typer.Option("--types", help="photo,video,document,voice,audio,gif")
    ] = None,
    since: Annotated[str | None, typer.Option("--since")] = None,
    until: Annotated[str | None, typer.Option("--until")] = None,
    min_size: Annotated[str | None, typer.Option("--min-size", help="e.g. 100k")] = None,
    max_size: Annotated[str | None, typer.Option("--max-size", help="e.g. 50M")] = None,
    template: Annotated[
        str, typer.Option("--name-template", help=f"default: {DEFAULT_TEMPLATE}")
    ] = DEFAULT_TEMPLATE,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing/--overwrite",
                     help="Skip files already present with the same size"),
    ] = True,
) -> None:
    """Download a chat's media. Emits one record per file: interruptible, and
    resumable by re-running the same command."""
    wanted = {t.lower() for t in parse_csv(types_)}
    lower, upper = parse_size(min_size), parse_size(max_size)
    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")
    wanted_ids = parse_ids(ids) or None
    # with a single type we let Telegram filter: far more efficient
    server_filter = media_filter(next(iter(wanted))) if len(wanted) == 1 else None

    async def _run() -> None:
        target_dir = out or state.settings.download_dir
        async with connected() as client:
            ent = await resolve(client, chat)
            chat_id = utils.get_peer_id(ent)
            chat_name = utils.get_display_name(ent) or str(chat_id)

            async def _stream():
                count = 0
                async for msg in iter_history(
                    client, ent,
                    limit=None,
                    since=window_start, until=window_end,
                    ids=wanted_ids, filter=server_filter,
                ):
                    kind = media_kind(msg)
                    if kind is None:
                        continue
                    if wanted and kind not in wanted:
                        continue
                    size = getattr(msg.file, "size", None)
                    if lower is not None and (size or 0) < lower:
                        continue
                    if upper is not None and (size or 0) > upper:
                        continue

                    path = build_path(
                        template, target_dir, chat=chat_name, msg_id=msg.id,
                        date=msg.date, name=getattr(msg.file, "name", None), kind=kind,
                        ext_hint=utils.get_extension(msg),
                    )
                    mime = getattr(msg.file, "mime_type", None)

                    existing = find_existing(path, size, kind) if skip_existing else None
                    if existing is not None:
                        yield ser_download(msg.id, chat_id, str(existing),
                                           existing.stat().st_size, mime, skipped=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        saved = await client.download_media(msg, file=str(path))
                        if saved is None:
                            continue
                        actual = Path(saved)
                        yield ser_download(msg.id, chat_id, str(actual),
                                           actual.stat().st_size if actual.exists() else None,
                                           mime)
                    count += 1
                    if limit > 0 and count >= limit:
                        return

            await state.emit_stream(_stream())

    run(_run())


@app.command("download-message")
def download_message(
    chat: Annotated[str, typer.Argument()],
    message_id: Annotated[int, typer.Argument()],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="File or directory")] = None,
) -> None:
    """Download the media of a single message."""

    async def _run() -> None:
        async with connected() as client:
            ent = await resolve(client, chat)
            messages = await client.get_messages(ent, ids=[message_id])
            msg: Any = messages[0] if messages else None
            if msg is None:
                raise UsageError(f"message {message_id} not found in {chat!r}")
            if media_kind(msg) is None:
                raise UsageError(f"message {message_id} carries no media")

            destination = out or state.settings.download_dir
            if destination.suffix == "":
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)

            saved = await client.download_media(msg, file=str(destination))
            path = Path(saved) if saved else None
            state.emit(
                ser_download(
                    msg.id, utils.get_peer_id(ent), str(path) if path else "",
                    path.stat().st_size if path and path.exists() else None,
                    getattr(msg.file, "mime_type", None),
                )
            )

    run(_run())
