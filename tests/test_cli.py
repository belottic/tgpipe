"""End-to-end CLI tests that need no network.

They run in a temporary cwd, so they see neither the real .env nor the real
session.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args, cwd, stdin=subprocess.DEVNULL, env=None):
    environment = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("TGPIPE_", "TELEGRAM_"))
    }
    environment["PYTHONPATH"] = ROOT
    # without TGPIPE_HOME the subprocesses would use the real .env and session
    environment["TGPIPE_HOME"] = str(cwd)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "tgpipe.cli", *args],
        cwd=cwd, stdin=stdin, capture_output=True, text=True,
        env=environment, timeout=60,
    )


def test_help_exits_zero(tmp_path):
    assert run_cli("--help", cwd=tmp_path).returncode == 0


def test_version(tmp_path):
    result = run_cli("--version", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip()


def test_missing_config_exits_2_with_json_on_stderr(tmp_path):
    result = run_cli("chats", "list", cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["type"] == "config"
    assert "TGPIPE_API_ID" in payload["error"]["message"]


def test_does_not_block_on_closed_stdin(tmp_path):
    """The most important test: with no session it must never wait for input."""
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("auth", "login", "--code", "12345", cwd=tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["type"] == "usage"


def test_invalid_date_argument_exits_2(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("messages", "history", "me", "--since", "domani", cwd=tmp_path)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["type"] == "usage"


def test_send_without_content_exits_2(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("messages", "send", "me", cwd=tmp_path)
    assert result.returncode == 2
    assert "nothing to send" in json.loads(result.stderr)["error"]["message"]


def test_leave_requires_confirmation(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("chats", "leave", "qualcosa", cwd=tmp_path)
    assert result.returncode == 2
    assert "--yes" in json.loads(result.stderr)["error"]["message"]


def test_export_session_requires_yes(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("auth", "export-session", cwd=tmp_path)
    assert result.returncode == 2
    assert "--yes" in json.loads(result.stderr)["error"]["message"]


def test_schema_is_valid_json(tmp_path):
    result = run_cli("schema", cwd=tmp_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "message" in payload and "entity" in payload


def test_schema_single_record(tmp_path):
    result = run_cli("schema", "entity", cwd=tmp_path)
    assert json.loads(result.stdout)["properties"]["kind"]


def test_schema_unknown_record(tmp_path):
    assert run_cli("schema", "pippo", cwd=tmp_path).returncode != 0


@pytest.mark.parametrize("fmt", ["yaml", "csv"])
def test_unknown_format_rejected(tmp_path, fmt):
    assert run_cli("--format", fmt, "chats", "list", cwd=tmp_path).returncode != 0


# --- group and channel ids are negative: they must not look like options ---


def test_negative_id_is_an_argument_not_an_option(tmp_path):
    """Without this, the id printed by 'chats list' is not reusable."""
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("messages", "send", "-1001234567890", cwd=tmp_path)
    # it reaches content validation, so the id was accepted
    assert "nothing to send" in json.loads(result.stderr)["error"]["message"]


def test_negative_id_alongside_short_options(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("messages", "history", "-1001234567890", "-n", "1", "--since",
                     "domani", cwd=tmp_path)
    assert json.loads(result.stderr)["error"]["type"] == "usage"


def test_unknown_option_still_fails(tmp_path):
    """ignore_unknown_options must not let typos through silently."""
    result = run_cli("messages", "history", "me", "--limitt", "5", cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""


def test_delete_above_ten_requires_confirmation(tmp_path):
    (tmp_path / ".env").write_text("TGPIPE_API_ID=1\nTGPIPE_API_HASH=abc\n")
    result = run_cli("messages", "delete", "me", "--ids", "1-11", cwd=tmp_path)
    assert result.returncode == 2
    assert "--yes" in json.loads(result.stderr)["error"]["message"]
