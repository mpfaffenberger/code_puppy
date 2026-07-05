"""Pluggable I/O backends for Code Puppy's tool layer.

By default Code Puppy's file and shell tools do I/O directly against the local
machine (``open()`` / ``atomic_write_text`` / ``subprocess``). An embedder that
hosts Code Puppy inside another environment -- an IDE, a sandbox, or an editor
speaking the Agent Client Protocol -- may want that I/O routed through *its*
channels instead, so edits land in the host's diff UI, reads see the host's
unsaved buffers, and commands run in the host's terminal.

These registries are the seam for that. They mirror ``set_approval_backend`` in
``tools.common``: a single process-wide slot, ``None`` by default (pure local
behavior), swapped in by the embedder. The tool layer checks the slot and
delegates when a backend is present, otherwise runs locally.

Two independent backends:

* ``FileSystemBackend`` — **synchronous** (file tools run in Code Puppy's tool
  threadpool, off any event loop). Covers *workspace* file reads/writes, i.e.
  the agent editing project files; internal writes (config, session state)
  deliberately do not go through it.
* ``CommandExecutor`` — **asynchronous** (the shell tool awaits it on the event
  loop). Runs one shell command and returns its combined output + exit code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


# =============================================================================
# Filesystem backend (workspace file I/O)
# =============================================================================
@runtime_checkable
class FileSystemBackend(Protocol):
    """Host-provided read/write for workspace files. Synchronous."""

    def read_text_file(
        self, path: str, line: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        """Return text of ``path`` (may reflect unsaved host edits).

        ``line`` (1-based) + ``limit`` request a slice so hosts can avoid
        shipping an entire large file for a chunked read; both ``None`` means
        the full file.
        """

    def write_text_file(self, path: str, content: str) -> None:
        """Write ``content`` to ``path`` through the host."""


_FS_BACKEND: Optional[FileSystemBackend] = None


def set_filesystem_backend(backend: Optional[FileSystemBackend]) -> None:
    """Install (or clear, with ``None``) the workspace filesystem backend."""
    global _FS_BACKEND
    _FS_BACKEND = backend


def get_filesystem_backend() -> Optional[FileSystemBackend]:
    """Return the installed filesystem backend, or ``None`` for local I/O."""
    return _FS_BACKEND


# =============================================================================
# Command executor (shell)
# =============================================================================
@dataclass
class ExecResult:
    """Outcome of running one command through a ``CommandExecutor``.

    ``output`` is the combined stdout+stderr stream (host terminals typically
    interleave them, matching Code Puppy's own streaming shell behavior).
    """

    exit_code: int
    output: str
    timed_out: bool = False


@runtime_checkable
class CommandExecutor(Protocol):
    """Host-provided shell execution. Asynchronous (awaited on the loop)."""

    async def run(self, command: str, cwd: Optional[str], timeout: int) -> ExecResult:
        """Run ``command`` (a shell string) and return its result."""


_CMD_EXECUTOR: Optional[CommandExecutor] = None


def set_command_executor(executor: Optional[CommandExecutor]) -> None:
    """Install (or clear, with ``None``) the shell command executor."""
    global _CMD_EXECUTOR
    _CMD_EXECUTOR = executor


def get_command_executor() -> Optional[CommandExecutor]:
    """Return the installed command executor, or ``None`` for local subprocess."""
    return _CMD_EXECUTOR
