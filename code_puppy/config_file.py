"""Bounded, recoverable I/O for Code Puppy's INI configuration file.

The public helpers in this module keep config-file safety concerns out of the
already-large :mod:`code_puppy.config` module. Built on the generic
primitives in :mod:`code_puppy.atomic_io`:

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
import io
import logging
from collections.abc import Callable

from code_puppy import atomic_io

logger = logging.getLogger(__name__)

MAX_CONFIG_BYTES = atomic_io.DEFAULT_MAX_BYTES
_LOCK_TIMEOUT_SECONDS = atomic_io.DEFAULT_LOCK_TIMEOUT_SECONDS

# Re-exported for backwards compatibility -- callers (and this module's own
# tests) historically imported the lock timeout error from here.
ConfigLockTimeout = atomic_io.LockTimeout


class ConfigFileCorrupt(Exception):
    """The file was read successfully but its contents are not safe INI."""


def _config_lock(path: str):
    """Serialize recovery and read-modify-write operations across processes."""
    return atomic_io.path_lock(path, timeout=_LOCK_TIMEOUT_SECONDS)


def _read_unlocked(path: str) -> configparser.ConfigParser:
    """Read and parse a bounded snapshot; propagate filesystem failures."""
    parser = configparser.ConfigParser()
    try:
        raw = atomic_io.read_bounded_bytes(path, max_bytes=MAX_CONFIG_BYTES)
    except atomic_io.ContentTooLarge as exc:
        raise ConfigFileCorrupt(str(exc)) from exc

    try:
        text = raw.decode("utf-8")
        if text:
            parser.read_string(text, source=path)
    except (UnicodeDecodeError, configparser.Error) as exc:
        raise ConfigFileCorrupt(str(exc)) from exc
    return parser


def _quarantine_unlocked(path: str) -> str:
    return atomic_io.quarantine_file(path)


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
    atomic_io.atomic_write_bytes(path, buffer.getvalue().encode("utf-8"))


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
