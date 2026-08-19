"""Telethon objects -> models from models.py.

All knowledge of the TL schema lives here: commands must never touch raw
Telethon attributes.
"""

from __future__ import annotations

from typing import Any

from telethon import utils
from telethon.tl import types

from .models import (
    AuthSession,
    Member,
    Contact,
    Dialog,
    Download,
    Draft,
    Entity,
    Folder,
    Forward,
    MediaInfo,
    Message,
    Reaction,
)


def _raw(obj: Any, include: bool) -> dict[str, Any] | None:
    if not include:
        return None
    try:
        return obj.to_dict()
    except Exception:
        return None


def _kind(obj: Any) -> str:
    if isinstance(obj, types.User):
        return "bot" if obj.bot else "user"
    if isinstance(obj, (types.Chat, types.ChatForbidden)):
        return "group"
    if isinstance(obj, (types.Channel, types.ChannelForbidden)):
        return "group" if getattr(obj, "megagroup", False) else "channel"
    return "unknown"


def entity(obj: Any, *, raw: bool = False) -> Entity | None:
    """Serialise User / Chat / Channel. Also accepts the *Full objects."""
    if obj is None:
        return None

    # get_entity can return a Full object: drill down to the useful part
    for attr in ("user", "chat", "channel"):
        inner = getattr(obj, attr, None)
        if inner is not None and isinstance(inner, (types.User, types.Chat, types.Channel)):
            obj = inner
            break

    try:
        peer_id = utils.get_peer_id(obj)
    except Exception:
        peer_id = getattr(obj, "id", 0)

    kind = _kind(obj)
    is_user = kind in ("user", "bot")
    return Entity(
        kind=kind,  # type: ignore[arg-type]
        id=peer_id,
        name=utils.get_display_name(obj) or None,
        username=getattr(obj, "username", None),
        title=None if is_user else getattr(obj, "title", None),
        first_name=getattr(obj, "first_name", None) if is_user else None,
        last_name=getattr(obj, "last_name", None) if is_user else None,
        phone=getattr(obj, "phone", None) if is_user else None,
        is_self=bool(getattr(obj, "is_self", False)),
        is_contact=getattr(obj, "contact", None) if is_user else None,
        is_deleted=getattr(obj, "deleted", None) if is_user else None,
        verified=getattr(obj, "verified", None),
        scam=getattr(obj, "scam", None),
        restricted=getattr(obj, "restricted", None),
        megagroup=getattr(obj, "megagroup", None),
        broadcast=getattr(obj, "broadcast", None),
        participants_count=getattr(obj, "participants_count", None),
        raw=_raw(obj, raw),
    )


def entity_full(full: Any, base: Any, *, raw: bool = False) -> Entity | None:
    """Like entity(), enriched with the fields only the *Full carries."""
    result = entity(base, raw=raw)
    if result is None:
        return None
    inner = getattr(full, "full_chat", None) or getattr(full, "full_user", None)
    if inner is not None:
        result.about = getattr(inner, "about", None)
        count = getattr(inner, "participants_count", None)
        if count is not None:
            result.participants_count = count
    return result


_MEDIA_PROBES = (
    ("voice", "voice"),
    ("video_note", "video"),
    ("gif", "gif"),
    ("sticker", "sticker"),
    ("photo", "photo"),
    ("video", "video"),
    ("audio", "audio"),
    ("contact", "contact"),
    ("geo", "geo"),
    ("poll", "poll"),
    ("dice", "dice"),
    ("invoice", "invoice"),
    ("game", "game"),
    ("web_preview", "webpage"),
    ("document", "document"),
)


def media_kind(msg: types.Message) -> str | None:
    for attr, kind in _MEDIA_PROBES:
        if getattr(msg, attr, None):
            return kind
    return "unknown" if getattr(msg, "media", None) else None


def media(msg: types.Message) -> MediaInfo | None:
    kind = media_kind(msg)
    if kind is None:
        return None
    file = getattr(msg, "file", None)
    return MediaInfo(
        type=kind,  # type: ignore[arg-type]
        mime_type=getattr(file, "mime_type", None),
        file_name=getattr(file, "name", None),
        size=getattr(file, "size", None),
        duration=getattr(file, "duration", None),
        width=getattr(file, "width", None),
        height=getattr(file, "height", None),
        has_spoiler=getattr(getattr(msg, "media", None), "spoiler", None),
    )


def _reactions(msg: types.Message) -> list[Reaction]:
    results = getattr(getattr(msg, "reactions", None), "results", None) or []
    out = []
    for item in results:
        reaction = getattr(item, "reaction", None)
        out.append(
            Reaction(
                emoji=getattr(reaction, "emoticon", None),
                custom_emoji_id=getattr(reaction, "document_id", None),
                count=getattr(item, "count", 0) or 0,
                chosen=getattr(item, "chosen_order", None) is not None,
            )
        )
    return out


def _forward(msg: types.Message) -> Forward | None:
    fwd = getattr(msg, "fwd_from", None)
    if fwd is None:
        return None
    from_id = getattr(fwd, "from_id", None)
    return Forward(
        from_id=utils.get_peer_id(from_id) if from_id else None,
        from_name=getattr(fwd, "from_name", None),
        date=getattr(fwd, "date", None),
        channel_post=getattr(fwd, "channel_post", None),
    )


def _text(msg: types.Message) -> str | None:
    """.text rebuilds the markdown but depends on the client: without one it
    falls back to the raw field."""
    try:
        formatted = msg.text
    except Exception:
        formatted = None
    return formatted or getattr(msg, "message", None) or None


def _sender(msg: types.Message, raw: bool) -> Entity | None:
    sender = getattr(msg, "sender", None)
    if sender is not None:
        return entity(sender, raw=raw)
    sender_id = getattr(msg, "sender_id", None)
    if sender_id is None:
        return None
    # without the full object return at least the id, typed by its sign
    kind = "user" if sender_id > 0 else "channel"
    return Entity(kind=kind, id=sender_id)  # type: ignore[arg-type]


def message(
    msg: types.Message,
    *,
    chat: Entity | None = None,
    raw: bool = False,
) -> Message:
    action = getattr(msg, "action", None)
    return Message(
        id=msg.id,
        chat_id=utils.get_peer_id(msg.peer_id) if msg.peer_id else 0,
        date=msg.date,
        out=bool(getattr(msg, "out", False)),
        text=_text(msg),
        sender=_sender(msg, raw),
        chat=chat,
        edit_date=getattr(msg, "edit_date", None),
        reply_to_msg_id=getattr(getattr(msg, "reply_to", None), "reply_to_msg_id", None),
        forward=_forward(msg),
        media=media(msg),
        reactions=_reactions(msg),
        views=getattr(msg, "views", None),
        forwards=getattr(msg, "forwards", None),
        pinned=bool(getattr(msg, "pinned", False)),
        silent=bool(getattr(msg, "silent", False)),
        post=bool(getattr(msg, "post", False)),
        grouped_id=getattr(msg, "grouped_id", None),
        action=type(action).__name__ if action is not None else None,
        raw=_raw(msg, raw),
    )


def dialog(dlg: Any, *, raw: bool = False) -> Dialog:
    ent = entity(dlg.entity, raw=raw)
    last = dlg.message
    return Dialog(
        entity=ent,  # type: ignore[arg-type]
        unread_count=getattr(dlg, "unread_count", 0) or 0,
        unread_mentions=getattr(dlg, "unread_mentions_count", 0) or 0,
        pinned=bool(getattr(dlg, "pinned", False)),
        archived=bool(getattr(dlg, "archived", False)),
        folder_id=getattr(dlg, "folder_id", None),
        last_message=message(last) if last else None,
    )


_ROLES = {
    "ChannelParticipantCreator": "creator",
    "ChatParticipantCreator": "creator",
    "ChannelParticipantAdmin": "admin",
    "ChatParticipantAdmin": "admin",
    "ChannelParticipantBanned": "banned",
    "ChannelParticipantLeft": "left",
}


def member(user: Any, *, raw: bool = False) -> Member:
    """User + participant data.

    Telethon's iter_participants attaches the participant to the user as
    `.participant`: that is where the role and the custom title live.
    """
    participant = getattr(user, "participant", None)
    role = _ROLES.get(type(participant).__name__, "member")
    if role == "banned" and not getattr(participant, "left", False):
        role = "restricted"
    return Member(
        entity=entity(user, raw=raw),  # type: ignore[arg-type]
        role=role,  # type: ignore[arg-type]
        rank=getattr(participant, "rank", None) or None,
        joined_date=getattr(participant, "date", None),
        inviter_id=getattr(participant, "inviter_id", None),
        promoted_by=getattr(participant, "promoted_by", None),
        raw=_raw(participant, raw),
    )


def download(msg_id: int, chat_id: int, path: str, size: int | None,
             mime_type: str | None, skipped: bool = False) -> Download:
    return Download(
        message_id=msg_id, chat_id=chat_id, path=path,
        size=size, mime_type=mime_type, skipped=skipped,
    )


def contact(user: types.User, *, blocked: bool | None = None, raw: bool = False) -> Contact:
    return Contact(
        entity=entity(user, raw=raw),  # type: ignore[arg-type]
        mutual=getattr(user, "mutual_contact", None),
        blocked=blocked,
    )


def auth_session(auth: types.Authorization, *, raw: bool = False) -> AuthSession:
    return AuthSession(
        hash=auth.hash,
        current=bool(auth.current),
        device_model=auth.device_model,
        platform=auth.platform,
        system_version=auth.system_version,
        app_name=auth.app_name,
        app_version=auth.app_version,
        ip=auth.ip,
        country=auth.country,
        region=auth.region,
        date_created=auth.date_created,
        date_active=auth.date_active,
        official_app=auth.official_app,
        password_pending=auth.password_pending,
        raw=_raw(auth, raw),
    )


def draft(dlg_entity: Any, dft: Any, *, raw: bool = False) -> Draft:
    reply_to = getattr(dft, "reply_to", None)
    return Draft(
        entity=entity(dlg_entity, raw=raw),
        text=getattr(dft, "message", None) or getattr(dft, "text", None) or None,
        date=getattr(dft, "date", None),
        reply_to_msg_id=getattr(reply_to, "reply_to_msg_id", None),
        raw=_raw(dft, raw),
    )


def _peer_ids(peers: Any) -> list[int]:
    out = []
    for peer in peers or []:
        try:
            out.append(utils.get_peer_id(peer))
        except Exception:
            continue
    return out


def folder(flt: Any, *, raw: bool = False) -> Folder:
    title = getattr(flt, "title", None)
    return Folder(
        id=getattr(flt, "id", 0),
        title=getattr(title, "text", None) if title is not None and not isinstance(title, str) else title,
        emoticon=getattr(flt, "emoticon", None),
        include_peers=_peer_ids(getattr(flt, "include_peers", None)),
        exclude_peers=_peer_ids(getattr(flt, "exclude_peers", None)),
        pinned_peers=_peer_ids(getattr(flt, "pinned_peers", None)),
        raw=_raw(flt, raw),
    )
