"""One-time migration of legacy pickle sessions to the v2 JSON envelope.

Follows the precedent of :mod:`code_puppy.session_migration` (which moves
session *locations*); this module migrates session *format*: ``<name>.pkl``
pickles become ``<name>.json`` envelopes readable by
``session_storage.read_envelope_file``.

The heavy lifting -- unpickling WITHOUT importing pydantic-ai classes --
lives in :mod:`code_puppy.session_surrogate_unpickler`. This module is the
caller/validation layer: it round-trips the normalized messages through
``ModelMessagesTypeAdapter`` (lazily imported via ``session_storage``) before
declaring a migration successful.

Startup entry point is :func:`sweep_legacy_pickle_sessions`, idempotent via a
marker file in the config dir. Originals are never deleted or moved on a
successful migration -- the ``.pkl`` stays next to its new ``.json`` twin so
an older code_puppy version can still find it after a downgrade. Only
unmigratable pickles are relocated, to ``<dir>/pre_v2_backup/failed/``.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from code_puppy.session_surrogate_unpickler import (
    load_surrogate_pickle,
    normalize_history,
    to_jsonable,
)

logger = logging.getLogger(__name__)

_MARKER_FILENAME = ".session_format_v2_migrated"
_BACKUP_DIRNAME = "pre_v2_backup"


@dataclass(slots=True)
class MigrationResult:
    success: bool
    json_path: Optional[pathlib.Path] = None
    error: Optional[str] = None


def migrate_pickle_file(
    pkl_path: pathlib.Path, json_path: Optional[pathlib.Path] = None
) -> MigrationResult:
    """Migrate one legacy pickle into a sibling ``.json`` envelope.

    Handles both raw-pickle payloads and the legacy ``CPSESSION\\x01`` signed
    framing. On success the envelope is written atomically and the metadata
    sidecar's ``file_path`` is repointed at the JSON file. The original
    pickle is left untouched (callers decide whether/where to archive it).
    """
    from code_puppy import session_storage

    pkl_path = pathlib.Path(pkl_path)
    if json_path is None:
        json_path = pkl_path.with_suffix(".json")

    try:
        payload = session_storage._extract_pickle_payload(pkl_path.read_bytes())
        history, had_surrogates = load_surrogate_pickle(payload)

        if not isinstance(history, (list, tuple)):
            return MigrationResult(
                success=False,
                error=f"payload is {type(history).__name__}, expected a list",
            )

        if had_surrogates:
            messages = normalize_history(history)
            # Validation layer: only declare success once the real adapter
            # can round-trip what the normalizer built.
            session_storage.validate_messages_jsonable(messages)
            envelope = session_storage.build_envelope_from_messages(
                messages, encoding=session_storage.ENCODING_MESSAGES
            )
        else:
            # Pure-builtin payload (e.g. plugin histories of plain dicts):
            # store verbatim when possible, else best-effort jsonable.
            messages = list(history)
            try:
                json.dumps(messages)
            except (TypeError, ValueError):
                messages = [to_jsonable(item) for item in messages]
            envelope = session_storage.build_envelope_from_messages(
                messages, encoding=session_storage.ENCODING_JSON
            )

        session_storage.write_envelope_file(json_path, envelope)
        _repoint_meta_sidecar(pkl_path, json_path)
        return MigrationResult(success=True, json_path=json_path)
    except Exception as exc:  # noqa: BLE001 - per-file failure must not raise
        return MigrationResult(success=False, error=repr(exc))


def _repoint_meta_sidecar(pkl_path: pathlib.Path, json_path: pathlib.Path) -> None:
    """Update ``<stem>_meta.json`` ``file_path`` to the new JSON file."""
    meta_path = pkl_path.with_name(f"{pkl_path.stem}_meta.json")
    if not meta_path.exists():
        return
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        data["file_path"] = str(json_path)
        tmp_path = meta_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(meta_path)
    except Exception:
        # Sidecar refresh is cosmetic; the envelope is the source of truth.
        pass


def _move_to(pkl_path: pathlib.Path, dest_dir: pathlib.Path) -> None:
    """Move ``pkl_path`` into ``dest_dir`` without ever overwriting."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / pkl_path.name
    counter = 1
    while destination.exists():
        destination = dest_dir / f"{pkl_path.stem}.{counter}{pkl_path.suffix}"
        counter += 1
    os.replace(str(pkl_path), str(destination))


def archive_legacy_pickle(pkl_path: pathlib.Path) -> None:
    """No-op: a successfully migrated pickle is left at ``pkl_path``.

    Moving it out of the session directory (the old behavior) hid it from
    any older code_puppy version's loader -- which only ever looks for
    ``<name>.pkl`` next to the session, never in a backup subfolder -- so a
    downgrade after migration looked like data loss even though nothing was
    deleted. Leaving the original in place keeps downgrades working; the
    current version already prefers the JSON twin (see ``load_session``), so
    the leftover ``.pkl`` is otherwise inert.
    """


def quarantine_failed_pickle(pkl_path: pathlib.Path) -> None:
    """Move an unmigratable pickle into ``pre_v2_backup/failed/``."""
    try:
        _move_to(pkl_path, pkl_path.parent / _BACKUP_DIRNAME / "failed")
    except OSError:
        pass


def _sweep_directories() -> Iterable[pathlib.Path]:
    """Every directory that may hold legacy session pickles."""
    from code_puppy.config import AUTOSAVE_DIR, CONTEXTS_DIR, DATA_DIR

    autosaves = pathlib.Path(AUTOSAVE_DIR)
    return (
        autosaves,
        autosaves / "acp",  # ACP plugin sessions reuse session_storage
        pathlib.Path(CONTEXTS_DIR),
        pathlib.Path(DATA_DIR) / "subagent_sessions",
    )


def _marker_path() -> pathlib.Path:
    from code_puppy.config import CONFIG_DIR

    return pathlib.Path(CONFIG_DIR) / _MARKER_FILENAME


def _migrate_directory(directory: pathlib.Path) -> Tuple[int, int]:
    """Migrate every ``.pkl`` in ``directory``; returns ``(migrated, failed)``."""
    migrated = 0
    failed = 0
    for pkl_path in sorted(directory.glob("*.pkl")):
        if pkl_path.with_suffix(".json").exists():
            continue  # JSON twin already present; nothing to do.
        result = migrate_pickle_file(pkl_path)
        if result.success:
            migrated += 1
            archive_legacy_pickle(pkl_path)
        else:
            failed += 1
            logger.debug(
                "Could not migrate session file %s: %s (quarantined)",
                pkl_path,
                result.error,
            )
            quarantine_failed_pickle(pkl_path)
    return migrated, failed


def _retry_quarantined(directory: pathlib.Path) -> Tuple[int, int]:
    """Retry ``pre_v2_backup/failed/*.pkl``; returns ``(rescued, stuck)``.

    Runs even when the sweep marker exists (cheap: only when ``failed/``
    is non-empty) so unpickler fixes retroactively rescue quarantined
    sessions. Rescued pickles graduate to ``pre_v2_backup/`` proper;
    repeat failures stay put with debug-only logging -- no warning spam.
    """
    failed_dir = directory / _BACKUP_DIRNAME / "failed"
    if not failed_dir.is_dir():
        return 0, 0
    rescued = 0
    stuck = 0
    for pkl_path in sorted(failed_dir.glob("*.pkl")):
        json_path = directory / pkl_path.with_suffix(".json").name
        if json_path.exists():
            logger.debug("Skipping quarantined %s: JSON twin already exists", pkl_path)
            continue
        result = migrate_pickle_file(pkl_path, json_path)
        if result.success:
            rescued += 1
            # Sidecar (if any) lives in the sessions dir, not failed/.
            _repoint_meta_sidecar(directory / pkl_path.name, json_path)
            archive_legacy_pickle_from_quarantine(pkl_path, directory)
        else:
            stuck += 1
            logger.debug(
                "Quarantined session %s still unmigratable: %s",
                pkl_path,
                result.error,
            )
    return rescued, stuck


def archive_legacy_pickle_from_quarantine(
    pkl_path: pathlib.Path, directory: pathlib.Path
) -> None:
    """Graduate a rescued pickle from ``failed/`` to ``pre_v2_backup/``."""
    try:
        _move_to(pkl_path, directory / _BACKUP_DIRNAME)
    except OSError:
        pass


def sweep_legacy_pickle_sessions() -> None:
    """Startup sweep: migrate every known ``.pkl`` session to JSON.

    The main sweep is one-time (marker file); the quarantine-retry pass is
    self-healing and runs every startup. Per-file failures are quarantined
    with debug-level detail and summarized in a single warning; the sweep
    never raises (best-effort at startup, same policy as
    ``session_migration.sweep_contexts_to_autosaves``).
    """
    try:
        directories = [d for d in _sweep_directories() if d.is_dir()]

        migrated = 0
        failed = 0
        marker = _marker_path()
        if not marker.exists():
            for directory in directories:
                dir_migrated, dir_failed = _migrate_directory(directory)
                migrated += dir_migrated
                failed += dir_failed
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()

        rescued = 0
        for directory in directories:
            dir_rescued, _stuck = _retry_quarantined(directory)
            rescued += dir_rescued

        if failed:
            _emit_warning_safely(
                f"{failed} session(s) could not be migrated and were "
                f"quarantined to {_BACKUP_DIRNAME}/failed/ -- run with debug "
                "logging for details."
            )
        if migrated or failed:
            _emit_info_safely(
                f"Session format migration: {migrated} migrated to JSON "
                f"(original .pkl left in place), {failed} failed "
                f"(quarantined under {_BACKUP_DIRNAME}/failed/)."
            )
        if rescued:
            _emit_info_safely(
                f"Recovered {rescued} previously quarantined session(s) "
                f"from {_BACKUP_DIRNAME}/failed/."
            )
    except Exception as exc:  # pragma: no cover - defensive
        try:
            from code_puppy.error_logging import log_error_message

            log_error_message(
                f"Session format sweep aborted: {exc!r}",
                context="session_format_migration.sweep_legacy_pickle_sessions",
            )
        except Exception:
            pass


def _emit_info_safely(message: str) -> None:
    try:
        from code_puppy.messaging import emit_info

        emit_info(message)
    except Exception:
        pass


def _emit_warning_safely(message: str) -> None:
    try:
        from code_puppy.messaging import emit_warning

        emit_warning(message)
    except Exception:
        pass
