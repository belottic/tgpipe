"""Resumable export of chats and media.

Resuming keeps no separate state that could drift out of sync: it re-reads
the last id already in messages.jsonl and carries on from there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from telethon import TelegramClient, utils

from ..client import connected
from ..errors import UsageError
from ..history import iter_history
from ..models import Ok
from ..output import note
from ..parsing import parse_csv, parse_date
from ..resolve import resolve
from ..runtime import run, state
from ..serialize import entity as ser_entity
from ..serialize import media_kind
from ..serialize import member as ser_member
from ..serialize import message as ser_message

from .media import find_existing, safe_component

app = typer.Typer(no_args_is_help=True)

_KINDS = ("user", "bot", "group", "channel")


def _chat_dir(out: Path, entity_record: Any) -> Path:
    label = safe_component(entity_record.name or "chat")
    return out / f"{label}_{entity_record.id}"


def last_exported_id(path: Path) -> int:
    """Highest id already on disk. Tolerates a last line truncated by Ctrl-C."""
    if not path.exists():
        return 0
    highest = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated line: it will be rewritten
            value = record.get("id")
            if isinstance(value, int):
                highest = max(highest, value)
    return highest


def rewrite_clean(path: Path) -> None:
    """Rewrite the file, dropping any invalid trailing lines."""
    if not path.exists():
        return
    good = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                continue
            good.append(stripped)
    path.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")


async def _export_one(
    client: TelegramClient,
    target: Any,
    out: Path,
    *,
    with_media: bool,
    since: Any,
    until: Any,
    resume: bool,
    participants: bool,
) -> dict[str, Any]:
    record = ser_entity(target)
    directory = _chat_dir(out, record)
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "entity.json").write_text(
        json.dumps(record.model_dump(mode="json", exclude_none=True),
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    messages_path = directory / "messages.jsonl"
    min_id = 0
    if resume:
        rewrite_clean(messages_path)
        min_id = last_exported_id(messages_path)
        if min_id:
            note(f"{record.name}: resuming from id {min_id}")
    elif messages_path.exists():
        messages_path.unlink()

    media_dir = directory / "media"
    exported = downloaded = 0

    with messages_path.open("a", encoding="utf-8") as handle:
        async for msg in iter_history(
            client, target, limit=None, since=since, until=until,
            min_id=min_id, reverse=True,
        ):
            payload = ser_message(msg).model_dump(mode="json", exclude_none=True)

            if with_media and media_kind(msg) is not None:
                media_dir.mkdir(parents=True, exist_ok=True)
                name = getattr(msg.file, "name", None)
                if name:
                    stem = safe_component(name)
                else:
                    # with no file name we need the extension, or Telethon
                    # adds one later and resuming will not recognise the file
                    stem = f"{msg.id}{utils.get_extension(msg) or ''}"
                destination = media_dir / f"{msg.id}_{stem}"
                size = getattr(msg.file, "size", None)
                existing = find_existing(destination, size, media_kind(msg))
                if existing is not None:
                    payload["media_path"] = str(existing)
                else:
                    saved = await client.download_media(msg, file=str(destination))
                    if saved:
                        payload["media_path"] = str(saved)
                        downloaded += 1

            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            exported += 1

    if participants and record.kind in ("group", "channel"):
        members_path = directory / "participants.jsonl"
        try:
            with members_path.open("w", encoding="utf-8") as handle:
                async for user in client.iter_participants(target):
                    record = ser_member(user)
                    handle.write(
                        json.dumps(record.model_dump(mode="json", exclude_none=True),
                                   ensure_ascii=False) + "\n"
                    )
        except Exception as exc:  # channels where members are not readable
            note(f"{record.name}: member list unavailable ({type(exc).__name__})")
            members_path.unlink(missing_ok=True)

    return {
        "chat_id": record.id,
        "chat": record.name,
        "dir": str(directory),
        "messages": exported,
        "media_downloaded": downloaded,
        "resumed_from": min_id or None,
    }


@app.command("chat")
def export_chat(
    chat: Annotated[str, typer.Argument()],
    out: Annotated[Path, typer.Option("--out", "-o", help="Destination directory")] = Path("export"),
    with_media: Annotated[bool, typer.Option("--with-media", help="Download media as well")] = False,
    since: Annotated[str | None, typer.Option("--since")] = None,
    until: Annotated[str | None, typer.Option("--until")] = None,
    resume: Annotated[
        bool, typer.Option("--resume/--restart", help="Resume from where it stopped")
    ] = True,
    participants: Annotated[
        bool, typer.Option("--participants/--no-participants")
    ] = True,
) -> None:
    """Export one chat: entity.json, messages.jsonl, participants.jsonl, media/."""

    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")

    async def _run() -> None:
        async with connected() as client:
            target = await resolve(client, chat)
            summary = await _export_one(
                client, target, out,
                with_media=with_media,
                since=window_start, until=window_end,
                resume=resume, participants=participants,
            )
            state.emit(Ok(action="export chat", details=summary))

    run(_run())


@app.command("all")
def export_all(
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("export"),
    kind: Annotated[str | None, typer.Option("--type", help=", ".join(_KINDS))] = None,
    exclude: Annotated[str | None, typer.Option("--exclude", help="Chats to skip")] = None,
    with_media: Annotated[bool, typer.Option("--with-media")] = False,
    since: Annotated[str | None, typer.Option("--since")] = None,
    until: Annotated[str | None, typer.Option("--until")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max chats to export; 0 = all of them")] = 0,
    resume: Annotated[bool, typer.Option("--resume/--restart")] = True,
    participants: Annotated[bool, typer.Option("--participants/--no-participants")] = True,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
) -> None:
    """Export every chat, one subdirectory each plus a manifest.json."""
    if kind and kind not in _KINDS:
        raise UsageError(f"unknown type: {kind!r} ({', '.join(_KINDS)})")

    window_start = parse_date(since, what="--since")
    window_end = parse_date(until, what="--until")

    async def _run() -> None:
        out.mkdir(parents=True, exist_ok=True)
        manifest_path = out / "manifest.json"
        manifest: dict[str, Any] = {}
        if resume and manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}

        async with connected() as client:
            skip = {utils.get_peer_id(await resolve(client, v)) for v in parse_csv(exclude)}
            summaries = []

            dialogs = []
            async for dlg in client.iter_dialogs(archived=None if include_archived else False):
                chat_id = utils.get_peer_id(dlg.entity)
                if chat_id in skip:
                    continue
                record = ser_entity(dlg.entity)
                if kind and record.kind != kind:
                    continue
                dialogs.append(dlg)
                if limit > 0 and len(dialogs) >= limit:
                    break

            note(f"{len(dialogs)} chats to export")
            for index, dlg in enumerate(dialogs, start=1):
                label = ser_entity(dlg.entity).name
                note(f"[{index}/{len(dialogs)}] {label}")
                try:
                    summary = await _export_one(
                        client, dlg.entity, out,
                        with_media=with_media,
                        since=window_start, until=window_end,
                        resume=resume, participants=participants,
                    )
                except Exception as exc:
                    note(f"  skipped: {type(exc).__name__}: {exc}")
                    summary = {"chat": label, "error": f"{type(exc).__name__}: {exc}"}
                summaries.append(summary)
                manifest[str(summary.get("chat_id") or label)] = summary
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            state.emit_all([Ok(action="export chat", details=s) for s in summaries])

    run(_run())
