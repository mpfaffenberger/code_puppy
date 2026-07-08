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

* ``FileSystemBackend`` -- **synchronous** (file tools run in Code Puppy's tool
  threadpool, off any event loop). When installed it owns the *entire* file
  surface the agent's tools touch, so there is exactly one filesystem the agent
  sees (no reading from the host while listing the local disk). See the
  protocol docstring for the operation set and the path/error/encoding
  contracts a backend must honor.
* ``CommandExecutor`` -- **asynchronous** (the shell tool awaits it on the event
  loop). Runs one shell command and returns its combined output + exit code.

Design note -- why the FileSystemBackend covers the *whole* surface
------------------------------------------------------------------
An earlier iteration only routed text read/write through the backend and left
``list_files`` / existence / delete on the local disk. That produced a
split-brain filesystem: a backend could serve ``read_file`` from a host buffer
while ``list_files`` reported the local disk -- coherent *only* when the host
happens to be the local disk (as it is for an editor on the same machine), and
incoherent for any remote/sandbox/virtual backend. So the backend owns every
operation the file tools perform. Recursive listing and content search are
*composed* by the core from ``list_dir`` + ``read_text_file`` when a backend is
installed, which keeps the backend contract small while remaining coherent; the
fast local ripgrep path is retained only for the no-backend (default) case.

A backend that legitimately shares the local disk (e.g. the ACP editor host,
which overlays only *content* -- unsaved buffers) is free to implement the
metadata/topology operations against the local disk in its adapter. That
"serve topology locally" choice belongs in the adapter, which *knows* its host
shares the disk -- never baked into this general seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable


# =============================================================================
# Filesystem backend (workspace file I/O)
# =============================================================================
@dataclass(frozen=True)
class DirEntry:
    """One entry in a directory listing.

    ``name`` is the bare entry name (no path), ``is_dir`` distinguishes files
    from directories, and ``size`` is the file size in bytes (0 for
    directories, or when the backend cannot cheaply determine it).
    """

    name: str
    is_dir: bool
    size: int = 0


@runtime_checkable
class FileSystemBackend(Protocol):
    """Host-provided filesystem for the agent's workspace tools. Synchronous.

    When a backend is installed it owns **every** filesystem operation the
    agent's file tools perform, so the agent sees a single coherent filesystem.
    Recursive listing and content search (grep) are composed by the core from
    ``list_dir`` + ``read_text_file``; a backend does not implement those
    directly.

    Contracts every method must honor
    ---------------------------------
    * **Paths** are always absolute and already normalized by the core
      (``code_puppy.tools.common.resolve_path``) before the backend is called.
      A backend never has to resolve relative paths or a working directory.
    * **Errors**: raise ``FileNotFoundError`` when a required path is missing,
      ``NotADirectoryError`` when a directory op targets a file (and vice
      versa), and ``OSError`` / ``ValueError`` for anything else. The core maps
      these onto tool error messages uniformly, so a backend should not invent
      its own error return values.
    * **Encoding**: text is UTF-8. A backend need not honor other encodings
      (the core rejects non-UTF-8 writes before reaching the backend).

    Internal writes (config, session state, agent metadata) deliberately do
    **not** go through a backend -- they are machine-local and must never be
    rerouted into an editor workspace.
    """

    # --- content -----------------------------------------------------------
    def read_text_file(
        self, path: str, line: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        """Return text of ``path`` (may reflect unsaved host edits).

        ``line`` (1-based) + ``limit`` request a slice so hosts can avoid
        shipping an entire large file for a chunked read; both ``None`` means
        the full file. Raises ``FileNotFoundError`` if ``path`` does not exist.
        """

    def write_text_file(self, path: str, content: str) -> None:
        """Write ``content`` (UTF-8 text) to ``path`` through the host."""

    # --- metadata / topology ----------------------------------------------
    def exists(self, path: str) -> bool:
        """Return whether ``path`` exists (file or directory)."""

    def is_file(self, path: str) -> bool:
        """Return whether ``path`` exists and is a regular file."""

    def is_dir(self, path: str) -> bool:
        """Return whether ``path`` exists and is a directory."""

    def list_dir(self, path: str) -> List[DirEntry]:
        """List the immediate children of directory ``path`` (one level).

        Raises ``FileNotFoundError`` if ``path`` does not exist and
        ``NotADirectoryError`` if it is not a directory.
        """

    # --- mutation ----------------------------------------------------------
    def delete_file(self, path: str) -> None:
        """Delete the file at ``path``. Raises ``FileNotFoundError`` if absent."""

    def make_dirs(self, path: str) -> None:
        """Create directory ``path`` and any parents (idempotent, like
        ``os.makedirs(path, exist_ok=True)``)."""


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
