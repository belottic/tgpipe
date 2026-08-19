---
name: tgpipe
description: Read and write Telegram through the user's own account with the tgpipe CLI (Telethon). Use it to catch up on unread chats, summarise what arrived, search or export message history, download media, send/reply/forward messages, and inspect group members, contacts and account sessions.
---

# tgpipe

Non-interactive Telegram CLI authenticated as the user's **personal account**
(not a bot). Installed on PATH, works from any directory:

```bash
tgpipe <group> <command> [options]
```

Credentials and session live in the project root and are found from anywhere.
Files the commands *produce* (`--out`, downloads, exports) are relative to the
current directory. `TGPIPE_HOME` overrides where credentials are looked up.

## Pick the right command

| The user wants | Run this | Not this |
| --- | --- | --- |
| "What did I miss?" | `inbox --preview 3` | `chats list` + N × `history` |
| "Summarise the last day" | `digest --since -24h --format jsonl` | one `history` per chat |
| "Did anyone mention me?" | `mentions --since -7d` | `search` for their name |
| "Find where X was discussed" | `messages search "X"` (no `--chat` = everywhere) | fetching whole histories |
| "What's in this chat" | `messages history CHAT --limit N` | `--all` on a big chat |
| "Who is in this group" | `chats members CHAT --limit 0` | `chats info` (counts only) |
| "Back up this chat" | `export chat CHAT --out DIR --with-media` | `history` + `media download` |
| "Save these photos" | `media download CHAT --types photo` | downloading one by one |

`inbox` and `digest` are one round-trip each and cost far less than fanning out
over chats. Reach for them first.

## Before you write

Sending, editing and deleting affect other people and cannot be undone beyond
Telegram's own limits. Four rules, in order of importance:

1. **Prefer the numeric id over the title.** Take it from `chats list` or from
   any record's `chat_id`. A bare title is resolved against the user's chats
   first, but a public entity with the same name can still win if no chat
   matches — which is how a message ends up in the wrong place.
2. **`--dry-run` first whenever the chat came from a title**, a search result,
   or anything the user typed loosely. It prints the resolved chat and the
   exact payload without sending.
3. **Confirm with the user** before messaging third parties, leaving groups,
   deleting messages, or terminating sessions. Their asking you to draft
   something is not the same as asking you to send it.
4. **Never pass `--yes` on your own initiative.** It exists on `chats leave`,
   `messages delete` above 10 ids, `account terminate-*` and
   `auth export-session` precisely so a human decides.

If a title is ambiguous the command exits `3` and lists candidate ids and
names — pick from that list, do not guess.

## Recipes

**Catch up and summarise**
```bash
tgpipe inbox --preview 5 > inbox.json                    # overview first
tgpipe --format jsonl digest --since -24h --incoming-only > day.jsonl
```
Every `digest` line carries its own `chat` object, so the stream can be read
line by line and handed to a model without extra context. A busy account can
produce ~1000 messages a day: use `--limit-per-chat`, `--chats`, `--exclude`
or `--type channel` to narrow before you widen.

**Read a long history without blowing up context**
```bash
tgpipe --format jsonl messages history CHAT --limit 200 > page1.jsonl
tail -1 page1.jsonl | jq .id                               # feed as --offset-id
tgpipe --format jsonl messages history CHAT --limit 200 --offset-id <id> > page2.jsonl
```
Pagination uses Telegram's own `offset_id`. There is no separate cursor.

**Reply to the last message from a specific person**
```bash
tgpipe chats members CHAT --query "Name" | jq -r '.[0].entity.id'
tgpipe messages history CHAT --from-user <id> --limit 1 | jq -r '.[0].id'
tgpipe messages send CHAT --text "..." --reply-to <message id>
```

**Back up a chat, resumably**
```bash
tgpipe export chat CHAT --out ./backup --with-media
```
Interrupted halfway, the *same command* resumes: it re-reads the last id from
`messages.jsonl` and skips media already on disk. Produces `entity.json`,
`messages.jsonl`, `participants.jsonl`, `media/`.

**Send text that contains quotes, newlines or markdown**
```bash
tgpipe messages send CHAT --stdin < body.md
tgpipe messages send CHAT --text-file body.md --parse-mode md
```

## Output contract

Global options go **before** the command group:
`--format json|jsonl|table`, `--nulls`, `--raw`, `--verbose`.

```bash
tgpipe --format jsonl messages history me --limit 500
```

- `json` (default): an array for lists, an object for single results.
- `jsonl`: one record per line. **Use it above ~200 records** — it streams,
  survives interruption, and each line stands alone.
- `table`: for human eyes only. **Never parse it.**
- Null fields are omitted; `--nulls` keeps them.
- Dates are ISO 8601 UTC. Group and channel ids are in marked `-100...` form
  and can be passed straight back as `CHAT`, minus sign and all.
- `--raw` attaches the raw Telethon dict when the normalised schema is not
  enough. Full schema: `tgpipe schema [record]` or `docs/SCHEMA.md`.
- **stdout carries data only.** Progress, warnings and errors go to stderr, so
  `tgpipe ... > file.json` is always valid JSON.

## When something fails

Errors arrive on stderr as
`{"error": {"type": ..., "message": ..., "details": ...}}`.

| exit | type | what to do |
| --- | --- | --- |
| 2 | `config`, `usage` | fix arguments, or the `.env` if `config` |
| 3 | `entity_not_found` | chat unresolved; use an id from `chats list`, or pick from `details.matches` |
| 4 | `not_authorized`, `password_required`, `auth_failed` | the session is gone or the login is incomplete. See **Recovering a login** below — you can do most of it yourself. |
| 5 | `flood_wait` | Telegram imposed a wait of `details.seconds`. Report it; do not hammer. |
| 6 | `forbidden` | missing rights or privacy settings. Not workable around — say so. |
| 1 | `session_busy` | another tgpipe process holds the session. Wait, or give this one its own via `TGPIPE_SESSION_PATH`. |

## Recovering a login

You cannot log in entirely on your own: Telegram sends the code out of band, to
the user's phone or to their Telegram app. Only they can read it. Everything
around that step, though, is yours to do — so do it, and ask for the one thing
you cannot get.

**First, work out which failure you are looking at.** Run `tgpipe auth status`
and read the error `type`, not just the exit code:

| type | meaning | what to do |
| --- | --- | --- |
| `config` | no `api_id`/`api_hash` | the user must create them at my.telegram.org and fill in `.env`. Nothing else will work until then. |
| `not_authorized` | credentials fine, no valid session | run the two-step login below |
| `auth_failed` | the code or password was wrong, or the code expired | start over from `login-start`; a code is single-use |
| `password_required` | the code worked, two-step verification is on | ask the user for their 2FA password |
| `flood_wait` | too many attempts | stop. Report `details.seconds` and wait. |

**The two-step login.** Step one is safe for you to run unprompted — it only
asks Telegram to send a code:

```bash
tgpipe auth login-start --phone +39...        # phone can come from TGPIPE_PHONE
```

It prints where the code went (`"type": "app"` means inside Telegram on another
device, `"sms"` means a text message). Tell the user which, then ask them for
the code and finish:

```bash
tgpipe auth login --code 12345
tgpipe auth status                            # confirm: authorized true
```

If that returns `password_required`, ask for the 2FA password and repeat with
`tgpipe auth login --code 12345 --password '…'`. Note the code from step one is
still valid at this point; do not request a new one.

**Rules for this flow**

- **Never run `login-start` more than once per attempt.** Each call sends a new
  code and invalidates the previous one; repeated calls earn a `flood_wait`
  that locks the user out for minutes or hours.
- **Never guess a code or a password**, and never retry the same code after
  `auth_failed` — it is single-use and expires in minutes. Go back to
  `login-start`.
- **Never run `tgpipe auth logout`** to "reset" a broken state. It destroys a
  session that may still be recoverable and forces a fresh login.
- **Do not echo the code or the password** into a file, a log, or a message.
  Pass them as arguments, or via `TGPIPE_CODE` / `TGPIPE_PASSWORD`, and let
  them go.
- `tgpipe auth export-session` prints a credential equivalent to full account
  access. Never run it to "back things up", never paste its output anywhere.
  It exists for the user to move a session deliberately.
- On a machine where a session already exists elsewhere,
  `tgpipe auth import-session --string …` or `TGPIPE_SESSION_STRING` logs in
  with no interaction at all — but the string has to come from the user.

## Gotchas worth knowing

- **Group "tags" are `rank`, not usernames.** The custom title a group shows
  next to a name lives on the participant, so it only appears in `chats
  members` records (`rank`, plus `role`), never in an `entity`. The same person
  has different ranks in different groups.
- **`delete` can succeed and remove nothing.** Telegram silently ignores
  deletion of service messages (joins, pins, title changes). Check
  `details.deleted` against what you asked for, not just `ok`.
- **One process per session.** Telethon holds a write transaction on the
  session file, so parallel commands can fail intermittently. Notably, do not
  run other commands while `messages watch` is listening.
- **`messages watch` never returns** — it streams JSONL until interrupted. Run
  it in the background and read its output file; never block on it.
- **Photos report a size that differs from the bytes saved.** Already handled
  when skipping downloads; just don't compare `media.size` to a file on disk.
- **Sending HTML gives markdown back.** `--parse-mode html` applies the right
  entities, but the `text` field is always reconstructed as markdown. Check
  `--raw` if the entities themselves matter.

## Command reference

**Cross-chat** — `digest`, `inbox`, `mentions`
`digest [--since -24h] [--until] [--chats a,b] [--exclude c] [--type user|bot|group|channel] [--limit-per-chat N] [--unread-only] [--incoming-only] [--include-archived]`
`inbox [--limit-chats N] [--preview N] [--folder ID] [--mentions-only]`
`mentions [--since] [--limit N] [--all-chats]` — default scans only chats with
unread mentions (fast); `--all-chats` scans everything and is much slower.

**chats** — `list [--limit N] [--all] [--archived] [--type ...] [--query T] [--folder ID]`,
`info CHAT`, `members CHAT [--limit N] [--query T] [--filter admins|bots|kicked|banned]`,
`join LINK|@name`, `leave CHAT --yes`, `archive|unarchive CHAT`, `folders`,
`mark-read CHAT`, `search-public "text" [--limit N]`

**messages** — `history CHAT [--limit N|--all] [--since] [--until] [--from-user X] [--type photo|video|url|voice|…] [--ids '1,2,5-8'] [--offset-id ID] [--min-id] [--max-id] [--reverse] [--with-chat]`,
`search "text" [--chat CHAT] [--since] [--from-user] [--type]`,
`send CHAT (--text T | --text-file F | --stdin) [--file PATH]… [--reply-to ID] [--parse-mode md|html|none] [--silent] [--no-webpage] [--as-document] [--schedule WHEN] [--dry-run]`,
`forward --from CHAT --to CHAT --ids '1,2,3' [--drop-author]`,
`edit CHAT ID --text "…"`, `delete CHAT --ids '1,2' [--no-revoke] [--yes]`,
`pin|unpin CHAT [ID]`, `react CHAT ID [--emoji 👍]` (no emoji removes it),
`drafts`, `scheduled CHAT`, `unschedule CHAT --ids …`, `watch [CHAT…]`

**media** — `download CHAT [--types photo,video,document,voice,audio,gif] [--ids] [--since] [--until] [--min-size 100k] [--max-size 50M] [--out DIR] [--name-template '{chat}/{date}_{id}{ext}'] [--limit N] [--overwrite]`,
`download-message CHAT ID --out PATH`

**export** — `chat CHAT --out DIR [--with-media] [--since] [--until] [--restart] [--no-participants]`,
`all --out DIR [--type group] [--exclude X] [--with-media] [--limit N]`

**contacts** — `list`, `blocked`, `resolve +39…|@name|id`, `add --phone --first-name [--last-name]`,
`delete CHAT`, `block|unblock CHAT`

**account** — `sessions`, `terminate-session --hash H --yes`, `terminate-others --yes`

**auth / meta** — `auth status` (exit 0 authorised, 4 not), `auth whoami`,
`auth login-start --phone`, `auth login --code [--password]`, `auth logout`,
`auth export-session --yes`, `auth import-session --string`, `schema [record]`

## Referring to a chat

| form | resolved against |
| --- | --- |
| `me` | Saved Messages |
| `-1001234567890` / `42` | numeric id — unambiguous, best for writing |
| `@name` | username, searched across **all** of Telegram |
| `Project` | title — the **user's own chats** first, elsewhere only if none match |
| `t.me/channel` | public link |
| `+39123456789` | phone number (must be a contact) |

Negative ids are passed directly, with no `--` and no quoting.
