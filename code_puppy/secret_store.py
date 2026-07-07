"""Generic OS keyring secret store for Code Puppy.

Reads and writes secrets through the operating system keyring, with a
permission-hardened JSON file fallback for headless and CI environments
where no keyring backend is available.

Public API
----------
``keyring_available()``
    Report whether a usable keyring backend is configured.
``get_secret(name)`` / ``set_secret(name, value)`` / ``delete_secret(name)``
    Keyring-first secret operations that transparently fall back to the
    ``0o600`` JSON file when the keyring backend is unavailable.
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings

import keyring

from code_puppy.config import CONFIG_DIR

# Namespace under which every secret is stored in the OS keyring. Downstream
# distributions should use a distinct service name so secrets never bleed
# across builds.
_SERVICE_NAME = "code-puppy"

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


def _keyring_get(name: str) -> str | None:
    try:
        value = keyring.get_password(_SERVICE_NAME, name)
    except Exception:
        return None
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _keyring_set(name: str, value: str) -> bool:
    normalized = str(value).strip()
    if not normalized:
        return False
    try:
        keyring.set_password(_SERVICE_NAME, name, normalized)
    except Exception:
        return False
    return True


def _keyring_delete(name: str) -> bool:
    try:
        keyring.delete_password(_SERVICE_NAME, name)
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Permission-hardened JSON file fallback (secure I/O helper)
# ---------------------------------------------------------------------------


def _warn_fallback_active() -> None:
    global _warned_fallback
    if _warned_fallback:
        return
    _warned_fallback = True
    warnings.warn(
        "No OS keyring backend is available; secrets are stored in the "
        f"permission-hardened fallback file at {_FALLBACK_FILE} "
        "(mode 0o600). This is intended for headless/CI use only.",
        stacklevel=2,
    )


def _read_fallback() -> dict[str, str]:
    """Read the fallback secrets file, repairing its permissions on read."""
    try:
        # Repair permissions on read: if the file leaked to a broader mode
        # (bad umask, restored backup), tighten it back to 0o600.
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
    return data if isinstance(data, dict) else {}


def _write_fallback(data: dict[str, str]) -> bool:
    """Atomically write the fallback file with ``0o600`` permissions.

    Writes to a temp file in the same directory, ``chmod`` s it before it
    ever holds content the target will keep, then ``os.replace`` s it into
    place so a crash mid-write can never leave a truncated secrets file.
    """
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except OSError:
        return False

    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    try:
        os.chmod(tmp, _FALLBACK_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _FALLBACK_FILE)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    return True


# ---------------------------------------------------------------------------
# Public high-level API
# ---------------------------------------------------------------------------


def get_secret(name: str) -> str | None:
    """Return a secret by name, or ``None`` when it is not stored.

    Reads the keyring first, then the file fallback. The fallback is only
    consulted when the keyring backend is unavailable.
    """
    _ensure_backend()
    value = _keyring_get(name)
    if value:
        return value

    if keyring_available():
        return None

    _warn_fallback_active()
    stored = _read_fallback().get(name)
    if stored is None:
        return None
    normalized = str(stored).strip()
    return normalized or None


def set_secret(name: str, value: str) -> None:
    """Persist a secret by name.

    Writes to the keyring when a backend is available, otherwise to the
    permission-hardened JSON fallback.
    """
    _ensure_backend()
    if _keyring_set(name, value):
        return

    if keyring_available():
        # The backend is healthy but the write still failed (transient
        # error, permission prompt dismissed, etc.).  Writing to the
        # fallback here would strand the secret: get_secret() skips the
        # fallback when the keyring is available.  Warn instead.
        warnings.warn(
            f"Keyring write failed for {name!r} despite a healthy "
            "backend; the secret was not persisted.",
            stacklevel=2,
        )
        return

    _warn_fallback_active()
    normalized = str(value).strip()
    if not normalized:
        return
    data = _read_fallback()
    data[name] = normalized
    _write_fallback(data)


def delete_secret(name: str) -> None:
    """Best-effort removal of a secret from both the keyring and fallback."""
    _ensure_backend()
    _keyring_delete(name)

    if keyring_available():
        return

    data = _read_fallback()
    if name in data:
        del data[name]
        _write_fallback(data)
