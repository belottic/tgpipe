"""Parsing of common arguments: dates, id lists, sizes."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from .errors import UsageError

_RELATIVE = re.compile(r"^-(\d+)([smhdw])$", re.IGNORECASE)
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_SIZE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kmg]?)b?$", re.IGNORECASE)
_MULTIPLIER = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def parse_date(value: str | None, *, what: str = "date") -> datetime | None:
    """Accepts ISO 8601, YYYY-MM-DD, or a relative such as -24h / -7d / -30m."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None

    if match := _RELATIVE.match(value):
        amount, unit = int(match.group(1)), match.group(2).lower()
        return datetime.now(UTC) - timedelta(**{_UNITS[unit]: amount})

    if value.lower() == "now":
        return datetime.now(UTC)

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise UsageError(
            f"invalid {what}: {value!r}. Use ISO 8601 (2026-08-18, "
            "2026-08-18T10:00:00Z) or a relative one (-24h, -7d, -30m)"
        ) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_ids(value: str | None) -> list[int]:
    """'1,2,3' or '1 2 3' or ranges '10-14' -> a list of integers."""
    if not value:
        return []
    ids: list[int] = []
    for chunk in re.split(r"[,\s]+", value.strip()):
        if not chunk:
            continue
        if match := re.fullmatch(r"(\d+)-(\d+)", chunk):
            start, end = int(match.group(1)), int(match.group(2))
            if end < start:
                raise UsageError(f"reversed id range: {chunk!r}")
            ids.extend(range(start, end + 1))
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            raise UsageError(f"invalid id: {chunk!r}") from None
    return ids


def parse_size(value: str | None) -> int | None:
    """'500k', '10M', '1.5G', '1024' -> bytes."""
    if value is None:
        return None
    match = _SIZE.match(value.strip())
    if not match:
        raise UsageError(f"invalid size: {value!r}. Examples: 500k, 10M, 1.5G")
    return int(float(match.group(1)) * _MULTIPLIER[match.group(2).lower()])


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
