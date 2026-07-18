"""Install the bundled Flux command set into ``~/.code_puppy``.

The plugin ships a snapshot of the Flux slash-command suite (markdown command
files + a couple of ``exec:`` helper scripts) as package data under
``bundled/``. On a fresh install -- or after code-puppy is upgraded -- we copy
that payload into the user config dir so ``/flux/...`` commands are available
out of the box.

Design goals:

* **Idempotent.** Re-running with the same bundled content is a no-op.
* **Non-destructive.** A file the user has hand-edited is never silently
  clobbered -- it is backed up to ``<name>.bak`` before the fresh copy lands.
  We tell "user edited it" from "we wrote it last time" via a manifest of the
  SHA-256 hashes we installed (``.flux_bootstrap_manifest.json``).
* **Version-gated.** We only walk the tree when the installed code-puppy
  version differs from the marker we stored last run, so steady-state startup
  stays cheap.
* **Fails closed, never fatal.** Any error is swallowed by the caller; a broken
  install must not take down the whole app.

The manifest + version marker are dot-files, so they never register as
slash-commands and stay out of the way of the command loader.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

# Best-effort cross-process lock so two code-puppy instances launched during the
# one-time install window don't both walk/copy the tree at once (torn reads,
# spurious .bak files). Dot-file so the command loader ignores it.
LOCK_NAME = ".flux_bootstrap.lock"

# Directory holding the shipped payload (``bundled/commands`` + ``bundled/scripts``).
BUNDLED_DIR = Path(__file__).parent / "bundled"

# Dot-files live at the root of the config dir so the command loader (which
# skips ``.``-prefixed namespaces) never picks them up.
VERSION_MARKER_NAME = ".flux_bootstrap_version"
MANIFEST_NAME = ".flux_bootstrap_manifest.json"


@dataclass
class InstallReport:
    """Summary of what an install pass did (handy for logging + tests)."""

    installed: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    backed_up: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.installed or self.updated or self.backed_up)

    def summary(self) -> str:
        return (
            f"{len(self.installed)} new, {len(self.updated)} updated, "
            f"{len(self.backed_up)} backed up, {len(self.skipped)} unchanged"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file + atomic replace.

    A crash mid-write leaves the previous file intact (or absent) rather than a
    half-written, corrupt one. ``os.replace`` is atomic on the same filesystem.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_bytes_preserving_mode(dest: Path, payload: bytes, src: Path) -> None:
    """Write ``payload`` to ``dest`` atomically and copy ``src``'s mode bits.

    Writes to a temp file, chmods it to match ``src`` (executable/mode metadata
    on installed scripts so a future direct-exec doesn't lose the +x bit), then
    atomically replaces ``dest``. A crash mid-write leaves the previous file
    intact rather than a truncated one -- the same crash-safety the manifest and
    version marker already get via :func:`_atomic_write_text`. Chmod failures
    are non-fatal; the content landing is what matters.
    """
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(payload)
    try:
        tmp.chmod(stat.S_IMODE(src.stat().st_mode))
    except OSError:
        pass
    os.replace(tmp, dest)


def _unique_backup_path(dest: Path) -> Path:
    """Return a non-colliding ``<name>.bak`` (or ``.bak.1``, ``.bak.2``, ...).

    Successive version bumps against a repeatedly hand-edited file would
    otherwise clobber the previous backup. Find the first free slot instead.
    """
    backup = dest.with_name(dest.name + ".bak")
    if not backup.exists():
        return backup
    i = 1
    while True:
        candidate = dest.with_name(f"{dest.name}.bak.{i}")
        if not candidate.exists():
            return candidate
        i += 1


def _iter_bundled_files() -> List[Path]:
    """Every regular file under ``bundled/`` (skipping OS junk)."""
    if not BUNDLED_DIR.is_dir():
        return []
    return sorted(
        p for p in BUNDLED_DIR.rglob("*") if p.is_file() and p.name != ".DS_Store"
    )


def _load_manifest(config_dir: Path) -> Dict[str, str]:
    manifest_path = config_dir / MANIFEST_NAME
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_manifest(config_dir: Path, manifest: Dict[str, str]) -> None:
    manifest_path = config_dir / MANIFEST_NAME
    _atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True))


def read_installed_version(config_dir: Path) -> str | None:
    """Return the code-puppy version recorded on the last successful install."""
    marker = config_dir / VERSION_MARKER_NAME
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_version(config_dir: Path, version: str) -> None:
    _atomic_write_text(config_dir / VERSION_MARKER_NAME, version)


def needs_install(config_dir: Path, current_version: str) -> bool:
    """True on a fresh install (no marker) or after a version bump."""
    return read_installed_version(config_dir) != current_version


def _install_pass(config_dir: Path, current_version: str) -> InstallReport:
    """Copy the bundled payload into ``config_dir`` (the actual work).

    Separated from :func:`install_bundled_commands` so the latter can wrap this
    in a best-effort cross-process lock without deepening the copy logic.
    """
    report = InstallReport()
    manifest = _load_manifest(config_dir)
    new_manifest: Dict[str, str] = {}

    for src in _iter_bundled_files():
        rel = src.relative_to(BUNDLED_DIR).as_posix()
        dest = config_dir / rel
        payload = src.read_bytes()
        payload_hash = _sha256_bytes(payload)

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes_preserving_mode(dest, payload, src)
            report.installed.append(rel)
            new_manifest[rel] = payload_hash
            continue

        current_hash = _sha256(dest)
        if current_hash == payload_hash:
            # Already exactly our payload -- idempotent no-op. Claim it so we
            # keep ownership across future bumps.
            report.skipped.append(rel)
            new_manifest[rel] = payload_hash
            continue

        # Content differs from what we ship. Two cases:
        #
        #   1. We never installed this file (``rel not in manifest``). It's a
        #      pre-existing, user-owned file that merely shares a name with our
        #      payload. Preserve it *in place* -- do NOT back it up, overwrite
        #      it, or claim it in the manifest. The user's file wins, forever,
        #      unless they delete it. This is what stops a fresh Flux install
        #      from stomping a user's own global command of the same name.
        #
        #   2. We installed it before (``rel in manifest``). It's ours to
        #      update. If the on-disk hash matches what the manifest says we
        #      wrote, it's untouched -> overwrite freely. Otherwise the user
        #      hand-edited our copy -> preserve theirs as a uniquely-named
        #      ``.bak`` before laying down the fresh version.
        if rel not in manifest:
            report.skipped.append(rel)
            continue

        if manifest.get(rel) != current_hash:
            backup = _unique_backup_path(dest)
            shutil.copy2(dest, backup)
            report.backed_up.append(backup.relative_to(config_dir).as_posix())

        _write_bytes_preserving_mode(dest, payload, src)
        report.updated.append(rel)
        new_manifest[rel] = payload_hash

    _save_manifest(config_dir, new_manifest)
    _write_version(config_dir, current_version)
    return report


def install_bundled_commands(config_dir: Path, current_version: str) -> InstallReport:
    """Copy the bundled Flux payload into ``config_dir``.

    ``bundled/commands/...`` -> ``config_dir/commands/...``
    ``bundled/scripts/...``  -> ``config_dir/scripts/...``

    Returns an :class:`InstallReport`. Writes the version marker + manifest only
    after a clean pass so a crash mid-install re-runs next time.

    Guarded by a best-effort exclusive ``flock`` on ``.flux_bootstrap.lock``: if
    another instance already holds it (a concurrent first-launch install), we
    skip and return an empty report rather than racing. The lock auto-releases
    when the holding process dies, so a crashed install can't wedge future ones.
    Where ``fcntl`` is unavailable (Windows), the pass runs unlocked -- the same
    behavior as before this guard existed.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    if fcntl is None:
        return _install_pass(config_dir, current_version)

    lock_fd = os.open(config_dir / LOCK_NAME, os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Another process holds the lock -- it's installing; skip.
            return InstallReport()
        return _install_pass(config_dir, current_version)
    finally:
        os.close(lock_fd)  # releases the flock
