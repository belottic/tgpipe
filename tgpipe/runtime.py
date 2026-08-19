"""Process-wide state and the run loop for async commands."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Coroutine, Iterable
from dataclasses import dataclass, field
from typing import Any

from .config import OutputFormat, Settings, get_settings
from .errors import ExitCode, TgpipeError, emit_error, translate
from .output import Emitter


@dataclass
class State:
    fmt: OutputFormat = "json"
    include_nulls: bool = False
    verbose: bool = False
    raw: bool = False
    _settings: Settings | None = field(default=None, repr=False)

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def emitter(self) -> Emitter:
        return Emitter(self.fmt, self.include_nulls)

    def emit(self, record: Any) -> None:
        self.emitter.one(record)

    def emit_all(self, records: Iterable[Any]) -> int:
        return self.emitter.many(records)

    async def emit_stream(self, records: AsyncIterator[Any]) -> int:
        return await self.emitter.many_async(records)


state = State()


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdout stays clean, always
    )
    if not verbose:
        logging.getLogger("telethon").setLevel(logging.ERROR)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async command, translating every error into an exit code + JSON."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        emit_error(TgpipeError("interrupted"))
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - this is the outer boundary
        error = translate(exc)
        if state.verbose:
            import traceback

            traceback.print_exc(file=sys.stderr)
        emit_error(error)
        raise SystemExit(int(error.exit_code)) from None
