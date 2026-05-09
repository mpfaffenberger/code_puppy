"""Atomic private file storage helpers for sensitive data.

Implements fail-closed helpers that create files with restrictive permissions
from the start, fsync before rename, and warn when existing files are too
broadly permissioned.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ensure_private_dir(path: Path) -> Path:
    """Create *path* (and parents) with mode ``0o700``.

    If the directory already exists its mode is corrected if necessary.
    """
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def atomic_write_private_bytes(path: Path, data: bytes) -> None:
    """Atomically write *data* to *path* with mode ``0o600``.

    Uses a temporary sibling file created with ``O_CREAT | O_EXCL`` so there
    is no race window where another observer can open the file before the
    mode is set.  After writing, ``fsync`` flushes data to disk and
    ``os.replace`` atomically moves the temp file into place.
    """
    tmp_path = Path(str(path) + ".tmp")
    fd: int | None = None
    try:
        fd = os.open(
            str(tmp_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.write(fd, data)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)
    os.replace(str(tmp_path), path)


def atomic_write_private_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write a JSON object to *path* with mode ``0o600``."""
    payload = json.dumps(data, indent=2).encode("utf-8")
    atomic_write_private_bytes(path, payload)


def warn_or_fix_private_file_mode(path: Path, expected_mode: int = 0o600) -> None:
    """Check *path* permissions and fix them if they are too broad.

    Emits a warning when the mode differs from *expected_mode* so operators
    know the file was created by an older version or another process.
    """
    if not path.exists():
        return
    current_mode = stat.S_IMODE(path.stat().st_mode)
    if current_mode != expected_mode:
        logger.warning(
            "File %s has mode %04o; fixing to %04o",
            path,
            current_mode,
            expected_mode,
        )
        path.chmod(expected_mode)
