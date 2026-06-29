"""One-shot sweep of legacy ``contexts/`` into the unified ``autosaves/`` store.

History: in earlier versions, named sessions lived in
``~/.code_puppy/contexts/`` (populated only by the obscure ``/dump_context``
slash command) and auto-saved sessions lived in ``~/.code_puppy/autosaves/``
(populated automatically by the interactive autosave loop). Under the
unified store, ``-r NAME``, ``/dump_context NAME``, and ``/load_context NAME``
all read and write ``autosaves/``. This module moves any files a power user
had ``/dump_context``'d into the legacy location so they remain visible.

The sweep is deliberately small: no flock, no quarantine, no slugification.
``contexts/`` was nearly empty for almost all users pre-Phase-1 (the
``/dump_context`` command is manual and obscure), so the typical sweep
moves zero files. When it does move files, name conflicts are genuinely
rare because autosave names follow ``auto_session_<ts>`` and user-named
entries are anything else. A skip-with-warning policy handles the rare
collision without needing a collision subsystem.

The sweep is **idempotent** via a sentinel file. Two simultaneous startups
racing the sweep are benign -- ``os.replace`` is atomic per file, the loser
of any per-file race sees the destination already exists and skips, and the
sentinel is touched atomically.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from typing import Optional

_SENTINEL_FILENAME = ".contexts_sweep_done"


def _autosave_dir() -> pathlib.Path:
    """Return AUTOSAVE_DIR as a Path. Lazy import dodges a config cycle."""
    from code_puppy.config import AUTOSAVE_DIR

    return pathlib.Path(AUTOSAVE_DIR)


def _legacy_contexts_dir() -> pathlib.Path:
    """Return the pre-unification contexts dir as a Path."""
    from code_puppy.config import CONTEXTS_DIR

    return pathlib.Path(CONTEXTS_DIR)


def _sidecar_for(pickle_path: pathlib.Path) -> pathlib.Path:
    """Return the metadata-sidecar path adjacent to a session pickle.

    Matches the layout produced by ``session_storage.save_session``:
    ``<stem>.pkl`` and ``<stem>_meta.json`` live side-by-side.
    """
    return pickle_path.with_name(f"{pickle_path.stem}_meta.json")


def _atomic_touch(path: pathlib.Path) -> None:
    """Create an empty file at ``path`` via tempfile + ``os.replace``.

    Survives concurrent attempts -- the loser overwrites the winner with
    an identically-empty file, which is functionally a no-op.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".sentinel_", dir=str(path.parent))
    try:
        os.close(fd)
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the tempfile if replace failed.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _log_orphan_sidecar(old_sidecar: pathlib.Path, error: Exception) -> None:
    """Log a sidecar-orphan event to the project's forensic error log.

    Called when the pickle move succeeded but the sidecar move failed
    (disk full, permission flip mid-sweep). The pickle is loadable from
    its new home; the orphan sidecar sits in ``contexts/`` and the user
    can clean it up from the log. This matches the project's "per-file
    error doesn't abort" policy and keeps the load-bearing pickle data.
    """
    try:
        from code_puppy.error_logging import log_error_message

        log_error_message(
            f"Sidecar orphan during contexts sweep: {old_sidecar} "
            f"(reason: {error!r}). The matching pickle was moved "
            f"successfully; this sidecar is safe to delete manually.",
            context="session_migration.sweep_contexts_to_autosaves",
        )
    except Exception:
        # Forensic logging is decorative; never crash the sweep over it.
        pass


def _move_pair(
    pickle_src: pathlib.Path, dest_dir: pathlib.Path
) -> tuple[bool, Optional[str]]:
    """Move pickle + sidecar from source to ``dest_dir``. Returns (moved, skip_reason).

    ``skip_reason`` is non-None when we deliberately did NOT move (e.g.
    name collision in dest). Pickle moves first; if the sidecar move fails
    afterwards we log the orphan but still count the pickle as moved.
    """
    dest_pickle = dest_dir / pickle_src.name
    sidecar_src = _sidecar_for(pickle_src)
    dest_sidecar = _sidecar_for(dest_pickle)
    # Asymmetric-collision guard: a prior interrupted sweep could have
    # moved only the sidecar OR only the pickle. Either kind of dest
    # entity blocks the move so we never silently overwrite half a pair.
    if dest_pickle.exists() or dest_sidecar.exists():
        return False, (
            f"Skipped sweep of {pickle_src} -- name already exists in "
            f"{dest_dir}. Leave the legacy copy in place or rename and "
            f"move it manually."
        )

    try:
        os.replace(str(pickle_src), str(dest_pickle))
    except OSError as exc:
        return False, f"Failed to move {pickle_src}: {exc}"

    if sidecar_src.exists():
        try:
            os.replace(str(sidecar_src), str(dest_sidecar))
        except OSError as exc:
            # Pickle already at dest; sidecar stuck at source. Log the
            # orphan path so the user can clean it up.
            _log_orphan_sidecar(sidecar_src, exc)
    return True, None


def sweep_contexts_to_autosaves() -> None:
    """Move any legacy ``contexts/`` session files into ``autosaves/``.

    Idempotent via a sentinel. Safe to call on every startup; the second
    call is an O(1) sentinel check. Failure modes are best-effort logged
    and never abort the caller.

    This is the ONLY caller-facing function in this module.
    """
    try:
        autosave_dir = _autosave_dir()
        contexts_dir = _legacy_contexts_dir()
        sentinel = autosave_dir / _SENTINEL_FILENAME

        if sentinel.exists():
            return

        autosave_dir.mkdir(parents=True, exist_ok=True)

        if not contexts_dir.exists():
            # Nothing to sweep. Drop the sentinel so we never re-check.
            _atomic_touch(sentinel)
            return

        moved = 0
        skipped = 0
        failures = 0
        for entry in sorted(contexts_dir.glob("*.pkl")):
            try:
                ok, reason = _move_pair(entry, autosave_dir)
            except Exception as exc:
                failures += 1
                _log_orphan_sidecar(entry, exc)
                continue

            if ok:
                moved += 1
            elif reason is not None:
                skipped += 1
                _emit_warning_safely(reason)
            else:
                failures += 1

        _atomic_touch(sentinel)

        if moved or skipped or failures:
            _emit_info_safely(
                f"Swept {moved} files from {contexts_dir} to "
                f"{autosave_dir} ({skipped} skipped -- name conflicts, "
                f"{failures} failed)."
            )

    except Exception as exc:  # pragma: no cover - defensive
        # Sweep MUST NOT crash the app. Worst case: legacy files stay
        # put, user sees them missing from the picker, and the sentinel
        # may or may not be touched. Next launch retries.
        try:
            from code_puppy.error_logging import log_error_message

            log_error_message(
                f"Contexts sweep aborted: {exc!r}",
                context="session_migration.sweep_contexts_to_autosaves",
            )
        except Exception:
            pass


def _emit_info_safely(message: str) -> None:
    """Best-effort ``emit_info`` -- never crash the sweep over UX wiring."""
    try:
        from code_puppy.messaging import emit_info

        emit_info(message)
    except Exception:
        pass


def _emit_warning_safely(message: str) -> None:
    """Best-effort ``emit_warning`` -- never crash the sweep."""
    try:
        from code_puppy.messaging import emit_warning

        emit_warning(message)
    except Exception:
        pass
