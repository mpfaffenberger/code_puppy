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

Startup entry point is :func:`sweep_legacy_pickle_sessions`: time-boxed,
resumable across startups, and complete once a marker file is written in the
config dir. Originals are never deleted: migrated pickles move to
``<dir>/pre_v2_backup/``, failures to ``<dir>/pre_v2_backup/failed/`` (retried
at most once per release).
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from code_puppy.session_surrogate_unpickler import (
    load_surrogate_pickle,
    normalize_history,
    to_jsonable,
)

logger = logging.getLogger(__name__)

_MARKER_FILENAME = ".session_format_v2_migrated"
_BACKUP_DIRNAME = "pre_v2_backup"
_RETRY_STATE_FILENAME = ".retry_state.json"

# The startup sweep is time-boxed so a huge legacy session store can never
# keep the prompt from appearing. Override with this env var (seconds; 0
# skips the startup sweep entirely -- sessions still migrate lazily on load).
_BUDGET_ENV = "CODE_PUPPY_SESSION_MIGRATION_BUDGET_SECONDS"
_DEFAULT_BUDGET_SECONDS = 10.0
# Only announce the sweep when it is big enough to be noticeable.
_ANNOUNCE_THRESHOLD = 25


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


def _move_to(pkl_path: pathlib.Path, dest_dir: pathlib.Path) -> pathlib.Path:
    """Move ``pkl_path`` into ``dest_dir`` without ever overwriting.

    Returns the destination actually used (collisions get a ``.N`` suffix).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / pkl_path.name
    counter = 1
    while destination.exists():
        destination = dest_dir / f"{pkl_path.stem}.{counter}{pkl_path.suffix}"
        counter += 1
    os.replace(str(pkl_path), str(destination))
    return destination


def archive_legacy_pickle(pkl_path: pathlib.Path) -> None:
    """Move a migrated pickle into its directory's ``pre_v2_backup/``."""
    try:
        _move_to(pkl_path, pkl_path.parent / _BACKUP_DIRNAME)
    except OSError:
        # Leaving the pickle behind is harmless: loads prefer the JSON twin.
        pass


def quarantine_failed_pickle(pkl_path: pathlib.Path) -> Optional[pathlib.Path]:
    """Move an unmigratable pickle into ``pre_v2_backup/failed/``.

    Returns the quarantined path, or ``None`` if the move failed.
    """
    try:
        return _move_to(pkl_path, pkl_path.parent / _BACKUP_DIRNAME / "failed")
    except OSError:
        return None


def _sweep_directories() -> Iterable[pathlib.Path]:
    """Every directory that may hold legacy session pickles.

    Ordered by importance: user-facing sessions first, bulky internal
    sub-agent sessions last, so a time-limited sweep spends its budget on
    the sessions people actually resume.
    """
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


def _monotonic() -> float:
    return time.monotonic()


def _migrator_version() -> str:
    """Identifier of the code that decides whether a pickle is migratable."""
    from code_puppy import __version__

    return str(__version__)


def _startup_budget_seconds() -> float:
    """Wall-clock budget for the startup sweep (env-overridable; 0 = skip)."""
    raw = os.environ.get(_BUDGET_ENV)
    if raw is None:
        return _DEFAULT_BUDGET_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_BUDGET_SECONDS
    if value != value or value < 0:  # NaN or negative
        return _DEFAULT_BUDGET_SECONDS
    return value


class _Budget:
    """Deadline shared by every phase of one startup sweep."""

    def __init__(self, seconds: float) -> None:
        self._deadline = _monotonic() + seconds

    def exhausted(self) -> bool:
        return _monotonic() >= self._deadline


@dataclass(slots=True)
class _Tally:
    migrated: int = 0
    failed: int = 0
    skipped: int = 0  # JSON twin appeared before we got to the pickle
    rescued: int = 0

    @property
    def handled(self) -> int:
        return self.migrated + self.failed + self.skipped


@dataclass(slots=True)
class _RetryState:
    """Which quarantined pickles were already retried under this version.

    Stored in ``failed/.retry_state.json``. A version change invalidates it,
    so unpickler fixes still rescue old failures -- once per release rather
    than on every startup.
    """

    path: pathlib.Path
    version: str
    attempted: set = field(default_factory=set)
    dirty: bool = False

    @classmethod
    def load(cls, failed_dir: pathlib.Path, version: str) -> "_RetryState":
        path = failed_dir / _RETRY_STATE_FILENAME
        attempted: set = set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == version:
                attempted = {str(name) for name in data.get("attempted", [])}
        except Exception:
            pass  # Missing/corrupt state just means "retry everything once".
        return cls(path=path, version=version, attempted=attempted)

    def mark(self, name: str) -> None:
        if name not in self.attempted:
            self.attempted.add(name)
            self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(
                    {"version": self.version, "attempted": sorted(self.attempted)}
                ),
                encoding="utf-8",
            )
            tmp_path.replace(self.path)
            self.dirty = False
        except OSError:
            pass  # Worst case: the retry repeats next startup.


def _pending_pickles(directory: pathlib.Path) -> List[pathlib.Path]:
    """Pickles in ``directory`` without a JSON twin (stat-only, no unpickling)."""
    return [
        pkl_path
        for pkl_path in sorted(directory.glob("*.pkl"))
        if not pkl_path.with_suffix(".json").exists()
    ]


def _migrate_directory(
    pickles: List[pathlib.Path],
    budget: _Budget,
    retry_state: _RetryState,
    tally: _Tally,
) -> None:
    """Migrate ``pickles`` until done or the budget runs out.

    Progress is recorded in ``tally`` as it happens so an interrupt still
    leaves accurate counts.
    """
    for pkl_path in pickles:
        if budget.exhausted():
            return
        if pkl_path.with_suffix(".json").exists():
            tally.skipped += 1  # JSON twin appeared meanwhile (lazy migration).
            continue
        result = migrate_pickle_file(pkl_path)
        if result.success:
            tally.migrated += 1
            archive_legacy_pickle(pkl_path)
        else:
            tally.failed += 1
            logger.debug(
                "Could not migrate session file %s: %s (quarantined)",
                pkl_path,
                result.error,
            )
            quarantined = quarantine_failed_pickle(pkl_path)
            if quarantined is not None:
                # Already tried under this version; don't re-read it below.
                retry_state.mark(quarantined.name)


def _retry_quarantined(
    directory: pathlib.Path,
    budget: _Budget,
    retry_state: _RetryState,
    tally: _Tally,
) -> None:
    """Retry ``pre_v2_backup/failed/*.pkl`` not yet tried under this version.

    Runs even when the sweep marker exists, so unpickler fixes retroactively
    rescue quarantined sessions. Each file is retried at most once per
    release (see :class:`_RetryState`) and only while the startup budget
    lasts. Rescued pickles graduate to ``pre_v2_backup/`` proper; repeat
    failures stay put with debug-only logging -- no warning spam.
    """
    failed_dir = directory / _BACKUP_DIRNAME / "failed"
    if not failed_dir.is_dir():
        return
    for pkl_path in sorted(failed_dir.glob("*.pkl")):
        if pkl_path.name in retry_state.attempted:
            continue
        json_path = directory / pkl_path.with_suffix(".json").name
        if json_path.exists():
            logger.debug("Skipping quarantined %s: JSON twin already exists", pkl_path)
            continue
        if budget.exhausted():
            return
        result = migrate_pickle_file(pkl_path, json_path)
        if result.success:
            tally.rescued += 1
            # Sidecar (if any) lives in the sessions dir, not failed/.
            _repoint_meta_sidecar(directory / pkl_path.name, json_path)
            archive_legacy_pickle_from_quarantine(pkl_path, directory)
        else:
            retry_state.mark(pkl_path.name)
            logger.debug(
                "Quarantined session %s still unmigratable: %s",
                pkl_path,
                result.error,
            )


def archive_legacy_pickle_from_quarantine(
    pkl_path: pathlib.Path, directory: pathlib.Path
) -> None:
    """Graduate a rescued pickle from ``failed/`` to ``pre_v2_backup/``."""
    try:
        _move_to(pkl_path, directory / _BACKUP_DIRNAME)
    except OSError:
        pass


def sweep_legacy_pickle_sessions() -> None:
    """Startup sweep: migrate known ``.pkl`` sessions to JSON, time-boxed.

    Work is bounded by a wall-clock budget (default
    ``_DEFAULT_BUDGET_SECONDS``; override via ``_BUDGET_ENV``, ``0`` skips
    the sweep). Unfinished work simply continues on later startups -- the
    per-file JSON-twin check makes that resumable, and sessions that are
    opened before then are migrated lazily by ``session_storage.load_session``.
    The completion marker is only written once nothing is left pending.

    After the main pass, quarantined pickles are retried at most once per
    release. Per-file failures are quarantined with debug-level detail and
    summarized in a single warning; Ctrl+C defers the remainder; the sweep
    never raises (best-effort at startup, same policy as
    ``session_migration.sweep_contexts_to_autosaves``).
    """
    try:
        directories = [d for d in _sweep_directories() if d.is_dir()]
        version = _migrator_version()
        states = {
            d: _RetryState.load(d / _BACKUP_DIRNAME / "failed", version)
            for d in directories
        }
        budget_seconds = _startup_budget_seconds()
        budget = _Budget(budget_seconds)
        tally = _Tally()
        total_pending = 0
        interrupted = False
        marker = _marker_path()
        try:
            if not marker.exists():
                pending = {d: _pending_pickles(d) for d in directories}
                total_pending = sum(len(p) for p in pending.values())
                if total_pending > _ANNOUNCE_THRESHOLD:
                    _emit_info_safely(
                        f"Migrating {total_pending} legacy session(s) to JSON "
                        f"(up to {budget_seconds:g}s per startup; press "
                        "Ctrl+C to defer the rest)..."
                    )
                for directory in directories:
                    _migrate_directory(
                        pending[directory], budget, states[directory], tally
                    )
                if tally.handled >= total_pending:
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.touch()

            for directory in directories:
                if budget.exhausted():
                    break
                _retry_quarantined(directory, budget, states[directory], tally)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            for state in states.values():
                state.save()

        remaining = max(total_pending - tally.handled, 0)
        if tally.failed:
            _emit_warning_safely(
                f"{tally.failed} session(s) could not be migrated and were "
                f"quarantined to {_BACKUP_DIRNAME}/failed/ -- run with debug "
                "logging for details."
            )
        if tally.migrated or tally.failed:
            _emit_info_safely(
                f"Session format migration: {tally.migrated} migrated to JSON, "
                f"{tally.failed} failed (originals kept under {_BACKUP_DIRNAME}/)."
            )
        if remaining:
            _emit_info_safely(
                f"{remaining} legacy session(s) still pending; they will "
                "migrate on later startups or when opened."
            )
        if tally.rescued:
            _emit_info_safely(
                f"Recovered {tally.rescued} previously quarantined session(s) "
                f"from {_BACKUP_DIRNAME}/failed/."
            )
        if interrupted:
            _emit_info_safely("Session migration deferred (interrupted).")
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
