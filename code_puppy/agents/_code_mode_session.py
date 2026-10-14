"""Keep the code-mode REPL alive across runs of one session.

The harness gives every agent run a fresh Monty REPL, and each user prompt is a
new run, so variables vanished between turns. Here the idle REPL is dumped when
a run ends and restored when the next run with the same session key starts.
Main-agent state sits beside the autosave as ``<session>_repl.bin``, so
``/resume`` brings it back and session deletion removes it; a sub-agent's sits
beside its ``subagent_sessions/<session_id>.json``.

Reaches into the harness's private ``_MontyRunState`` / ``_run_state``; the
harness version is pinned exactly in ``pyproject.toml``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai_harness.code_mode import CodeMode
from pydantic_ai_harness.code_mode._eager import EagerCodeModeToolset
from pydantic_ai_harness.code_mode._toolset import _MontyRunState
from pydantic_monty import MontySession, ResourceLimits

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


@dataclass
class _SessionRunState(_MontyRunState):
    """Run state that starts from a saved REPL and saves it again on close."""

    path: Path | None = None
    pending: bytes | None = None
    # Set only by an explicit `restart: true`. Harness-internal resets (a
    # cancelled feed, an eager prefix mismatch) keep the last saved REPL.
    discarded: bool = field(default=False, repr=False)

    def get_session(
        self,
        *,
        type_check: bool,
        type_check_stubs: str | None,
        limits: ResourceLimits,
    ) -> MontySession:
        fresh = self.session is None
        session = super().get_session(
            type_check=type_check, type_check_stubs=type_check_stubs, limits=limits
        )
        blob, self.pending = self.pending, None
        if fresh and blob is not None:
            try:
                session.load_session(blob)
            except Exception as exc:  # stale dump from another Monty version
                logger.warning(
                    "code mode: cannot restore REPL from %s: %s", self.path, exc
                )
                self._forget()
                super().reset()
                session = super().get_session(
                    type_check=type_check,
                    type_check_stubs=type_check_stubs,
                    limits=limits,
                )
        return session

    def reset(self) -> None:
        self.pending = None
        super().reset()

    def close(self) -> None:
        try:
            self._persist()
        finally:
            super().close()

    def _persist(self) -> None:
        if self.path is None:
            return
        if self.session is None:
            if self.discarded:
                self._forget()
            return
        try:
            blob = self.session.dump()
        except Exception as exc:  # e.g. the run was cancelled mid-statement
            logger.warning("code mode: cannot save REPL state: %s", exc)
            return
        if len(blob) > MAX_REPL_BYTES:
            logger.warning(
                "code mode: REPL state is %d bytes; not saving it", len(blob)
            )
            self._forget()
            return
        try:
            _write_atomic(self.path, blob)
        except OSError as exc:
            logger.warning("code mode: cannot write %s: %s", self.path, exc)

    def _forget(self) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)


def _load(path: Path) -> bytes | None:
    try:
        return path.read_bytes() or None
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("code mode: cannot read %s: %s", path, exc)
        return None


@dataclass
class SessionEagerCodeModeToolset(EagerCodeModeToolset[Any]):
    """``EagerCodeModeToolset`` whose REPL is keyed by a session, not a run."""

    repl_path: ReplPath | None = field(default=None, kw_only=True, repr=False)

    async def __aenter__(self):
        await super().__aenter__()
        try:
            path = self.repl_path() if self.repl_path is not None else None
        except Exception as exc:
            logger.warning("code mode: cannot resolve the REPL session: %s", exc)
            path = None
        if path is not None:
            pending = _load(path)
            # A restored REPL is a "later" snippet: the harness type-checks only
            # the first feed of a fresh REPL, so mark it as already fed.
            self._run_state = _SessionRunState(
                path=path, pending=pending, has_executed_feed=pending is not None
            )
        return self

    async def call_tool(self, name, tool_args, ctx, tool):  # type: ignore[override]
        state = self._run_state
        if tool_args.get("restart", False) and isinstance(state, _SessionRunState):
            state.discarded = True
        return await super().call_tool(name, tool_args, ctx, tool)


@dataclass
class SessionCodeMode(CodeMode[Any]):
    """``CodeMode`` that persists its REPL per session via ``repl_path``."""

    repl_path: ReplPath | None = field(default=None, kw_only=True, repr=False)

    def get_wrapper_toolset(
        self, toolset: AbstractToolset[Any]
    ) -> AbstractToolset[Any] | None:
        built = super().get_wrapper_toolset(toolset)
        if not isinstance(built, EagerCodeModeToolset) or self.repl_path is None:
            return built
        init = {f.name: getattr(built, f.name) for f in fields(built) if f.init}
        return SessionEagerCodeModeToolset(**init, repl_path=self.repl_path)
