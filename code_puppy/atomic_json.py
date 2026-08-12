"""Bounded, recoverable I/O for Code Puppy's hand-edited JSON config files.

The JSON counterpart to :mod:`code_puppy.config_file` -- built on the same
:mod:`code_puppy.atomic_io` primitives -- for state files users are expected
to hand-edit (``mcp_servers.json``, ``extra_models.json``, ``spinners.json``,
...). These carry the identical three failure modes the PUP-605 config-file
fix addressed for the INI config: unbounded reads, torn writes, and no
cross-process lock, and are arguably more exposed since they're hand-edited.

Unlike INI config (which is exclusively owned by Code Puppy and safe to
quarantine-and-reset on corruption), a hand-edited JSON file failing to
parse is far more likely to be a *typo the user just made* than bitrot --
silently resetting it to ``{}`` would be a worse outcome than the crash this
module exists to prevent. So corruption here is surfaced to the caller as
:class:`JsonFileCorrupt` rather than auto-quarantined; each call site keeps
its own warn-and-fall-back-to-default behavior on top of that.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from code_puppy import atomic_io

logger = logging.getLogger(__name__)

MAX_JSON_BYTES = atomic_io.DEFAULT_MAX_BYTES
_LOCK_TIMEOUT_SECONDS = atomic_io.DEFAULT_LOCK_TIMEOUT_SECONDS

LockTimeout = atomic_io.LockTimeout


class JsonFileCorrupt(Exception):
    """The file was read successfully but its contents aren't valid JSON."""


def _lock(path: str):
    """Serialize read-modify-write operations on ``path`` across processes."""
    return atomic_io.path_lock(path, timeout=_LOCK_TIMEOUT_SECONDS)


def _read_unlocked(path: str, max_bytes: int) -> Any:
    """Return ``None`` for a missing file, or the parsed JSON value.

    Raises :class:`JsonFileCorrupt` for oversize/decode/parse failures;
    propagates genuine filesystem errors untouched.
    """
    try:
        raw = atomic_io.read_bounded_bytes(path, max_bytes=max_bytes)
    except atomic_io.ContentTooLarge as exc:
        raise JsonFileCorrupt(str(exc)) from exc
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonFileCorrupt(str(exc)) from exc


def load_json(path: str, default: Any = None, max_bytes: int | None = None) -> Any:
    """Load ``path`` as JSON, bounded to ``max_bytes`` before parsing.

    ``max_bytes`` defaults to the current :data:`MAX_JSON_BYTES`, resolved
    at call time rather than baked in as a parameter default, so tests and
    callers can override the module-level bound without threading it
    through every call site.

    Returns ``default`` for a missing file (the caller owns making a fresh
    copy if ``default`` is mutable). Raises :class:`JsonFileCorrupt` for
    oversize/decode/parse failures -- see the module docstring for why this
    doesn't auto-quarantine the way :mod:`code_puppy.config_file` does.
    """
    if max_bytes is None:
        max_bytes = MAX_JSON_BYTES
    parsed = _read_unlocked(path, max_bytes)
    return default if parsed is None else parsed


def mutate_json(
    path: str,
    mutation: Callable[[Any], Any],
    default: Any = None,
    max_bytes: int | None = None,
) -> Any:
    """Apply one locked read-modify-write transaction against JSON at ``path``.

    ``mutation`` receives the current value (``default`` if the file is
    missing) and returns the value to persist -- always written, since JSON
    mutations here are typically cheap dict/list edits rather than a full
    INI re-serialize, so there's no analogous ``False``-skip-the-write
    sentinel like :func:`code_puppy.config_file.mutate_config` has.

    Raises :class:`JsonFileCorrupt` if the existing file can't be parsed --
    unlike the INI config, we never silently discard a hand-edited file the
    user might have just made one typo in. Callers that want the old
    "warn and fall back to an empty file" behavior should catch
    :class:`JsonFileCorrupt` around this call.
    """
    if max_bytes is None:
        max_bytes = MAX_JSON_BYTES
    with _lock(path):
        current = _read_unlocked(path, max_bytes)
        if current is None:
            current = default
        updated = mutation(current)
        atomic_io.atomic_write_bytes(
            path, json.dumps(updated, indent=2, ensure_ascii=False).encode("utf-8")
        )
        return updated
