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
import errno
import logging
import os
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


def _truncate_fd(fd: int, size: int) -> None:
    """Best-effort fd truncation across Python/OS builds.

    ``os.ftruncate`` is absent on some Windows Python builds. Fall back to
    truncating through a duplicated file object when needed.
    """
    ftruncate = getattr(os, "ftruncate", None)
    if callable(ftruncate):
        try:
            ftruncate(fd, size)
            return
        except NotImplementedError:
            pass
        except OSError as exc:
            if exc.errno != errno.ENOSYS:
                raise

    dup_fd = os.dup(fd)
    try:
        file = os.fdopen(dup_fd, "r+b", buffering=0)
    except BaseException:
        os.close(dup_fd)
        raise
    with file:
        file.truncate(size)


def _prepare_windows_lockfile(fd: int) -> None:
    """Normalize the Windows lock sidecar to exactly one byte.

    ``msvcrt.locking`` requires at least one byte to lock. Keep the sidecar at
    one byte so repeated acquisitions cannot balloon it over time.

    Call this only while holding the lock for this file descriptor.
    """
    os.lseek(fd, 0, os.SEEK_SET)
    if os.fstat(fd).st_size != 1:
        _truncate_fd(fd, 1)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)


def _prime_windows_lockfile_if_empty(fd: int) -> None:
    """Seed a zero-length Windows sidecar with one byte, best effort.

    ``msvcrt.locking`` can reject locking byte 0 of an empty file on some
    runtimes. This helper initializes only truly empty sidecars and swallows
    contention/share-violation errors so lock polling semantics stay intact.
    """
    os.lseek(fd, 0, os.SEEK_SET)
    if os.fstat(fd).st_size != 0:
        return

    try:
        os.write(fd, b"\0")
    except OSError:
        pass
    finally:
        os.lseek(fd, 0, os.SEEK_SET)


@contextlib.contextmanager
def path_lock(
    path: str, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS
) -> Iterator[None]:
    """Cross-process advisory lock scoped to a ``{path}.lock`` sidecar file.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows. Raises
    :class:`LockTimeout` rather than blocking forever if another process
    (or another lock held by this same process) doesn't release in time.
    """
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        if msvcrt is not None:
            _prime_windows_lockfile_if_empty(fd)
        deadline = time.monotonic() + timeout
        while not (acquired := _try_lock(fd)):
            if msvcrt is not None:
                _prime_windows_lockfile_if_empty(fd)
            if time.monotonic() >= deadline:
                raise LockTimeout(f"Timed out waiting for lock: {lock_path}")
            time.sleep(_LOCK_POLL_SECONDS)

        if msvcrt is not None:
            _prepare_windows_lockfile(fd)
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


# errno values from link(2) that mean a hard link is genuinely impossible on
# this filesystem -- NOT a permission/policy decision we should silently
# bypass. Anything else (notably EACCES = permission denied) is surfaced
# unchanged so a real filesystem restriction is never quietly circumvented.
_LINK_UNSUPPORTED_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ENOSYS", None),  # link() not implemented (e.g. Android/bionic)
        getattr(errno, "EPERM", None),  # link(2): fs lacks hard-link support
        getattr(errno, "EOPNOTSUPP", None),  # operation not supported by filesystem
        getattr(errno, "EMLINK", None),  # source's link count is already maxed out
        getattr(errno, "EXDEV", None),  # cross-device (shouldn't occur: sibling dest)
    )
    if value is not None
)


def _create_quarantine_copy(src: str, dst: str) -> None:
    """Exclusive-create copy fallback for platforms/filesystems without a
    usable ``os.link`` (e.g. Android/Termux, where ``os.link`` is absent).

    Preserves the guarantees that matter for quarantine -- but NOT perfect
    hard-link identity:

    * **no-overwrite** -- ``O_CREAT | O_EXCL`` makes creation atomic and
      raises :class:`FileExistsError` (never clobbers an existing backup),
      the identical signal ``os.link`` raises;
    * **byte integrity** -- the whole source is streamed with fd-level
      ``os.read`` in bounded chunks (memory never balloons), and every
      ``os.write`` is looped until the entire buffer is accepted (a single
      ``os.write`` may write only part of the buffer);
    * **permissions** -- the source's permission bits are copied to the backup;
    * **rollback / no-data-loss** -- ``dst`` is fully written and ``fsync``ed
      before this returns, so the caller only unlinks the original once a
      durable backup exists; on *any* failure the partial ``dst`` is removed,
      every fd is closed, and the error is re-raised with the source untouched.

    Unlike a hard link this creates a NEW inode: link count, inode identity,
    ownership, and timestamps are NOT reproduced -- only data and mode are.
    """
    mode = os.stat(src).st_mode & 0o777
    # O_EXCL => atomic no-overwrite; raises FileExistsError like os.link.
    dst_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    dst_closed = False
    try:
        src_fd = os.open(src, os.O_RDONLY)
        try:
            while True:
                chunk = os.read(src_fd, 64 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    # os.write may accept only part of the buffer; loop until
                    # the entire chunk has been handed to the kernel.
                    view = view[os.write(dst_fd, view) :]
        finally:
            os.close(src_fd)
        os.fsync(dst_fd)
        os.close(dst_fd)
        dst_closed = True
    except BaseException:
        if not dst_closed:
            try:
                os.close(dst_fd)
            except OSError:
                pass
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise
    # Creation mode can be trimmed by umask; pin it back to the source mode.
    try:
        os.chmod(dst, mode)
    except OSError:
        pass


def _hardlink_or_copy(src: str, dst: str) -> None:
    """Create ``dst`` as an exclusive backup of ``src``.

    Prefers ``os.link`` (atomic, shares the inode, refuses to overwrite).
    Where hard links are unavailable (``os.link`` missing, e.g. Android) or
    unsupported by the filesystem, falls back to an exclusive-create copy
    with the same no-overwrite / no-data-loss guarantees.
    :class:`FileExistsError` always propagates so the caller's retry loop
    picks a fresh name instead of clobbering an existing backup.
    """
    link = getattr(os, "link", None)
    if link is not None:
        try:
            link(src, dst)
            return
        except FileExistsError:
            raise
        except OSError as exc:
            if exc.errno not in _LINK_UNSUPPORTED_ERRNOS:
                raise
            # hard links unsupported here -- fall through to the copy path
    _create_quarantine_copy(src, dst)


def quarantine_file(path: str) -> str:
    """Move a confirmed-corrupt file aside without ever losing user data.

    Creates the backup with :func:`_hardlink_or_copy` -- a hard link where
    supported (atomic, refuses to overwrite an existing destination), or an
    exclusive-create copy fallback with the same guarantees on platforms
    without a usable ``os.link`` (e.g. Android/Termux). The original is only
    ``os.unlink``ed *after* its backup safely exists, retried with fresh
    collision-resistant names so concurrent/rapid recoveries never clobber
    each other's backup and the original is never deleted before its backup
    safely exists.
    """
    for _ in range(10):
        quarantine_path = f"{path}.corrupted-{time.time_ns()}-{uuid.uuid4().hex}"
        try:
            _hardlink_or_copy(path, quarantine_path)
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
        mode = os.stat(target).st_mode
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
