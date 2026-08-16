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
marker file in the config dir. Originals are never deleted: migrated pickles
move to ``<dir>/pre_v2_backup/``, failures to ``<dir>/pre_v2_backup/failed/``.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from typing import Iterable, Optional

from code_puppy.session_surrogate_unpickler import (
    load_surrogate_pickle,
    normalize_history,
    to_jsonable,
)

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
    """Move a migrated pickle into its directory's ``pre_v2_backup/``."""
    try:
        _move_to(pkl_path, pkl_path.parent / _BACKUP_DIRNAME)
    except OSError:
        # Leaving the pickle behind is harmless: loads prefer the JSON twin.
        pass


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


def sweep_legacy_pickle_sessions() -> None:
    """One-time startup sweep: migrate every known ``.pkl`` session to JSON.

    Idempotent via a marker file; per-file failures are warned about,
    quarantined, and never abort the sweep. Never raises (best-effort at
    startup, same policy as ``session_migration.sweep_contexts_to_autosaves``).
    """
    try:
        marker = _marker_path()
        if marker.exists():
            return

        migrated = 0
        failed = 0
        for directory in _sweep_directories():
            if not directory.is_dir():
                continue
            for pkl_path in sorted(directory.glob("*.pkl")):
                if pkl_path.with_suffix(".json").exists():
                    continue  # JSON twin already present; nothing to do.
                result = migrate_pickle_file(pkl_path)
                if result.success:
                    migrated += 1
                    archive_legacy_pickle(pkl_path)
                else:
                    failed += 1
                    _emit_warning_safely(
                        f"Could not migrate session file {pkl_path.name}: "
                        f"{result.error} (moved to {_BACKUP_DIRNAME}/failed/)"
                    )
                    quarantine_failed_pickle(pkl_path)

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

        if migrated or failed:
            _emit_info_safely(
                f"Session format migration: {migrated} migrated to JSON, "
                f"{failed} failed (originals kept under {_BACKUP_DIRNAME}/)."
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
