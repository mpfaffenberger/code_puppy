"""PTY Manager for terminal emulation with cross-platform support.

Provides pseudo-terminal (PTY) functionality for interactive shell sessions
via WebSocket connections. Supports Unix (pty module) and Windows (pywinpty).
"""

import asyncio
import logging
import os
import signal
import struct
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform == "win32"

# Conditional imports based on platform
if IS_WINDOWS:
    try:
        import winpty  # type: ignore

        HAS_WINPTY = True
    except ImportError:
        HAS_WINPTY = False
        winpty = None
else:
    import fcntl
    import pty
    import termios

    HAS_WINPTY = False


@dataclass
class PTYSession:
    """Represents an active PTY session."""

    session_id: str
    master_fd: Optional[int] = None  # Unix only
    slave_fd: Optional[int] = None  # Unix only
    pid: Optional[int] = None  # Unix only
    winpty_process: Any = None  # Windows only
    cols: int = 80
    rows: int = 24
    on_output: Optional[Callable[[bytes], None]] = None
    _reader_task: Optional[asyncio.Task] = None  # type: ignore
    _running: bool = field(default=False, init=False)

    def is_alive(self) -> bool:
        """Check if the PTY session is still active."""
        if IS_WINDOWS:
            return self.winpty_process is not None and self.winpty_process.isalive()
        else:
            if self.pid is None:
                return False
            try:
                pid_result, status = os.waitpid(self.pid, os.WNOHANG)
                if pid_result == 0:
                    return True  # Still running
                return False  # Exited
            except ChildProcessError:
                return False  # Already reaped


class PTYManager:
    """Manages PTY sessions for terminal emulation.

    Provides cross-platform terminal emulation with support for:
    - Unix systems via the pty module
    - Windows via pywinpty (optional dependency)

    Example:
        manager = PTYManager()
        session = await manager.create_session(
            session_id="my-terminal",
            on_output=lambda data: print(data.decode())
        )
        await manager.write(session.session_id, b"ls -la\n")
        await manager.close_session(session.session_id)
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PTYSession] = {}
        self._lock = asyncio.Lock()

    @property
    def sessions(self) -> dict[str, PTYSession]:
        """Get all active sessions."""
        return self._sessions.copy()

    async def create_session(
        self,
        session_id: str,
        cols: int = 80,
        rows: int = 24,
        on_output: Optional[Callable[[bytes], None]] = None,
        shell: Optional[str] = None,
    ) -> PTYSession:
        """Create a new PTY session.

        Args:
            session_id: Unique identifier for the session
            cols: Terminal width in columns
            rows: Terminal height in rows
            on_output: Callback for terminal output
            shell: Shell to spawn (defaults to user's shell or /bin/bash)

        Returns:
            PTYSession: The created session

        Raises:
            RuntimeError: If session creation fails
        """
        async with self._lock:
            if session_id in self._sessions:
                logger.warning(f"Session {session_id} already exists, closing old one")
                await self._close_session_internal(session_id)

            if IS_WINDOWS:
                session = await self._create_windows_session(
                    session_id, cols, rows, on_output, shell
                )
            else:
                session = await self._create_unix_session(
                    session_id, cols, rows, on_output, shell
                )

            self._sessions[session_id] = session
            logger.info(f"Created PTY session: {session_id}")
            return session

    async def _create_unix_session(
        self,
        session_id: str,
        cols: int,
        rows: int,
        on_output: Optional[Callable[[bytes], None]],
        shell: Optional[str],
    ) -> PTYSession:
        """Create a PTY session on Unix systems."""
        shell = shell or os.environ.get("SHELL", "/bin/bash")

        # Fork a new process with a PTY
        pid, master_fd = pty.fork()

        if pid == 0:
            # Child process - exec the shell
            os.execlp(shell, shell, "-i")  # noqa: S606
        else:
            # Parent process
            # Set terminal size
            self._set_unix_winsize(master_fd, rows, cols)

            # Make master_fd non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            session = PTYSession(
                session_id=session_id,
                master_fd=master_fd,
                pid=pid,
                cols=cols,
                rows=rows,
                on_output=on_output,
            )
            session._running = True

            # Start reader task
            session._reader_task = asyncio.create_task(self._unix_reader_loop(session))

            return session

    async def _create_windows_session(
        self,
        session_id: str,
        cols: int,
        rows: int,
        on_output: Optional[Callable[[bytes], None]],
        shell: Optional[str],
    ) -> PTYSession:
        """Create a PTY session on Windows systems."""
        if not HAS_WINPTY:
            raise RuntimeError(
                "pywinpty is required for Windows terminal support. "
                "Install it with: pip install pywinpty"
            )

        shell = shell or os.environ.get("COMSPEC", "cmd.exe")

        # Create winpty process
        winpty_process = winpty.PtyProcess.spawn(
            shell,
            dimensions=(rows, cols),
        )

        session = PTYSession(
            session_id=session_id,
            winpty_process=winpty_process,
            cols=cols,
            rows=rows,
            on_output=on_output,
        )
        session._running = True

        # Start reader task
        session._reader_task = asyncio.create_task(self._windows_reader_loop(session))

        return session

    def _set_unix_winsize(self, fd: int, rows: int, cols: int) -> None:
        """Set the terminal window size on Unix."""
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    async def _unix_reader_loop(self, session: PTYSession) -> None:
        """Read output from Unix PTY and forward to callback."""
        loop = asyncio.get_running_loop()

        try:
            while session._running and session.master_fd is not None:
                try:
                    data = await loop.run_in_executor(
                        None, self._read_unix_pty, session.master_fd
                    )

                    if data is None:
                        # No data available, wait a bit
                        await asyncio.sleep(0.01)
                        continue
                    elif data == b"":
                        # EOF - process terminated
                        break
                    elif session.on_output:
                        session.on_output(data)

                except asyncio.CancelledError:
                    break

        except Exception as e:
            logger.error(f"Unix reader loop error: {e}")
        finally:
            session._running = False

    def _read_unix_pty(self, fd: int) -> bytes | None:
        """Read from Unix PTY file descriptor.

        Returns:
            bytes: Data read from PTY
            None: No data available (would block)
            b'': EOF (process terminated)
        """
        try:
            data = os.read(fd, 4096)
            return data
        except BlockingIOError:
            return None
        except OSError:
            return b""

    async def _windows_reader_loop(self, session: PTYSession) -> None:
        """Read output from Windows PTY and forward to callback."""
        loop = asyncio.get_running_loop()

        try:
            while (
                session._running
                and session.winpty_process is not None
                and session.winpty_process.isalive()
            ):
                try:
                    data = await loop.run_in_executor(
                        None, session.winpty_process.read, 4096
                    )
                    if data and session.on_output:
                        session.on_output(
                            data.encode() if isinstance(data, str) else data
                        )
                except EOFError:
                    break
                except asyncio.CancelledError:
                    break

                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Windows reader loop error: {e}")
        finally:
            session._running = False

    async def write(self, session_id: str, data: bytes) -> bool:
        """Write data to a PTY session.

        Args:
            session_id: The session to write to
            data: Data to write

        Returns:
            bool: True if write succeeded
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            return False

        try:
            if IS_WINDOWS:
                if session.winpty_process:
                    session.winpty_process.write(
                        data.decode() if isinstance(data, bytes) else data
                    )
                    return True
            else:
                if session.master_fd is not None:
                    os.write(session.master_fd, data)
                    return True
        except Exception as e:
            logger.error(f"Write error for session {session_id}: {e}")

        return False

    async def resize(self, session_id: str, cols: int, rows: int) -> bool:
        """Resize a PTY session.

        Args:
            session_id: The session to resize
            cols: New width in columns
            rows: New height in rows

        Returns:
            bool: True if resize succeeded
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            return False

        try:
            if IS_WINDOWS:
                if session.winpty_process:
                    session.winpty_process.setwinsize(rows, cols)
            else:
                if session.master_fd is not None:
                    self._set_unix_winsize(session.master_fd, rows, cols)

            session.cols = cols
            session.rows = rows
            logger.debug(f"Resized session {session_id} to {cols}x{rows}")
            return True

        except Exception as e:
            logger.error(f"Resize error for session {session_id}: {e}")
            return False

    async def close_session(self, session_id: str) -> bool:
        """Close a PTY session.

        Args:
            session_id: The session to close

        Returns:
            bool: True if session was closed
        """
        async with self._lock:
            return await self._close_session_internal(session_id)

    async def _close_session_internal(self, session_id: str) -> bool:
        """Internal session close without lock."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return False

        session._running = False

        # Cancel reader task
        if session._reader_task:
            session._reader_task.cancel()
            try:
                await session._reader_task
            except asyncio.CancelledError:
                pass

        # Clean up platform-specific resources
        if IS_WINDOWS:
            if session.winpty_process:
                try:
                    session.winpty_process.terminate()
                except Exception as e:
                    logger.debug(f"Error terminating winpty: {e}")
        else:
            # Close file descriptors
            if session.master_fd is not None:
                try:
                    os.close(session.master_fd)
                except OSError:
                    pass

            # Terminate child process
            if session.pid is not None:
                try:
                    os.kill(session.pid, signal.SIGTERM)
                    # Use WNOHANG to avoid blocking the event loop
                    try:
                        os.waitpid(session.pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
                except (OSError, ChildProcessError):
                    pass

        logger.info(f"Closed PTY session: {session_id}")
        return True

    async def close_all(self) -> None:
        """Close all PTY sessions."""
        async with self._lock:
            session_ids = list(self._sessions.keys())
            for session_id in session_ids:
                await self._close_session_internal(session_id)
        logger.info("Closed all PTY sessions")

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        """Get a session by ID.

        Args:
            session_id: The session ID

        Returns:
            PTYSession or None if not found
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        """List all active session IDs.

        Returns:
            List of session IDs
        """
        return list(self._sessions.keys())


# Global PTY manager instance
_pty_manager: Optional[PTYManager] = None


def get_pty_manager() -> PTYManager:
    """Get or create the global PTY manager instance."""
    global _pty_manager
    if _pty_manager is None:
        _pty_manager = PTYManager()
    return _pty_manager
