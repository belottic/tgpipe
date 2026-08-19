# tgpipe

A Telegram command-line client that authenticates as **your own account** (not
a bot), built for scripts and automation.

> **This connects your personal Telegram account.** tgpipe authenticates as a
> real user over MTProto, not as a bot: it acts with your identity and your
> permissions, and anything it sends is sent by you. You need your own
> `api_id`/`api_hash` from [my.telegram.org](https://my.telegram.org). Telegram
> treats automation of user accounts as sensitive and may restrict or ban
> accounts that abuse it — read their
> [Terms of Service](https://telegram.org/tos), keep your usage reasonable, and
> note that responsibility for how you use this tool is yours.

Two rules hold everything else together:

1. **stdout carries data only.** Logs, progress and errors go to stderr.
2. **No command ever prompts.** Not even login, which is split into two
   invocations driven by flags or environment variables. The only `input()` in
   the program sits behind an explicit `--interactive` flag.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13 (uv fetches it for
you).

```bash
git clone https://github.com/belottic/tgpipe.git
cd tgpipe
uv sync                          # create the environment
uv tool install --editable .     # put `tgpipe` on PATH
```

With `uv tool install --editable`, `tgpipe` works from any directory and picks
up code changes immediately. Without that step, use `uv run tgpipe …` from the
repository root.

You need an `api_id` / `api_hash` pair, created at <https://my.telegram.org> →
*API development tools*:

```bash
cp .env.example .env
# then fill in TGPIPE_API_ID and TGPIPE_API_HASH
```

`.env`, the session file and the login state stay in the repository directory
with mode `600`, and are all gitignored.

**Where credentials are looked up.** They are anchored to the repository root,
not to the current directory: `tgpipe` run from `/tmp` still finds its session.
The files a command *produces* (`--out`, downloads, exports) are relative to
the current directory, which is where you expect them.

### Installing without cloning

```bash
uv tool install git+https://github.com/belottic/tgpipe
```

This gets you the command but no repository to anchor to, so credentials and
the session are looked up in the **current directory** instead. Give it a fixed
home to avoid surprises:

```bash
export TGPIPE_HOME="$HOME/.config/tgpipe"
mkdir -p "$TGPIPE_HOME"
# put TGPIPE_API_ID and TGPIPE_API_HASH in $TGPIPE_HOME/.env
```

`TGPIPE_HOME` also lets you keep a second account, or isolate tests, on a
cloned install.

## Login

Telegram delivers the code out of band (SMS, or a message inside Telegram if
you have another session). Someone has to read it. But the CLI never asks you
for it at a prompt:

```bash
tgpipe auth login-start --phone +39...     # sends the code
tgpipe auth login --code 12345             # completes
tgpipe auth login --code 12345 --password <2FA>
```

Every value can also come from an environment variable (`TGPIPE_CODE`,
`TGPIPE_PASSWORD`) or from stdin with `--code -`. If 2FA is required and the
password is missing, the command exits `4` with `password_required` rather than
blocking.

Alternatives:

```bash
tgpipe auth login --qr            # QR code to scan with your phone
tgpipe auth login --interactive   # classic prompted flow
tgpipe auth status                # exit 0 if authenticated, 4 otherwise
```

**Reusing the session.** After bootstrapping once by hand, logging in on any
other machine or in CI takes no interaction at all:

```bash
tgpipe auth export-session --yes | jq -r .details.session_string
# elsewhere: TGPIPE_SESSION_STRING=… or
tgpipe auth import-session --string <string>
```

> A StringSession is equivalent to full access to your account. Treat it like a
> password: never commit it, never paste it into a chat.

## Output

`--format json` (default) | `jsonl` (streaming) | `table` (human eyes only).

No envelope and no cursor: pagination uses `offset_id`, which you read from the
last record's `id`.

```bash
tgpipe chats list --limit 5 | jq '.[].entity.title'
tgpipe --format jsonl messages history @someone --limit 200 > history.jsonl
tgpipe messages history @someone --offset-id 4711   # next page
```

Errors go to stderr as JSON, with meaningful exit codes:

| code | meaning |
| --- | --- |
| 0 | ok |
| 2 | bad arguments or configuration |
| 3 | chat or entity not found |
| 4 | session missing or expired |
| 5 | FloodWait beyond `--flood-max-wait` |
| 6 | permission or privacy denied |
| 1 | anything else |

The record schema is in [docs/SCHEMA.md](docs/SCHEMA.md), generated from the
pydantic models and queryable at runtime with `tgpipe schema`.

## Referring to a chat

`me`, a numeric id (`-1001234567890` — negative ids need no `--` and no
quoting), `@username` (searched across all of Telegram), a `t.me/…` link, a
`+39…` phone number, or the chat **title**.

A bare title is looked up among your own chats first and only then elsewhere:
`Project` is your group, `@Project` is any public entity of the same name. If
the title is ambiguous the command exits `3`, listing candidate ids and names.

For **writing**, use the id: it is the only form that cannot resolve to the
wrong chat.

## Commands

**Cross-chat views** — these answer "what did I miss?" in a single call,
instead of `chats list` plus N calls to `history`:

```bash
tgpipe --format jsonl digest --since -24h   # every line carries its own chat
tgpipe inbox --preview 3                    # unread chats + latest messages
tgpipe mentions --since -7d                 # where you were mentioned
```

**Chats** — `list`, `info`, `members` (returns `role` and `rank`, the custom
title a group displays next to a name), `join`, `leave`, `archive`,
`unarchive`, `folders`, `mark-read`, `search-public`.

**Messages** — `history`, `search`, `send`, `forward`, `edit`, `delete`, `pin`,
`unpin`, `react`, `drafts`, `scheduled`, `unschedule`, `watch`.

```bash
tgpipe messages send me --text "reminder"
tgpipe messages send @someone --file photo.jpg --text "here"
tgpipe messages send @someone --text "…" --dry-run   # show, do not send
cat note.md | tgpipe messages send me --stdin
tgpipe messages search "invoice" --since -30d
```

**Media** — bulk downloads, resumable:

```bash
tgpipe --format jsonl media download @channel --types photo,video \
  --since -7d --out ./downloaded
```

**Export** — resumable backup. Interrupted halfway, the same command resumes:
it re-reads the last id from `messages.jsonl` and continues from there.

```bash
tgpipe export chat @group --out ./backup --with-media
tgpipe export all --out ./backup --type group
```

**Contacts and account** —
`contacts list|add|delete|block|unblock|blocked|resolve`,
`account sessions|terminate-session|terminate-others`.

```bash
tgpipe contacts resolve +39123456789
tgpipe account sessions --format table
```

## Known limits

- **One process per session.** Telethon holds an open transaction on the
  session file, so two commands in parallel can fail with `session_busy`. This
  mostly affects `messages watch`, which keeps listening.
- **`delete` does not remove service messages** (joins, pins, title changes):
  Telegram accepts the request and leaves them. The command reports this in
  `details.deleted` and `details.note` instead of just saying `ok`.
- **For photos, the declared size is not the size saved** (`file.size` reports
  the largest progressive variant). Recognising already-downloaded files
  therefore accepts any non-empty file for photos, stickers and web previews;
  for documents the comparison stays exact.

## Development

```bash
uv run pytest                          # offline tests, no network
uv run python tools/gen_schema.py      # regenerate docs/SCHEMA.md
```

`tgpipe/models.py` is the output contract: if you change a record, regenerate
the schema.

## Using it from Claude Code

The repository ships an agent skill in `.claude/skills/tgpipe/`. It is picked
up automatically when working inside this project; to use it from anywhere,
link it into your user skills directory:

```bash
ln -s "$PWD/.claude/skills/tgpipe" ~/.claude/skills/tgpipe
```

The skill documents the command set, the output schema, the exit codes and the
safety rules for write operations.
