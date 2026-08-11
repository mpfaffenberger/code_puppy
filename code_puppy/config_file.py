"""Bounded, recoverable I/O for Code Puppy's INI configuration file.

The public helpers in this module keep config-file safety concerns out of the
already-large :mod:`code_puppy.config` module:

* reads are size-bounded before parsing, preventing pathological lines from
  exhausting memory;
* only confirmed content corruption is quarantined -- ordinary I/O failures
  still propagate;
* recovery and writes share a cross-process lock;
* quarantine names are collision-resistant and never overwrite a backup; and
* writes use a same-directory temporary file followed by atomic replacement.
"""

from __future__ import annotations

import configparser
import contextlib
import io
import logging
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)

MAX_CONFIG_BYTES = 10 * 1024 * 1024
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.05

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class ConfigFileCorrupt(Exception):
    """The file was read successfully but its contents are not safe INI."""


class ConfigLockTimeout(TimeoutError):
    """Another process held the config lock beyond the bounded wait."""


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
def _config_lock(path: str) -> Iterator[None]:
    """Serialize recovery and read-modify-write operations across processes."""
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        if msvcrt is not None:
            os.write(fd, b"\0")
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while not (acquired := _try_lock(fd)):
            if time.monotonic() >= deadline:
                raise ConfigLockTimeout(
                    f"Timed out waiting for config lock: {lock_path}"
                )
            time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        if acquired:
            try:
                _unlock(fd)
            except OSError:
                logger.debug(
                    "Failed to release config lock %s", lock_path, exc_info=True
                )
        os.close(fd)


def _read_unlocked(path: str) -> configparser.ConfigParser:
    """Read and parse a bounded snapshot; propagate filesystem failures."""
    parser = configparser.ConfigParser()
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return parser
    if size > MAX_CONFIG_BYTES:
        raise ConfigFileCorrupt(
            f"config is {size} bytes; maximum is {MAX_CONFIG_BYTES} bytes"
        )

    try:
        with open(path, "rb") as file:
            raw = file.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return parser
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigFileCorrupt(f"config exceeds {MAX_CONFIG_BYTES} bytes")

    try:
        text = raw.decode("utf-8")
        if text:
            parser.read_string(text, source=path)
    except (UnicodeDecodeError, configparser.Error) as exc:
        raise ConfigFileCorrupt(str(exc)) from exc
    return parser


def _quarantine_unlocked(path: str) -> str:
    """Move a confirmed-corrupt file aside without overwriting prior backups."""
    for _ in range(10):
        quarantine_path = f"{path}.corrupted-{time.time_ns()}-{uuid.uuid4().hex}"
        try:
            # Hard-link creation is atomic and refuses to overwrite an existing
            # destination. Unlink only after the backup exists, so any failure
            # leaves the original user data in place.
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
    raise FileExistsError("Could not allocate a unique config quarantine path")


def load_config(path: str) -> configparser.ConfigParser:
    """Load config, quarantining only confirmed content corruption.

    A second read under the process lock closes the read/quarantine TOCTOU
    window between cooperating Code Puppy processes. If another process fixed
    or replaced the file first, its healthy version wins and is returned.
    Filesystem errors and genuine ``MemoryError`` conditions propagate; neither
    proves that user data is corrupt.
    """
    try:
        return _read_unlocked(path)
    except ConfigFileCorrupt as first_error:
        with _config_lock(path):
            try:
                return _read_unlocked(path)
            except ConfigFileCorrupt as confirmed_error:
                quarantine_path = _quarantine_unlocked(path)
                logger.warning(
                    "Corrupted config %s was quarantined to %s: %s",
                    path,
                    quarantine_path,
                    confirmed_error or first_error,
                )
                return configparser.ConfigParser()


def _atomic_write_unlocked(path: str, parser: configparser.ConfigParser) -> None:
    """Durably replace ``path`` with serialized config from a temp file."""
    buffer = io.StringIO()
    parser.write(buffer)
    target = os.path.realpath(path)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)

    mode = None
    try:
        mode = os.stat(target).st_mode
    except OSError:
        pass

    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".puppy.cfg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(buffer.getvalue())
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


def mutate_config(
    path: str, mutation: Callable[[configparser.ConfigParser], bool | None]
) -> configparser.ConfigParser:
    """Apply one locked read-modify-write transaction.

    ``mutation`` may return ``False`` to skip an unnecessary write. A corrupt
    file is quarantined while the same lock remains held; if quarantine fails,
    the exception propagates and the mutation is never written over user data.
    """
    with _config_lock(path):
        try:
            parser = _read_unlocked(path)
        except ConfigFileCorrupt as exc:
            quarantine_path = _quarantine_unlocked(path)
            logger.warning(
                "Corrupted config %s was quarantined to %s: %s",
                path,
                quarantine_path,
                exc,
            )
            parser = configparser.ConfigParser()
        should_write = mutation(parser)
        if should_write is not False:
            _atomic_write_unlocked(path, parser)
        return parser
