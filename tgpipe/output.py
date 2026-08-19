"""Emitting results.

Non-negotiable rule: stdout carries data only. Logs, progress and errors go
to stderr.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator, Iterable, Sequence
from typing import Any

from .config import OutputFormat
from .models import Record

_MAX_COLS = 8
_MAX_CELL = 44


def _to_dict(obj: Any, include_nulls: bool) -> Any:
    if isinstance(obj, Record):
        return obj.model_dump(mode="json", exclude_none=not include_nulls)
    return obj


def _write(line: str) -> None:
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # typical of `... | head`: exit quietly, this is not our error
        raise SystemExit(0) from None


class Emitter:
    def __init__(self, fmt: OutputFormat = "json", include_nulls: bool = False) -> None:
        self.fmt = fmt
        self.include_nulls = include_nulls

    def _dumps(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def one(self, record: Any) -> None:
        data = _to_dict(record, self.include_nulls)
        if self.fmt == "table":
            _write(_render_vertical(data))
        else:
            _write(self._dumps(data))

    def many(self, records: Iterable[Any]) -> int:
        rows = [_to_dict(r, self.include_nulls) for r in records]
        return self._flush_many(rows)

    async def many_async(self, records: AsyncIterator[Any]) -> int:
        """In jsonl it emits as it goes; other formats buffer."""
        if self.fmt == "jsonl":
            count = 0
            async for record in records:
                _write(self._dumps(_to_dict(record, self.include_nulls)))
                count += 1
            return count

        rows = [_to_dict(r, self.include_nulls) async for r in records]
        return self._flush_many(rows)

    def _flush_many(self, rows: Sequence[Any]) -> int:
        if self.fmt == "jsonl":
            for row in rows:
                _write(self._dumps(row))
        elif self.fmt == "table":
            _write(_render_table(rows))
        else:
            _write(self._dumps(list(rows)))
        return len(rows)


def note(message: str) -> None:
    """Progress or warning message: always to stderr."""
    print(message, file=sys.stderr, flush=True)


# --- table rendering (human eyes only, never to be parsed) -----------------


def _flatten(data: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return {prefix or "value": _cell(data)}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, name))
        else:
            out[name] = _cell(value)
    return out


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return f"[{len(value)}]"
    text = str(value).replace("\n", " ").replace("\t", " ")
    return text if len(text) <= _MAX_CELL else text[: _MAX_CELL - 1] + "…"


def _render_vertical(data: Any) -> str:
    flat = _flatten(data)
    if not flat:
        return ""
    width = max(len(k) for k in flat)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in flat.items())


def _render_table(rows: Sequence[Any]) -> str:
    if not rows:
        return "(no results)"

    flat_rows = [_flatten(r) for r in rows]
    columns: list[str] = []
    for row in flat_rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    # drop always-empty columns, then cut to the first _MAX_COLS useful ones
    columns = [c for c in columns if any(r.get(c) for r in flat_rows)][:_MAX_COLS]
    if not columns:
        return f"({len(rows)} results with no displayable fields)"

    widths = {
        c: max(len(c), *(len(r.get(c, "")) for r in flat_rows)) for c in columns
    }
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    body = [
        "  ".join(r.get(c, "").ljust(widths[c]) for c in columns) for r in flat_rows
    ]
    return "\n".join([header, sep, *body])
