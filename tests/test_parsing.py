from datetime import UTC, datetime, timedelta

import pytest

from tgpipe.errors import UsageError
from tgpipe.parsing import parse_csv, parse_date, parse_ids, parse_size


def test_parse_date_relative():
    before = datetime.now(UTC) - timedelta(hours=24)
    parsed = parse_date("-24h")
    assert abs((parsed - before).total_seconds()) < 5


def test_parse_date_naive_iso_becomes_utc():
    assert parse_date("2026-08-18").tzinfo == UTC
    assert parse_date("2026-08-18T10:00:00Z") == datetime(2026, 8, 18, 10, tzinfo=UTC)


def test_parse_date_empty_or_none():
    assert parse_date(None) is None
    assert parse_date("  ") is None


def test_parse_date_invalid():
    with pytest.raises(UsageError, match="invalid date"):
        parse_date("domani")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,2,3", [1, 2, 3]), ("1 2", [1, 2]), ("5-8", [5, 6, 7, 8]), ("", []), (None, [])],
)
def test_parse_ids(value, expected):
    assert parse_ids(value) == expected


def test_parse_ids_reversed_range():
    with pytest.raises(UsageError, match="reversed id range"):
        parse_ids("8-5")


def test_parse_ids_non_numeric():
    with pytest.raises(UsageError, match="invalid id"):
        parse_ids("1,abc")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1024", 1024), ("1k", 1024), ("1.5M", 1572864), ("2G", 2 * 1024**3), (None, None)],
)
def test_parse_size(value, expected):
    assert parse_size(value) == expected


def test_parse_size_invalid():
    with pytest.raises(UsageError):
        parse_size("tanto")


def test_parse_csv():
    assert parse_csv(" a , b ,, c ") == ["a", "b", "c"]
    assert parse_csv(None) == []
