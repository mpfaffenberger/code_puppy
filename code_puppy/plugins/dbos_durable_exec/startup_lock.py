"""Cross-process startup serialization for the DBOS durable-exec plugin.

Multiple Code Puppy instances launched at the same instant (e.g. several
Zellij panes each spawning their own process) all open the *same* shared
DBOS SQLite system database and run schema migration + workflow recovery
during ``DBOS.launch()``. SQLite is single-writer, so the racers collide on
the write lock, and the losers either raise ``database is locked`` (or an
Alembic migration conflict) and disable durable execution -- or, on older
builds, exit the whole process with code 1.

This module provides:

* :func:`interprocess_lock` -- a cross-platform advisory file lock so that
  DBOS initialization happens one process at a time. Late starters *wait*
  for the lock instead of racing the migration.
* :func:`enable_sqlite_wal` -- flips the shared SQLite database into WAL
  journal mode (a persistent, header-level setting) so that, once
  initialized, concurrent reads/writes are far less likely to block.

Both helpers fail soft: locking and PRAGMA tuning are best-effort
optimizations, never correctness requirements, so any platform quirk
degrades to the previous (racy) behavior rather than blocking startup.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from typing import Iterator

# Platform-specific locking primitives. We deliberately avoid adding a
# third-party dependency (filelock/portalocker) since the stdlib already
# gives us everything on both POSIX and Windows.
try:  # POSIX
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    _HAVE_FCNTL = False

try:  # Windows
    import msvcrt

    _HAVE_MSVCRT = True
except ImportError:  # pragma: no cover - POSIX
    _HAVE_MSVCRT = False


def _try_acquire(fd: int) -> bool:
    """Attempt a single non-blocking exclusive lock on ``fd``.

    Returns True on success, False if the lock is currently held elsewhere.
    """
    if _HAVE_FCNTL:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    if _HAVE_MSVCRT:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    # No locking primitive available: behave as if always acquired.
    return True


def _release(fd: int) -> None:
    """Best-effort release of a lock previously taken on ``fd``."""
    try:
        if _HAVE_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_UN)
        elif _HAVE_MSVCRT:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextlib.contextmanager
def interprocess_lock(lock_path: str, timeout: float = 30.0) -> Iterator[bool]:
    """Hold a cross-process advisory lock for the duration of the block.

    Serializes a critical section across separate Code Puppy processes. Late
    arrivals poll until the holder releases or ``timeout`` seconds elapse.

    Yields:
        True if the lock was actually acquired, False if it timed out (the
        caller still runs -- we never want a cosmetic lock to *prevent*
        startup, only to order it when possible).
    """
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    fd = None
    acquired = False
    try:
        # Windows requires a real byte in the file to lock a region.
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        if _HAVE_MSVCRT:
            try:
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
            except OSError:
                pass

        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            if _try_acquire(fd):
                acquired = True
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)

        yield acquired
    finally:
        if fd is not None:
            if acquired:
                _release(fd)
            try:
                os.close(fd)
            except OSError:
                pass


def enable_sqlite_wal(sqlite_path: str) -> None:
    """Switch the shared SQLite DB to WAL journal mode (best effort).

    WAL is a persistent, header-level setting, so a single successful call
    sticks for every future connection (including DBOS's own engine). It lets
    readers and a writer coexist, dramatically reducing ``database is locked``
    errors at runtime. Failures are swallowed -- this is pure optimization.
    """
    try:
        import sqlite3
    except ImportError:  # pragma: no cover - sqlite3 is stdlib
        return

    try:
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
        # busy_timeout here only affects *this* connection, but WAL is what
        # we actually persist. timeout keeps this probe from hanging.
        conn = sqlite3.connect(sqlite_path, timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - cosmetic optimization, fail soft
        # Surface a hint in debug mode but never block startup.
        if os.environ.get("CODE_PUPPY_DEBUG"):
            sys.stderr.write(f"[dbos_durable_exec] WAL setup skipped: {exc}\n")
