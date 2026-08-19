"""Generate docs/SCHEMA.md from the pydantic models.

Re-run with:  uv run python tools/gen_schema.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tgpipe.models import SCHEMA_RECORDS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "SCHEMA.md"

INTRO = """# Output schema

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

"""


def type_name(spec: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in spec:
        return spec["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in spec:
        names = [
            type_name(option, defs)
            for option in spec["anyOf"]
            if option.get("type") != "null"
        ]
        return " | ".join(dict.fromkeys(names)) or "null"
    if "const" in spec:
        return repr(spec["const"])
    if "enum" in spec:
        return " | ".join(repr(v) for v in spec["enum"])
    kind = spec.get("type")
    if kind == "array":
        return f"{type_name(spec.get('items', {}), defs)}[]"
    if kind == "object":
        return "object"
    return kind or "any"


def render(name: str, schema: dict[str, Any]) -> str:
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    lines = [f"## `{name}`", ""]
    if description := schema.get("description"):
        lines += [description, ""]
    lines += ["| field | type | required |", "| --- | --- | --- |"]
    for field, spec in schema.get("properties", {}).items():
        if field == "raw":
            continue
        # pipes inside unions would break the markdown table
        rendered = type_name(spec, defs).replace("|", "\\|")
        lines.append(
            f"| `{field}` | `{rendered}` | {'yes' if field in required else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    sections = [
        render(name, model.model_json_schema())
        for name, model in SCHEMA_RECORDS.items()
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(INTRO + "\n".join(sections), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(SCHEMA_RECORDS)} records)")


if __name__ == "__main__":
    main()
