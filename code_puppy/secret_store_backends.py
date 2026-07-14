"""macOS consolidated keyring backend for Code Puppy.

Stores every secret in a single macOS Keychain item (one JSON blob) so
the user sees at most one Keychain access prompt regardless of how many
secrets Code Puppy stores.

Why this exists
---------------
A macOS Keychain item carries an ACL naming which binaries may read it
without prompting. The ACL is anchored to the calling binary's identity.
The interpreter that talks to Keychain is uv's managed CPython, which is
ad-hoc signed (no stable Team ID), so its identity is its cdhash. Every
Python version bump produces a new cdhash, misses the stored ACL, and
prompts the user once per keychain item. With a dozen secrets that is a
dozen "Always Allow" dialogs after a routine upgrade. One item means one
ACL and therefore one prompt.

Scope
-----
This backend is registered only on macOS, only when the active backend is
the stock macOS one, and only when the user has not pinned their own
backend. Off macOS the native ``keyring`` backend is used unchanged. The
``secret_store`` public API does not change; consolidation is a backend
concern that callers never observe.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import threading

import keyring
from keyring.backend import KeyringBackend

from code_puppy.config import CONFIG_DIR

# All secrets for a given service live under this single, fixed account.
# The service name is supplied per call by secret_store, so different
# distributions (with distinct service names) get distinct blob items.
_BLOB_ACCOUNT = "__code_puppy_secret_blob__"

# Cross-process lock file guarding the read-modify-write of the blob.
_LOCK_FILE = os.path.join(CONFIG_DIR, ".secrets.lock")

# In-process guard. flock covers other processes; this covers threads in
# this process cheaply and predictably.
_thread_lock = threading.RLock()


@contextlib.contextmanager
def _blob_lock():
    """Serialize the blob read-modify-write across threads and processes.

    Keychain item writes are atomic at the item level, so readers always
    see a whole blob (old or new), never a partial one. Writers, however,
    must not interleave their read-modify-write cycles or one would clobber
    the other's addition. This takes an in-process lock plus an advisory
    ``flock`` on a lock file beside ``CONFIG_DIR``.
    """
    with _thread_lock:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
        except OSError:
            # If we cannot create the lock dir, fall through with only the
            # thread lock. Better to proceed than to wedge secret writes.
            yield
            return
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class ConsolidatedKeychainBackend(KeyringBackend):
    """Store all of a service's secrets in one keychain item (JSON blob).

    This backend is selected explicitly via ``keyring.set_keyring`` from
    ``install_consolidated_backend_if_appropriate``; it is never chosen by
    ``keyring``'s automatic priority-based discovery. Its ``priority`` is
    deliberately below the stock macOS backend so auto-discovery prefers
    the native backend on every platform, and the Darwin gating in
    ``should_use_consolidated_backend`` stays the single source of truth
    for when consolidation is active.
    """

    # Below the stock macOS backend (5) so keyring's auto-discovery never
    # selects this backend on any platform. Selection is explicit via
    # set_keyring. Still positive so secret_store.keyring_available()
    # treats it as usable once installed.
    priority = 0.5

    def __init__(self) -> None:
        super().__init__()
        # Delegate is created lazily (see _get_delegate) rather than here,
        # so merely constructing this class during keyring's cross-platform
        # backend discovery never touches the macOS-only backend.
        self._delegate_cache = None

    def _get_delegate(self):
        """Lazily construct the stock macOS backend we delegate I/O to.

        This backend only reshapes the key space (one item instead of one
        per secret); it does not reimplement keychain I/O.
        """
        if self._delegate_cache is None:
            from keyring.backends import macOS as macos_backend

            self._delegate_cache = macos_backend.Keyring()
        return self._delegate_cache

    # -- blob helpers -------------------------------------------------------

    def _read_blob(self, service: str) -> dict[str, str]:
        """Read and parse the blob. Raise on corruption; never assume empty.

        Treating a corrupt blob as empty would let the next write clobber
        every stored secret. Raising instead surfaces the problem and,
        because secret_store wraps keyring calls, degrades safely rather
        than destroying data.
        """
        raw = self._get_delegate().get_password(service, _BLOB_ACCOUNT)
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("secret blob is not a JSON object")
        return data

    def _write_blob(self, service: str, blob: dict[str, str]) -> None:
        self._get_delegate().set_password(service, _BLOB_ACCOUNT, json.dumps(blob))

    # -- KeyringBackend interface ------------------------------------------

    def get_password(self, service: str, username: str) -> str | None:
        # Item-level atomicity makes a lock unnecessary for a single read.
        blob = self._read_blob(service)
        value = blob.get(username)
        return value if value else None

    def set_password(self, service: str, username: str, password: str) -> None:
        with _blob_lock():
            blob = self._read_blob(service)  # raises on corruption, no clobber
            blob[username] = password
            self._write_blob(service, blob)

    def delete_password(self, service: str, username: str) -> None:
        with _blob_lock():
            blob = self._read_blob(service)
            if username in blob:
                del blob[username]
                self._write_blob(service, blob)


def should_use_consolidated_backend() -> bool:
    """Report whether the consolidated backend should be installed.

    True only on macOS, only when the active backend is the stock macOS
    one, and only when the user has not pinned a backend via the
    ``PYTHON_KEYRING_BACKEND`` env var. A backend configured through
    ``keyringrc.cfg`` becomes the active backend, so the stock-backend
    check below also defers to it.
    """
    if sys.platform != "darwin":
        return False
    if os.environ.get("PYTHON_KEYRING_BACKEND"):
        return False
    try:
        from keyring.backends import macOS as macos_backend

        current = keyring.get_keyring()
    except Exception:
        return False
    return isinstance(current, macos_backend.Keyring)


def install_consolidated_backend_if_appropriate() -> bool:
    """Install the consolidated backend when appropriate. Best-effort.

    Returns True when the backend was installed. Never raises: a failure
    here must leave the native backend in place rather than break startup.
    """
    try:
        if not should_use_consolidated_backend():
            return False
        keyring.set_keyring(ConsolidatedKeychainBackend())
        return True
    except Exception:
        return False
