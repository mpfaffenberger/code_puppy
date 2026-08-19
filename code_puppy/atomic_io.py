"""Generic, cross-process-safe primitives for user-editable config files.

Extracted from :mod:`code_puppy.config_file` (the PUP-605 config-corruption
fix) so every corner of the config surface -- not just the INI file -- gets
the same three guarantees for free:

* **bounded reads** -- a pathological/oversized file can never balloon
  memory the way it did in the original ``MemoryError`` field report;
* **one cross-process lock per path** -- concurrent readers/writers on the
  same file (two terminals, a wizard + a slash-command) serialize instead
  of racing; and
* **atomic writes** -- same-directory temp file + ``fsync`` + ``os.replace``,
  so a crash mid-write can never leave a half-written file behind.

:mod:`code_puppy.config_file` (INI) and :mod:`code_puppy.atomic_json` (JSON)
both build their format-specific ``load_x``/``mutate_x`` helpers on top of
these primitives. New config-file-shaped state should use one of those two
modules rather than hand-rolling ``open()``/``json.load()`` again.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import tempfile
import time
import uuid
from collections.abc import Iterator

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.05

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class ContentTooLarge(Exception):
    """A file exceeded the caller's byte budget, before or during a read."""


class LockTimeout(TimeoutError):
    """Another process held the path lock beyond the bounded wait."""


def _try_lock(fd: int) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    if msvcrt is not None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    return True


def _unlock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def path_lock(
    path: str, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS
) -> Iterator[None]:
    """Cross-process advisory lock scoped to a ``{path}.lock`` sidecar file.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows. Raises
    :class:`LockTimeout` rather than blocking forever if another process
    (or another lock held by this same process) doesn't release in time.

    Not reentrant: ``flock`` is scoped per *open file description*, not per
    process or thread, so a second ``path_lock(path)`` (directly, or via
    ``mutate_config``/``mutate_json`` on the same ``path``) taken from
    *inside* an already-held lock on that same path will not recognize the
    outer lock as "ours" -- it will block for the full ``timeout`` and then
    raise :class:`LockTimeout`, rather than deadlock forever, but still not
    proceed. Do not call ``mutate_config``/``mutate_json`` for a path from
    within a ``mutation``/``mutate`` callback already locking that path.
    """
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        if msvcrt is not None:
            os.write(fd, b"\0")
        deadline = time.monotonic() + timeout
        while not (acquired := _try_lock(fd)):
            if time.monotonic() >= deadline:
                raise LockTimeout(f"Timed out waiting for lock: {lock_path}")
            time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        if acquired:
            try:
                _unlock(fd)
            except OSError:
                logger.debug("Failed to release lock %s", lock_path, exc_info=True)
        os.close(fd)


def read_bounded_bytes(path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """Read at most ``max_bytes`` from ``path``.

    Returns ``b""`` for a missing file. Raises :class:`ContentTooLarge` if
    the file is (or turns out to be, past a lying ``stat`` size) larger than
    ``max_bytes`` -- without ever buffering more than ``max_bytes + 1`` bytes
    into memory. This bound is the actual fix for the original field report:
    stdlib ``configparser``'s buffered line reader ballooning memory on one
    pathological giant line can only happen if the whole line reaches it
    first, and it never does now.
    """
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return b""
    if size > max_bytes:
        raise ContentTooLarge(f"{path} is {size} bytes; maximum is {max_bytes} bytes")

    try:
        with open(path, "rb") as file:
            raw = file.read(max_bytes + 1)
    except FileNotFoundError:
        return b""
    if len(raw) > max_bytes:
        raise ContentTooLarge(f"{path} exceeds {max_bytes} bytes")
    return raw


def quarantine_file(path: str) -> str:
    """Move a confirmed-corrupt file aside without ever losing user data.

    Uses ``os.link`` (atomic, refuses to overwrite an existing destination)
    followed by ``os.unlink`` of the original, retried with fresh
    collision-resistant names so concurrent/rapid recoveries never clobber
    each other's backup and the original is never deleted before its backup
    safely exists.
    """
    for _ in range(10):
        quarantine_path = f"{path}.corrupted-{time.time_ns()}-{uuid.uuid4().hex}"
        try:
            os.link(path, quarantine_path)
        except FileExistsError:
            continue
        try:
            os.unlink(path)
        except BaseException:
            try:
                os.unlink(quarantine_path)
            except OSError:
                pass
            raise
        return quarantine_path
    raise FileExistsError(f"Could not allocate a unique quarantine path for {path}")


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Durably replace ``path``'s contents.

    Writes to a same-directory temp file, ``fsync``s it, then ``os.replace``s
    it over the target -- so a crash mid-write can never leave a truncated
    or half-written file behind, and preserves the original file's
    permission bits.
    """
    target = os.path.realpath(path)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)

    mode = None
    try:
        mode = stat.S_IMODE(os.stat(target).st_mode)
    except OSError:
        pass

    prefix = f".{os.path.basename(target)}-"
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, target)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
