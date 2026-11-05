"""Keep macOS libmalloc's ``MallocStackLogging`` noise out of the terminal.

Why this exists: once a long-lived macOS process receives the system's
"disable malloc stack logging" memory-status event, every ``fork()`` child
it creates prints this from inside ``fork()``, *before* ``exec``::

    python(12345) MallocStackLogging: can't turn off malloc stack logging because it was not enabled.

At that point the child's fd 2 is still *our* fd 2, which is the terminal.
``subprocess`` only dup2()s ``stderr=PIPE`` onto fd 2 after ``fork()``
returns, so every spawn site leaks the line no matter how carefully it
captures stderr (shell tool, MCP stdio servers, hooks, git, provider CLIs),
and it lands in the middle of the TUI. No environment variable is involved,
so scrubbing ``Malloc*`` from child envs would not help.

The fix: fd 2 becomes a pipe, drained by a tiny forwarder process that drops
that one exact line and copies every other byte to the real terminal.

* The forwarder is started with ``posix_spawn``, so there is no fork child
  that could print the noise itself.
* It stays alive until every writer closes the pipe. Late child output and
  crash dumps still reach the terminal, and a background child that outlives
  us never gets EPIPE.
* Python's own ``sys.stderr`` is rebound to a dup of the terminal, so
  in-process writes stay synchronous and ``isatty()``. The inline bar's
  write coordination depends on both.
"""

from __future__ import annotations

import os
import re
import sys

#: The exact libmalloc diagnostic, prefixed by ``progname(pid)``. The program
#: name can carry a parenthesised suffix (``zsh (figterm)(7164)``). This is
#: deliberately narrow: other ``MallocStackLogging`` output, such as when a
#: user *did* enable stack logging, passes through untouched.
MALLOC_NOISE_PATTERN = (
    rb"[\w.+-]+(?: \([\w.+-]+\))?\(\d+\) MallocStackLogging: "
    rb"can't turn off malloc stack logging because it was not enabled\.\r?\n?"
)

_MALLOC_NOISE = re.compile(MALLOC_NOISE_PATTERN)

#: Runs as ``python -I -S -c _FORWARDER_SOURCE <pattern>`` with fd 0 = pipe and
#: fd 1 = terminal. Kept standalone (stdlib only, no ``site``) so it starts
#: fast. Each libmalloc report is one sub-``PIPE_BUF`` write, which pipes
#: deliver atomically, so a line never straddles two reads.
_FORWARDER_SOURCE = """\
import os, re, signal, sys
for name in ("SIGINT", "SIGQUIT", "SIGTSTP", "SIGTTOU"):
    signal.signal(getattr(signal, name), signal.SIG_IGN)
noise = re.compile(sys.argv[1].encode())
sink_open = True
while chunk := os.read(0, 65536):
    data = memoryview(noise.sub(b"", chunk))
    while sink_open and data:
        try:
            data = data[os.write(1, data):]
        except OSError:
            sink_open = False  # terminal gone: keep draining so writers never block
"""


def strip_malloc_noise(data: bytes) -> bytes:
    """Return ``data`` with every libmalloc "can't turn off" report removed."""
    return _MALLOC_NOISE.sub(b"", data)


def install_malloc_noise_guard() -> bool:
    """Route fd 2 through the noise filter. Returns True when installed.

    A no-op (False) off macOS, when fd 2 is not a terminal (piped or logged
    stderr is not the TUI), or when the forwarder cannot be started, in which
    case fd 2 is left exactly as it was.
    """
    if sys.platform != "darwin" or not sys.executable or not _stderr_is_tty():
        return False
    terminal_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    try:
        os.posix_spawn(
            sys.executable,
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                _FORWARDER_SOURCE,
                MALLOC_NOISE_PATTERN.decode(),
            ],
            os.environ,
            file_actions=[
                (os.POSIX_SPAWN_DUP2, read_fd, 0),
                (os.POSIX_SPAWN_DUP2, terminal_fd, 1),
            ],
        )
    except OSError:
        os.close(terminal_fd)
        return False
    finally:
        os.close(read_fd)
    if sys.stderr is not None:
        sys.stderr.flush()
    os.dup2(write_fd, 2)
    os.close(write_fd)
    _rebind_python_stderr(terminal_fd)
    return True


def _stderr_is_tty() -> bool:
    try:
        return os.isatty(2)
    except OSError:
        return False


def _rebind_python_stderr(terminal_fd: int) -> None:
    """Point ``sys.stderr`` at the terminal, keeping the original's text settings."""
    old = sys.stderr
    new = os.fdopen(
        terminal_fd,
        "w",
        encoding=getattr(old, "encoding", None) or "utf-8",
        errors=getattr(old, "errors", None) or "backslashreplace",
    )
    new.reconfigure(
        line_buffering=getattr(old, "line_buffering", True),
        write_through=getattr(old, "write_through", True),
    )
    sys.stderr = sys.__stderr__ = new
