import json

from telethon import errors

from tgpipe.errors import (
    ExitCode,
    Forbidden,
    NotAuthorized,
    TgpipeError,
    emit_error,
    translate,
)


def test_flood_wait_carries_the_seconds():
    error = translate(errors.FloodWaitError(request=None))
    assert error.exit_code == ExitCode.FLOOD_WAIT
    assert "seconds" in error.details


def test_two_factor_password():
    error = translate(errors.SessionPasswordNeededError(request=None))
    assert error.type == "password_required"
    assert error.exit_code == ExitCode.NOT_AUTHORIZED


def test_entity_not_found_from_value_error():
    error = translate(ValueError('Cannot find any entity corresponding to "pippo"'))
    assert error.exit_code == ExitCode.NOT_FOUND


def test_permission_denied():
    error = translate(errors.ChatWriteForbiddenError(request=None))
    assert error.exit_code == ExitCode.FORBIDDEN
    assert error.details["telethon_error"] == "ChatWriteForbiddenError"


def test_revoked_session_is_not_authorized():
    error = translate(errors.AuthKeyUnregisteredError(request=None))
    assert error.exit_code == ExitCode.NOT_AUTHORIZED


def test_generic_error_stays_generic():
    assert translate(RuntimeError("boom")).exit_code == ExitCode.GENERIC


def test_tgpipe_error_passes_through():
    original = Forbidden("no")
    assert translate(original) is original


def test_error_goes_to_stderr_as_json(capsys):
    emit_error(NotAuthorized())
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["type"] == "not_authorized"


def test_payload_omits_empty_details():
    assert "details" not in TgpipeError("x").payload()["error"]


def test_busy_session_explains_what_to_do():
    """'database is locked' tells neither a user nor an agent anything."""
    import sqlite3

    error = translate(sqlite3.OperationalError("database is locked"))
    assert error.type == "session_busy"
    assert "one command at a time" in error.message
    assert "TGPIPE_SESSION_PATH" in error.message


def test_other_sqlite_errors_stay_generic():
    import sqlite3

    assert translate(sqlite3.OperationalError("no such table: x")).type == "error"
