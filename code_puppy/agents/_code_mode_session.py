"""Keep the code-mode REPL alive across runs of one session.

The harness gives every agent run a fresh Monty REPL, and each user prompt is a
new run, so variables vanished between turns. Here the idle REPL is saved when
a run ends and restored when the next run with the same session key starts,
through the harness's ``CodeModeReplStore`` hook.
Main-agent state sits beside the autosave as ``<session>_repl.bin``, so
``/resume`` brings it back and session deletion removes it; a sub-agent's sits
beside its ``subagent_sessions/<session_id>.json``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Callable

import anyio
from pydantic_ai import RunContext

logger = logging.getLogger(__name__)

REPL_SUFFIX = "_repl.bin"
# A dump holds every live variable; don't write a runaway one to disk.
MAX_REPL_BYTES = 32 * 1024 * 1024

ReplPath = Callable[[], "Path | None"]


def repl_path_for(directory: Path | str, session_key: str) -> Path:
    """Where the REPL dump for ``session_key`` lives inside ``directory``."""
    return Path(directory) / f"{session_key}{REPL_SUFFIX}"


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes() or None
    except FileNotFoundError:
        return None


class FileReplStore:
    """``CodeModeReplStore`` that keeps one REPL state file per session."""

    def __init__(self, repl_path: ReplPath) -> None:
        self._repl_path = repl_path

    async def load(self, ctx: RunContext[object]) -> bytes | None:
        path = self._repl_path()
        if path is None:
            return None
        return await anyio.to_thread.run_sync(_read, path)

    async def save(self, ctx: RunContext[object], state: bytes | None) -> None:
        path = self._repl_path()
        if path is None:
            return
        if state is not None and len(state) > MAX_REPL_BYTES:
            logger.warning(
                "code mode: REPL state is %d bytes; not saving it", len(state)
            )
            state = None
        if state is None:
            await anyio.to_thread.run_sync(lambda: path.unlink(missing_ok=True))
            return
        await anyio.to_thread.run_sync(_write_atomic, path, state)
