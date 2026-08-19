# Output schema

Generated from `tgpipe/models.py` by `uv run python tools/gen_schema.py` —
do not edit by hand.

The full JSON Schema is always available at runtime:

```bash
tgpipe schema            # every record
tgpipe schema message    # just one
```

## Common rules

- Null fields are **omitted** from the output. Pass `--nulls` to include them.
- Dates are ISO 8601 in UTC (`2026-08-18T10:00:00Z`).
- Group and channel ids are in marked form (`-100...`), exactly as Telegram
  accepts them: they can be passed straight back as a `CHAT` argument.
- With `--raw` every read record gains a `raw` field holding the raw Telethon
  dict, for whatever the normalised schema does not cover.
- `--format json` produces an array (or an object for single-result commands),
  `--format jsonl` one line per record.

## `entity`

A user, bot, group or channel.

| field | type | required |
| --- | --- | --- |
| `kind` | `'user' \| 'bot' \| 'group' \| 'channel' \| 'unknown'` | yes |
| `id` | `integer` | yes |
| `name` | `string` | no |
| `username` | `string` | no |
| `title` | `string` | no |
| `first_name` | `string` | no |
| `last_name` | `string` | no |
| `phone` | `string` | no |
| `is_self` | `boolean` | no |
| `is_contact` | `boolean` | no |
| `is_deleted` | `boolean` | no |
| `verified` | `boolean` | no |
| `scam` | `boolean` | no |
| `restricted` | `boolean` | no |
| `megagroup` | `boolean` | no |
| `broadcast` | `boolean` | no |
| `participants_count` | `integer` | no |
| `about` | `string` | no |

## `message`

| field | type | required |
| --- | --- | --- |
| `id` | `integer` | yes |
| `chat_id` | `integer` | yes |
| `date` | `string` | yes |
| `out` | `boolean` | no |
| `text` | `string` | no |
| `sender` | `Entity` | no |
| `chat` | `Entity` | no |
| `edit_date` | `string` | no |
| `reply_to_msg_id` | `integer` | no |
| `forward` | `Forward` | no |
| `media` | `MediaInfo` | no |
| `reactions` | `Reaction[]` | no |
| `views` | `integer` | no |
| `forwards` | `integer` | no |
| `pinned` | `boolean` | no |
| `silent` | `boolean` | no |
| `post` | `boolean` | no |
| `grouped_id` | `integer` | no |
| `action` | `string` | no |

## `dialog`

| field | type | required |
| --- | --- | --- |
| `entity` | `Entity` | yes |
| `unread_count` | `integer` | no |
| `unread_mentions` | `integer` | no |
| `pinned` | `boolean` | no |
| `archived` | `boolean` | no |
| `folder_id` | `integer` | no |
| `last_message` | `Message` | no |

## `member`

A participant: the user plus whatever only holds inside this chat.

`rank` is the custom title Telegram shows next to the name (e.g.
"Moderator"): it lives on the participant, not on the user, so it could
never appear in an `entity` record.

| field | type | required |
| --- | --- | --- |
| `entity` | `Entity` | yes |
| `role` | `'creator' \| 'admin' \| 'member' \| 'restricted' \| 'banned' \| 'left'` | no |
| `rank` | `string` | no |
| `joined_date` | `string` | no |
| `inviter_id` | `integer` | no |
| `promoted_by` | `integer` | no |

## `inbox_entry`

| field | type | required |
| --- | --- | --- |
| `entity` | `Entity` | yes |
| `unread_count` | `integer` | no |
| `unread_mentions` | `integer` | no |
| `archived` | `boolean` | no |
| `last_messages` | `Message[]` | no |

## `download`

| field | type | required |
| --- | --- | --- |
| `message_id` | `integer` | yes |
| `chat_id` | `integer` | yes |
| `path` | `string` | yes |
| `size` | `integer` | no |
| `mime_type` | `string` | no |
| `skipped` | `boolean` | no |

## `contact`

| field | type | required |
| --- | --- | --- |
| `entity` | `Entity` | yes |
| `mutual` | `boolean` | no |
| `blocked` | `boolean` | no |

## `auth_session`

| field | type | required |
| --- | --- | --- |
| `hash` | `integer` | yes |
| `current` | `boolean` | no |
| `device_model` | `string` | no |
| `platform` | `string` | no |
| `system_version` | `string` | no |
| `app_name` | `string` | no |
| `app_version` | `string` | no |
| `ip` | `string` | no |
| `country` | `string` | no |
| `region` | `string` | no |
| `date_created` | `string` | no |
| `date_active` | `string` | no |
| `official_app` | `boolean` | no |
| `password_pending` | `boolean` | no |

## `draft`

| field | type | required |
| --- | --- | --- |
| `entity` | `Entity` | no |
| `text` | `string` | no |
| `date` | `string` | no |
| `reply_to_msg_id` | `integer` | no |

## `folder`

| field | type | required |
| --- | --- | --- |
| `id` | `integer` | yes |
| `title` | `string` | no |
| `emoticon` | `string` | no |
| `include_peers` | `integer[]` | no |
| `exclude_peers` | `integer[]` | no |
| `pinned_peers` | `integer[]` | no |

## `login_request`

| field | type | required |
| --- | --- | --- |
| `phone` | `string` | yes |
| `phone_code_hash` | `string` | yes |
| `type` | `string` | no |
| `next_type` | `string` | no |
| `timeout` | `integer` | no |

## `auth_status`

| field | type | required |
| --- | --- | --- |
| `authorized` | `boolean` | yes |
| `user` | `Entity` | no |
| `session_path` | `string` | no |

## `ok`

Outcome of a command with nothing else to return.

| field | type | required |
| --- | --- | --- |
| `ok` | `boolean` | no |
| `action` | `string` | no |
| `details` | `object` | no |
