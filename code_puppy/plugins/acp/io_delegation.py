"""Wire Code Puppy's I/O backends to the client (file reads/writes + terminal).

This is the delegation layer that makes Code Puppy *truly native* inside the client:
workspace file reads/writes go through the client's ``fs/*`` methods (so edits show in
the client's diff UI and reads see unsaved buffers), and shell commands run through
the client's ``terminal/*`` methods (so they execute in the client's terminal).

It plugs into the two general core seams in ``code_puppy.tools.io_backends``:

* ``FileSystemBackend`` is **synchronous** — file tools run in Code Puppy's
  tool threadpool, so ``DelegatedFileSystemBackend`` bridges to the ACP event loop
  with ``run_coroutine_threadsafe`` (same pattern as the approval backend).
* ``CommandExecutor`` is **asynchronous** — the shell tool awaits it on the
  loop, so ``DelegatedCommandExecutor`` calls the client directly.

Both are installed only when the connected client advertises the matching
capability in ``initialize``; otherwise Code Puppy keeps doing that I/O
locally. Everything talks to the client through the SDK's ``AgentSideConnection``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, List, Optional, Tuple

from code_puppy.plugins.acp import capabilities, state
from code_puppy.tools.io_backends import (
    DirEntry,
    ExecResult,
    set_command_executor,
    set_filesystem_backend,
)

logger = logging.getLogger(__name__)


def shell_invocation(command: str) -> Tuple[str, List[str]]:
    """Split a shell string into ``(program, args)`` for ``terminal/create``.

    ACP's ``terminal/create`` takes a program + argv, so we run the command
    string through the platform shell (``sh -c`` / ``cmd /c``).
    """
    if sys.platform.startswith("win"):
        return "cmd", ["/c", command]
    return "/bin/sh", ["-c", command]


class DelegatedFileSystemBackend:
    """Workspace file I/O that delegates *content* to the client's ``fs/*``.

    Called from Code Puppy's tool threadpool, so the content methods bridge to
    the ACP loop via ``run_coroutine_threadsafe`` and block the worker for the
    answer. The loop stays free to service the round-trip, so there's no
    deadlock; a guard bails out if we ever end up on the loop thread itself.

    Topology/metadata (exists / is_file / is_dir / list_dir / delete /
    make_dirs) is served from the **local disk**: an ACP editor host runs on
    the same machine and workspace as the agent, so the local filesystem is the
    authoritative source for what exists and how the tree is shaped -- only
    *content* carries the host's unsaved-buffer overlay. This "topology is
    local" decision lives here, in the adapter that legitimately knows its host
    shares the disk, and never leaks into the general ``FileSystemBackend``
    seam (a remote/virtual backend would implement these against its own store).
    """

    def read_text_file(
        self, path: str, line: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        async def _read(conn: Any, sid: str) -> str:
            response = await conn.read_text_file(
                path=path, session_id=sid, line=line, limit=limit
            )
            return getattr(response, "content", "") or ""

        return self._bridge(_read)

    def write_text_file(self, path: str, content: str) -> None:
        async def _write(conn: Any, sid: str) -> None:
            await conn.write_text_file(content=content, path=path, session_id=sid)

        self._bridge(_write)

    # --- topology / metadata: local disk (host shares it) ------------------
    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def is_file(self, path: str) -> bool:
        return os.path.isfile(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def list_dir(self, path: str) -> List[DirEntry]:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(path)
        entries: List[DirEntry] = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                if os.path.isdir(full):
                    entries.append(DirEntry(name=name, is_dir=True, size=0))
                elif os.path.isfile(full):
                    size = os.path.getsize(full)
                    entries.append(DirEntry(name=name, is_dir=False, size=size))
            except OSError:
                continue
        return entries

    def delete_file(self, path: str) -> None:
        os.remove(path)

    def make_dirs(self, path: str) -> None:
        if path:
            os.makedirs(path, exist_ok=True)

    def _bridge(self, make_coro):
        connection = state.get_connection()
        loop = state.get_loop()
        session_id = state.get_active_session_id()
        if connection is None or loop is None:
            raise RuntimeError("ACP filesystem backend used with no active connection")
        if session_id is None:
            raise RuntimeError("ACP filesystem backend used outside a session")
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            raise RuntimeError("ACP fs backend hit on the ACP loop (would deadlock)")
        return asyncio.run_coroutine_threadsafe(
            make_coro(connection, session_id), loop
        ).result()


class DelegatedCommandExecutor:
    """Asynchronous shell execution that delegates to the client's ``terminal/*``.

    Awaited on the ACP loop, so it talks to the client directly. Creates a terminal,
    waits for exit (honoring ``timeout`` — kills on overrun), collects the
    combined output, and always releases the terminal handle.
    """

    async def run(self, command: str, cwd: Optional[str], timeout: int) -> ExecResult:
        connection = state.get_connection()
        session_id = state.get_active_session_id()
        if connection is None:
            raise RuntimeError("ACP command executor used with no active connection")
        if session_id is None:
            raise RuntimeError("ACP command executor used outside a session")

        program, args = shell_invocation(command)
        created = await connection.create_terminal(
            command=program, session_id=session_id, args=args, cwd=cwd
        )
        terminal_id = getattr(created, "terminal_id", None)
        if not terminal_id:
            raise RuntimeError("the client did not return a terminalId")

        timed_out = False
        exit_code: Optional[int] = None
        try:
            try:
                exited = await asyncio.wait_for(
                    connection.wait_for_terminal_exit(
                        session_id=session_id, terminal_id=terminal_id
                    ),
                    timeout=timeout,
                )
                exit_code = getattr(exited, "exit_code", None)
            except asyncio.TimeoutError:
                timed_out = True
                await self._kill(connection, session_id, terminal_id)

            out = await connection.terminal_output(
                session_id=session_id, terminal_id=terminal_id
            )
            output = getattr(out, "output", "") or ""
            if exit_code is None:
                status = getattr(out, "exit_status", None)
                exit_code = getattr(status, "exit_code", None) if status else None
        finally:
            await self._release(connection, session_id, terminal_id)

        if exit_code is None:
            exit_code = -1 if timed_out else 0
        return ExecResult(exit_code=int(exit_code), output=output, timed_out=timed_out)

    @staticmethod
    async def _kill(connection: Any, session_id: str, terminal_id: str) -> None:
        try:
            await connection.kill_terminal(
                session_id=session_id, terminal_id=terminal_id
            )
        except Exception:  # noqa: BLE001
            logger.debug("terminal/kill failed", exc_info=True)

    @staticmethod
    async def _release(connection: Any, session_id: str, terminal_id: str) -> None:
        try:
            await connection.release_terminal(
                session_id=session_id, terminal_id=terminal_id
            )
        except Exception:  # noqa: BLE001
            logger.debug("terminal/release failed", exc_info=True)


def install(client_capabilities: Any) -> None:
    """Install the client-backed I/O backends the client can actually service.

    Capability-gated: only reroute reads/writes if the client advertises fs support,
    and only reroute shell if the client advertises terminal support. Unsupported
    edges keep running locally.
    """
    fs_read, fs_write, terminal = capabilities.client_io_caps(client_capabilities)
    if fs_read and fs_write:
        set_filesystem_backend(DelegatedFileSystemBackend())
        logger.debug("ACP: delegating workspace file I/O to the client")
    if terminal:
        set_command_executor(DelegatedCommandExecutor())
        logger.debug("ACP: delegating shell execution to the client's terminal")


def uninstall() -> None:
    """Clear both backends so Code Puppy resumes local I/O."""
    set_filesystem_backend(None)
    set_command_executor(None)
