"""Pydantic models for the records the CLI emits.

This module IS the output contract: docs/SCHEMA.md is generated from it
(`tgpipe schema`), so documentation and code cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

EntityKind = Literal["user", "bot", "group", "channel", "unknown"]

MediaKind = Literal[
    "photo", "video", "gif", "audio", "voice", "sticker", "document",
    "webpage", "contact", "geo", "poll", "dice", "invoice", "game", "unknown",
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64")

    raw: dict[str, Any] | None = None


class Entity(Record):
    """A user, bot, group or channel."""

    kind: EntityKind
    id: int
    name: str | None = None
    username: str | None = None
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_self: bool = False
    is_contact: bool | None = None
    is_deleted: bool | None = None
    verified: bool | None = None
    scam: bool | None = None
    restricted: bool | None = None
    megagroup: bool | None = None
    broadcast: bool | None = None
    participants_count: int | None = None
    about: str | None = None


class MediaInfo(Record):
    type: MediaKind
    mime_type: str | None = None
    file_name: str | None = None
    size: int | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    has_spoiler: bool | None = None


class Reaction(Record):
    emoji: str | None = None
    custom_emoji_id: int | None = None
    count: int = 0
    chosen: bool = False


class Forward(Record):
    from_id: int | None = None
    from_name: str | None = None
    date: datetime | None = None
    channel_post: int | None = None


class Message(Record):
    id: int
    chat_id: int
    date: datetime
    out: bool = False
    text: str | None = None
    sender: Entity | None = None
    chat: Entity | None = None
    edit_date: datetime | None = None
    reply_to_msg_id: int | None = None
    forward: Forward | None = None
    media: MediaInfo | None = None
    reactions: list[Reaction] = []
    views: int | None = None
    forwards: int | None = None
    pinned: bool = False
    silent: bool = False
    post: bool = False
    grouped_id: int | None = None
    action: str | None = None


class Dialog(Record):
    entity: Entity
    unread_count: int = 0
    unread_mentions: int = 0
    pinned: bool = False
    archived: bool = False
    folder_id: int | None = None
    last_message: Message | None = None


class InboxEntry(Record):
    entity: Entity
    unread_count: int = 0
    unread_mentions: int = 0
    archived: bool = False
    last_messages: list[Message] = []


MemberRole = Literal["creator", "admin", "member", "restricted", "banned", "left"]


class Member(Record):
    """A participant: the user plus whatever only holds inside this chat.

    `rank` is the custom title Telegram shows next to the name (e.g.
    "Moderator"): it lives on the participant, not on the user, so it could
    never appear in an `entity` record.
    """

    entity: Entity
    role: MemberRole = "member"
    rank: str | None = None
    joined_date: datetime | None = None
    inviter_id: int | None = None
    promoted_by: int | None = None


class Download(Record):
    message_id: int
    chat_id: int
    path: str
    size: int | None = None
    mime_type: str | None = None
    skipped: bool = False


class Contact(Record):
    entity: Entity
    mutual: bool | None = None
    blocked: bool | None = None


class AuthSession(Record):
    hash: int
    current: bool = False
    device_model: str | None = None
    platform: str | None = None
    system_version: str | None = None
    app_name: str | None = None
    app_version: str | None = None
    ip: str | None = None
    country: str | None = None
    region: str | None = None
    date_created: datetime | None = None
    date_active: datetime | None = None
    official_app: bool | None = None
    password_pending: bool | None = None


class Draft(Record):
    entity: Entity | None = None
    text: str | None = None
    date: datetime | None = None
    reply_to_msg_id: int | None = None


class Folder(Record):
    id: int
    title: str | None = None
    emoticon: str | None = None
    include_peers: list[int] = []
    exclude_peers: list[int] = []
    pinned_peers: list[int] = []


class LoginRequest(Record):
    phone: str
    phone_code_hash: str
    type: str | None = None
    next_type: str | None = None
    timeout: int | None = None


class AuthStatus(Record):
    authorized: bool
    user: Entity | None = None
    session_path: str | None = None


class Ok(Record):
    """Outcome of a command with nothing else to return."""

    ok: bool = True
    action: str | None = None
    details: dict[str, Any] | None = None


SCHEMA_RECORDS: dict[str, type[Record]] = {
    "entity": Entity,
    "message": Message,
    "dialog": Dialog,
    "member": Member,
    "inbox_entry": InboxEntry,
    "download": Download,
    "contact": Contact,
    "auth_session": AuthSession,
    "draft": Draft,
    "folder": Folder,
    "login_request": LoginRequest,
    "auth_status": AuthStatus,
    "ok": Ok,
}
