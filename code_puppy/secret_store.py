"""Generic OS keyring secret store for Code Puppy.

Reads and writes secrets through the operating system keyring, with a
permission-hardened JSON file fallback as a final safety net.

Write strategy (three tiers, in order):
  1. **Direct keyring write** -- used when the value fits in one entry.
  2. **Chunked keyring write** -- the value is split into ≤``_CHUNK_SIZE``
     pieces when the OS imposes a per-entry size cap.  The primary real-world
     case is Windows Credential Manager, which rejects blobs larger than
     ~2 560 bytes UTF-16-LE (error 1783); long tokens routinely exceed
     this.  Chunking keeps the keyring as the source of truth.
  3. **Permission-hardened file fallback** -- used only when both keyring
     strategies fail (genuinely broken backend, backend crash, headless CI).
     Written atomically and restricted to the owner: ``0o600`` on POSIX, and
     an owner-only NTFS DACL (via ``icacls``) on Windows.  If the Windows ACL
     cannot be applied, the fallback warning says so plainly -- the file is
     then plaintext with default inheritance, not owner-only protected.

Read strategy:
  The keyring is queried first (with transparent chunk reassembly).  The
  fallback file is always consulted as a last resort so secrets written there
  by a previous session (after exhausting both keyring options) are still
  recoverable even when the keyring subsequently becomes healthy.

The keyring service name is configurable via ``configure_service_name`` so
each distribution can namespace its secrets and never read, copy, or alias
secrets across builds.  The default is ``"code-puppy"``; downstream
distributions override it at startup.

Public API
----------
``keyring_available()``
    Report whether a usable keyring backend is configured.
``configure_service_name(name)``
    Override the keyring service name used for all secret operations.
``get_secret(name)`` / ``set_secret(name, value)`` / ``delete_secret(name)``
    Three-tier secret operations (keyring direct → keyring chunked → file).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import warnings

import keyring

from code_puppy.config import CONFIG_DIR

# Namespace under which every secret is stored in the OS keyring. Downstream
# distributions call ``configure_service_name`` to use a distinct name so
# secrets never bleed across builds.
_service_name = "code-puppy"

# The default service namespace.  A legacy flat fallback file (pre per-service
# scoping) is migrated under this name so it stays readable on the default
# build without leaking into another distribution's namespace.
_DEFAULT_SERVICE = "code-puppy"

# Permission-hardened JSON fallback used only when the keyring backend is
# unavailable (headless boxes, minimal CI containers, etc.).
_FALLBACK_FILE = os.path.join(CONFIG_DIR, "secrets.json")
_FALLBACK_MODE = 0o600

# Emit the "fallback storage is active" warning at most once per process so
# we do not spam the console on every read/write.
_warned_fallback = False

# The consolidated macOS backend is installed lazily, once, on first use.
_backend_installed = False


def _ensure_backend() -> None:
    """Install the consolidated macOS backend once, before any secret op.

    Off macOS (or when the user pinned a backend) this is a no-op and the
    native ``keyring`` backend is used unchanged. Best-effort: a failure
    leaves the native backend in place.
    """
    global _backend_installed
    if _backend_installed:
        return
    _backend_installed = True
    try:
        from code_puppy.secret_store_backends import (
            install_consolidated_backend_if_appropriate,
        )
    except ImportError:
        # secret_store_backends imports fcntl (POSIX-only); on Windows
        # the consolidated macOS backend is irrelevant anyway.
        return

    install_consolidated_backend_if_appropriate()


def get_service_name() -> str:
    """Return the current keyring service name."""
    return _service_name


def configure_service_name(name: str) -> None:
    """Override the keyring service name used for all secret operations.

    Call this early at startup -- before any get/set/delete calls -- so
    secrets are namespaced per distribution.  Downstream distributions
    call this from their ``startup`` callback.  The default is
    ``"code-puppy"``.
    """
    global _service_name
    name = str(name).strip()
    if not name:
        raise ValueError("service name must be non-empty")
    _service_name = name


# Maximum characters per keyring entry.  Windows Credential Manager encodes
# credential blobs as UTF-16-LE (2 bytes per char) and caps them at ~2 560
# bytes, giving a ~1 280-char ceiling.  We stay conservatively below that so
# typical ASCII padding in the JWT header/signature doesn't push us over.
_CHUNK_SIZE = 1200

# Suffix tokens used to build chunk-related keyring entry names.  The ``cp``
# prefix scopes them to Code Puppy and makes accidental collisions with real
# secret names essentially impossible.
_CHUNK_NS = ":cp:"
_COUNT_SUFFIX = ":cp:n"


class SecretStoreError(RuntimeError):
    """Raised when a secret cannot be persisted or removed as requested.

    Distinct from a *missing* secret (``get_secret`` returns ``None``): this
    signals an active failure -- e.g. a fallback write to a read-only or full
    filesystem -- so callers never mistake a lost credential for success.
    """


def _validate_name(name: str) -> str:
    """Validate a caller-supplied secret name.

    The chunk machinery reserves the ``:cp:`` token to build internal entry
    names (``<name>:cp:<i>`` for chunks, ``<name>:cp:n`` for the commit
    marker).  A caller-supplied name containing ``:cp:`` could therefore
    shadow a real secret's chunk metadata or, via ``delete_secret``, destroy
    an unrelated entry.  Because this module is a generic store whose names
    may be built from user- or config-derived strings, we reject the reserved
    token outright rather than trust that "nobody would name a secret that."
    """
    if not isinstance(name, str) or not name:
        raise ValueError("secret name must be a non-empty string")
    if _CHUNK_NS in name:
        raise ValueError(
            f"secret name {name!r} contains the reserved substring "
            f"{_CHUNK_NS!r}; it is used internally for chunk metadata"
        )
    return name


def _validate_value(value: str) -> str:
    """Validate a caller-supplied secret value.

    Empty or whitespace-only values are rejected with a ``ValueError`` so an
    empty write can never be confused with a backend failure (the old code
    silently no-oped and then emitted a misleading "keyring write failed"
    warning).  Values with *content* plus surrounding whitespace are allowed
    and stored verbatim -- secrets with significant leading/trailing
    whitespace exist and must not be silently mutated.
    """
    if not isinstance(value, str):
        raise ValueError("secret value must be a string")
    if not value.strip():
        raise ValueError("secret value must be non-empty")
    return value


def _chunk_count_key(name: str) -> str:
    """Keyring entry name for the chunk-count (commit) marker."""
    return f"{name}{_COUNT_SUFFIX}"


def _chunk_key(name: str, i: int) -> str:
    """Keyring entry name for chunk *i* of *name*."""
    return f"{name}{_CHUNK_NS}{i}"


# ---------------------------------------------------------------------------
# Keyring availability + low-level access
# ---------------------------------------------------------------------------


def keyring_available() -> bool:
    """Return True when a usable keyring backend is configured.

    A backend with ``priority <= 0`` (for example the fail/null backend on
    a headless Linux box) is treated as unavailable, so callers degrade to
    the file fallback instead of writing into a black hole.
    """
    _ensure_backend()
    try:
        backend = keyring.get_keyring()
    except Exception:
        return False
    priority = getattr(backend, "priority", None)
    if priority is None:
        return True
    try:
        return float(priority) > 0
    except Exception:
        return True


def _kr_get_raw(name: str) -> str | None:
    """Read one keyring entry verbatim; ``None`` on error or absence.

    The stored value is returned byte-for-byte (no ``.strip()``): a secret
    with legitimate leading/trailing whitespace must round-trip unchanged.
    A truly empty string is treated as absence.
    """
    try:
        value = keyring.get_password(_service_name, name)
    except Exception:
        return None
    if not value:
        return None
    return str(value)


def _kr_set_raw(name: str, value: str) -> bool:
    """Write one keyring entry; return ``False`` on any error."""
    try:
        keyring.set_password(_service_name, name, value)
    except Exception:
        return False
    return True


def _kr_del_raw(name: str) -> bool:
    """Delete one keyring entry; return ``False`` on any error."""
    try:
        keyring.delete_password(_service_name, name)
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Chunk-aware keyring helpers (transparent to callers)
# ---------------------------------------------------------------------------


def _keyring_get(name: str) -> str | None:
    """Read a logical secret, transparently reassembling chunks if present.

    Checks for a chunk-count key first.  When found, reads and concatenates
    all chunks in order.  Falls back to a direct single-entry read for values
    written by older builds or that never needed chunking.
    """
    count_raw = _kr_get_raw(_chunk_count_key(name))
    if count_raw is not None:
        try:
            n = int(count_raw)
        except ValueError:
            return None  # corrupt count -- treat as absent
        parts: list[str] = []
        for i in range(n):
            chunk = _kr_get_raw(_chunk_key(name, i))
            if chunk is None:
                return None  # partial write -- treat as absent
            parts.append(chunk)
        assembled = "".join(parts)
        return assembled or None

    # No chunk metadata -- try a plain single-entry read.
    return _kr_get_raw(name)


def _delete_chunks(name: str) -> None:
    """Best-effort removal of all chunk entries for *name*."""
    count_raw = _kr_get_raw(_chunk_count_key(name))
    if count_raw is None:
        return
    try:
        n = int(count_raw)
    except ValueError:
        n = 0
    for i in range(n):
        _kr_del_raw(_chunk_key(name, i))
    _kr_del_raw(_chunk_count_key(name))


def _keyring_set(name: str, value: str) -> bool:
    """Write a logical secret, chunking automatically when it exceeds _CHUNK_SIZE.

    **Small values** (len <= _CHUNK_SIZE):
      - Written as a single keyring entry under *name*.
      - Any stale chunk entries from a prior oversized write are removed.

    **Large values** (len > _CHUNK_SIZE):
      - Split into ceil(len / _CHUNK_SIZE) pieces.
      - Chunk data entries are written first, then the count key last so a
        mid-write crash never leaves a partially-readable value behind.
      - Excess chunks from a prior write with more pieces are pruned.
      - The direct *name* entry is removed to avoid ambiguity on read.

    Returns ``True`` on success, ``False`` if any keyring write fails.

    The value is stored verbatim; callers reject empty/whitespace-only input
    at the public boundary (``set_secret``), so a ``False`` here always means
    a genuine backend failure -- never "you passed an empty string."
    """
    if len(value) <= _CHUNK_SIZE:
        if not _kr_set_raw(name, value):
            return False
        _delete_chunks(name)  # clean up any old chunked write
        return True

    # --- Chunked write path ---
    chunks = [value[i : i + _CHUNK_SIZE] for i in range(0, len(value), _CHUNK_SIZE)]

    # Write data entries first.
    for idx, chunk in enumerate(chunks):
        if not _kr_set_raw(_chunk_key(name, idx), chunk):
            # Partial write -- roll back what we managed.
            for j in range(idx):
                _kr_del_raw(_chunk_key(name, j))
            return False

    # Prune stale trailing chunks from a prior larger write.
    stale = len(chunks)
    while _kr_get_raw(_chunk_key(name, stale)) is not None:
        _kr_del_raw(_chunk_key(name, stale))
        stale += 1

    # Commit: write the count key last as the atomic marker.
    if not _kr_set_raw(_chunk_count_key(name), str(len(chunks))):
        for idx in range(len(chunks)):
            _kr_del_raw(_chunk_key(name, idx))
        return False

    _kr_del_raw(name)  # remove any stale single-entry write
    return True


def _keyring_delete(name: str) -> bool:
    """Delete a logical secret, removing chunks if present."""
    direct = _kr_del_raw(name)
    _delete_chunks(name)
    return direct


# ---------------------------------------------------------------------------
# Permission-hardened JSON file fallback (secure I/O helper)
# ---------------------------------------------------------------------------


# Cross-process advisory lock guarding the fallback read-modify-write. Atomic
# os.replace() prevents truncated reads but not *lost updates*: two processes
# (e.g. the main app and an MCP subprocess) can each read the document, add a
# different key, and the second writer clobbers the first. The lock serializes
# the whole read->mutate->write cycle. The chunked keyring path activates on
# Windows, so this lock is cross-platform (fcntl on POSIX, msvcrt on Windows).
_FALLBACK_LOCK_FILE = os.path.join(CONFIG_DIR, ".secrets.lock")
_fallback_thread_lock = threading.RLock()

try:
    import fcntl

    def _lock_fd(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_fd(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
except ImportError:  # pragma: no cover - platform-specific (Windows)
    import msvcrt

    def _lock_fd(fd: int) -> None:
        # Byte-range lock on the first byte; blocks until acquired.
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock_fd(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


@contextlib.contextmanager
def _fallback_lock():
    """Serialize the fallback read-modify-write across threads and processes.

    Best-effort: if the lock file cannot be created (e.g. read-only config
    dir), we degrade to the in-process thread lock alone rather than wedge
    secret operations. The subsequent _write_fallback will surface any real
    persistence failure.
    """
    with _fallback_thread_lock:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            fd = os.open(_FALLBACK_LOCK_FILE, os.O_CREAT | os.O_RDWR, _FALLBACK_MODE)
        except OSError:
            yield
            return
        try:
            _lock_fd(fd)
            yield
        finally:
            try:
                _unlock_fd(fd)
            finally:
                os.close(fd)


def _notify(message: str) -> None:
    """Surface a user-facing notice through the messaging bus.

    ``warnings.warn`` is effectively invisible inside the TUI and is
    deduplicated by the default warnings filter, so the headless-fallback and
    write-failure notices never reached a human.  Routing through the bus makes
    them render.  Falls back to ``warnings.warn`` when the bus is unavailable
    (early startup, non-TUI callers, or an import failure) so a notice is never
    silently dropped.
    """
    try:
        from code_puppy.messaging import emit_warning

        emit_warning(message)
    except Exception:
        warnings.warn(message, stacklevel=2)


def _warn_fallback_active() -> None:
    global _warned_fallback
    if _warned_fallback:
        return
    _warned_fallback = True
    if sys.platform == "win32" and _windows_acl_hardened is False:
        detail = (
            "secrets are stored in PLAINTEXT at "
            f"{_FALLBACK_FILE}; an owner-only NTFS ACL could not be applied "
            "(icacls unavailable on this system). Treat this file as sensitive."
        )
    elif sys.platform == "win32":
        detail = (
            "secrets are stored in the fallback file at "
            f"{_FALLBACK_FILE}, restricted to your account by an owner-only "
            "NTFS ACL."
        )
    else:
        detail = (
            "secrets are stored in the permission-hardened fallback file at "
            f"{_FALLBACK_FILE} (mode 0o600)."
        )
    warnings_msg = (
        "No OS keyring backend is available; "
        + detail
        + " This is intended for headless/CI use only."
    )
    _notify(warnings_msg)


# Tracks whether the most recent Windows ACL hardening attempt succeeded, so
# the fallback warning can be honest about the actual on-disk protection.
# None until the first Windows hardening attempt.
_windows_acl_hardened: bool | None = None


def _harden_windows(path: str) -> bool:
    """Apply an owner-only NTFS DACL to *path* via ``icacls`` (no extra deps).

    Removes inherited ACEs and grants Full control to the current user only.
    Best-effort: minimal or older Windows images -- exactly where this
    fallback activates -- may lack a usable ``icacls``.
    """
    user = os.environ.get("USERNAME")
    if not user:
        return False
    try:
        subprocess.run(
            ["icacls", path, "/inheritance:r"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["icacls", path, "/grant:r", f"{user}:F"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _harden_permissions(path: str) -> bool:
    """Restrict *path* to the owner, honestly per platform.

    POSIX: ``chmod 0o600``.  Windows: an owner-only NTFS DACL via ``icacls``,
    because ``chmod(0o600)`` does **not** establish owner-only protection on
    NTFS -- it only toggles the read-only attribute.  The Windows outcome is
    recorded so ``_warn_fallback_active`` can tell the user the truth.
    """
    global _windows_acl_hardened
    if sys.platform == "win32":
        _windows_acl_hardened = _harden_windows(path)
        return _windows_acl_hardened
    try:
        os.chmod(path, _FALLBACK_MODE)
        return True
    except OSError:
        return False


def _read_fallback_doc() -> dict[str, dict[str, str]]:
    """Read the raw fallback file as a service-namespaced document.

    The on-disk shape is ``{service_name: {secret_name: value}}`` so each
    distribution's fallback secrets are isolated the same way keyring entries
    are (F2).  Permissions are repaired on read.  A legacy *flat*
    ``{secret_name: value}`` file (written before per-service scoping existed)
    is migrated under the default service namespace so historical secrets stay
    readable under the default build without leaking into another
    distribution's namespace.
    """
    try:
        # Repair permissions on read: if the file leaked to a broader mode
        # (bad umask, restored backup), tighten it back to owner-only.
        if sys.platform == "win32":
            _harden_permissions(_FALLBACK_FILE)
        else:
            try:
                current = os.stat(_FALLBACK_FILE).st_mode & 0o777
                if current != _FALLBACK_MODE:
                    os.chmod(_FALLBACK_FILE, _FALLBACK_MODE)
            except OSError:
                pass
        with open(_FALLBACK_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Current (nested) format: service -> {name: value}.
    nested = {k: v for k, v in data.items() if isinstance(v, dict)}
    if nested:
        return nested
    # Legacy flat format: migrate under the default service namespace.
    flat = {k: v for k, v in data.items() if isinstance(v, str)}
    return {_DEFAULT_SERVICE: flat} if flat else {}


def _read_fallback() -> dict[str, str]:
    """Return the current service's fallback slice (used by ``get_secret``)."""
    return dict(_read_fallback_doc().get(_service_name, {}))


def _write_fallback(data: dict[str, dict[str, str]]) -> bool:
    """Atomically write the fallback file with ``0o600`` permissions.

    Writes to a temp file in the same directory, ``chmod`` s it before it
    ever holds content the target will keep, then ``os.replace`` s it into
    place so a crash mid-write can never leave a truncated secrets file.

    Returns ``True`` on success and ``False`` on *any* failure (including a
    ``mkstemp`` that fails on a read-only or full filesystem).  The contract
    is uniform so callers can act on it -- see ``set_secret``/``delete_secret``.
    """
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except OSError:
        return False

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
        _harden_permissions(tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _FALLBACK_FILE)
    except OSError:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False
    return True


def _fallback_set(name: str, value: str) -> bool:
    """Add/update a fallback entry under the cross-process lock (F5), scoped to
    the current service namespace (F2)."""
    with _fallback_lock():
        doc = _read_fallback_doc()
        doc.setdefault(_service_name, {})[name] = value
        return _write_fallback(doc)


def _fallback_delete(name: str) -> bool | None:
    """Remove a fallback entry (current service only) under the lock.

    Returns ``True`` on a successful scrub, ``False`` if the rewrite failed,
    and ``None`` when there was nothing to remove (so callers don't treat a
    no-op as a failure).
    """
    with _fallback_lock():
        doc = _read_fallback_doc()
        slice_ = doc.get(_service_name, {})
        if name not in slice_:
            return None
        del slice_[name]
        if not slice_:
            doc.pop(_service_name, None)
        return _write_fallback(doc)


def _fallback_scrub(name: str) -> None:
    """Best-effort removal of a stale fallback entry after a healthy keyring
    write (F6), scoped to the current service namespace (F2).

    A successful keyring write must not leave a rotated-out secret sitting in
    plaintext on disk, where it could later be resurrected if the keyring
    entry vanishes. The keyring already holds the source of truth here, so a
    failure to rewrite the file is not fatal -- but it is worth surfacing.
    """
    with _fallback_lock():
        doc = _read_fallback_doc()
        slice_ = doc.get(_service_name, {})
        if name not in slice_:
            return
        del slice_[name]
        if not slice_:
            doc.pop(_service_name, None)
        if not _write_fallback(doc):
            _notify(
                f"Secret {name!r} was written to the keyring but its stale "
                f"plaintext copy in {_FALLBACK_FILE} could not be removed "
                "(read-only or full filesystem?)."
            )


# ---------------------------------------------------------------------------
# Public high-level API
# ---------------------------------------------------------------------------


def get_secret(name: str) -> str | None:
    """Return a secret by name, or ``None`` when it is not stored.

    Resolution order:
      1. OS keyring -- direct read or transparent chunk reassembly.
      2. Permission-hardened fallback file -- always consulted as a last
         resort so secrets written there by a previous session (after
         exhausting both keyring options) are still recoverable.
    """
    _validate_name(name)
    _ensure_backend()
    value = _keyring_get(name)
    if value:
        return value

    # Always check the fallback file: a prior set_secret may have ended up
    # there after both keyring paths failed.  Only emit the headless warning
    # when the keyring backend itself is unavailable.
    if not keyring_available():
        _warn_fallback_active()
    stored = _read_fallback().get(name)
    if not stored:
        return None
    return str(stored)


def set_secret(name: str, value: str) -> None:
    """Persist a secret by name.

    Attempts three strategies in order:
      1. Direct keyring write (small values).
      2. Chunked keyring write (oversized values, e.g. Windows CM cap).
      3. Permission-hardened JSON file fallback (only when both keyring
         strategies fail -- unexpected backend error or no keyring at all).
    """
    _validate_name(name)
    _validate_value(value)
    _ensure_backend()
    if _keyring_set(name, value):
        # F6: scrub any stale plaintext copy so a rotated secret can't linger
        # on disk and be resurrected later if the keyring entry vanishes.
        _fallback_scrub(name)
        return

    if keyring_available():
        # Both direct and chunked writes failed despite a healthy backend.
        # Unexpected (transient error, backend crash, prompt dismissed).
        # Warn so it's diagnosable, then persist to the file so the secret
        # is not lost.
        _notify(
            f"Keyring write failed for {name!r} despite a healthy backend "
            "(transient error or backend crash). Storing in the secure file "
            f"fallback at {_FALLBACK_FILE}."
        )
    else:
        _warn_fallback_active()

    if not _fallback_set(name, value):
        raise SecretStoreError(
            f"Failed to persist secret {name!r}: the OS keyring is unavailable "
            f"and the fallback file at {_FALLBACK_FILE} could not be written "
            "(read-only or full filesystem?). The secret was NOT saved."
        )


def delete_secret(name: str) -> None:
    """Best-effort removal of a secret from keyring (and chunks) and fallback.

    Raises ``SecretStoreError`` if the fallback file holds the secret but
    cannot be rewritten to scrub it -- otherwise "delete" would report success
    while the plaintext secret survives on disk.
    """
    _validate_name(name)
    _ensure_backend()
    _keyring_delete(name)

    # Always scrub the fallback file: a prior write may have ended up there
    # even on a system where the keyring is now healthy.
    if _fallback_delete(name) is False:
        raise SecretStoreError(
            f"Failed to remove secret {name!r} from the fallback file at "
            f"{_FALLBACK_FILE} (read-only or full filesystem?). The "
            "plaintext secret may still be present on disk."
        )
