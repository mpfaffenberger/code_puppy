"""Tests for code_puppy.secret_store_backends -- consolidated macOS backend.

Covers:
    1. gating -- should_use_consolidated_backend only on darwin + default
    2. blob storage -- N secrets share one keychain item
    3. concurrency-safety invariants -- corrupt blob never silently clobbered
    4. install helper -- best-effort, never raises
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# secret_store_backends imports fcntl which is POSIX-only. Skip the entire
# module on Windows before attempting the import so collection doesn't crash.
if sys.platform == "win32":
    pytest.skip(
        "secret_store_backends uses fcntl (POSIX-only); not applicable on Windows",
        allow_module_level=True,
    )

from code_puppy import secret_store_backends as ssb  # noqa: E402


# ---------------------------------------------------------------------------
# Gating: should_use_consolidated_backend
# ---------------------------------------------------------------------------


class TestGating:
    def test_false_off_darwin(self, monkeypatch):
        monkeypatch.setattr(ssb.sys, "platform", "linux")
        assert ssb.should_use_consolidated_backend() is False

    def test_false_when_user_pinned_backend(self, monkeypatch):
        monkeypatch.setattr(ssb.sys, "platform", "darwin")
        monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.fail.Keyring")
        assert ssb.should_use_consolidated_backend() is False

    def test_true_on_darwin_with_stock_backend(self, monkeypatch):
        monkeypatch.setattr(ssb.sys, "platform", "darwin")
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)
        from keyring.backends import macOS as macos_backend

        with patch.object(
            ssb.keyring, "get_keyring", return_value=macos_backend.Keyring()
        ):
            assert ssb.should_use_consolidated_backend() is True

    def test_false_when_active_backend_not_stock_macos(self, monkeypatch):
        monkeypatch.setattr(ssb.sys, "platform", "darwin")
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)
        with patch.object(ssb.keyring, "get_keyring", return_value=MagicMock()):
            assert ssb.should_use_consolidated_backend() is False

    def test_false_when_get_keyring_raises(self, monkeypatch):
        monkeypatch.setattr(ssb.sys, "platform", "darwin")
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)
        with patch.object(ssb.keyring, "get_keyring", side_effect=RuntimeError("boom")):
            assert ssb.should_use_consolidated_backend() is False


# ---------------------------------------------------------------------------
# Blob storage behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """A ConsolidatedKeychainBackend whose delegate is an in-memory store."""
    monkeypatch.setattr(ssb, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ssb, "_LOCK_FILE", str(tmp_path / ".secrets.lock"))

    store: dict[tuple[str, str], str] = {}
    delegate = MagicMock()
    delegate.get_password = MagicMock(side_effect=lambda s, a: store.get((s, a)))
    delegate.set_password = MagicMock(
        side_effect=lambda s, a, v: store.__setitem__((s, a), v)
    )

    with patch.object(ssb.ConsolidatedKeychainBackend, "__init__", lambda self: None):
        be = ssb.ConsolidatedKeychainBackend()
    be._delegate_cache = delegate
    return be, store


class TestBlobStorage:
    def test_multiple_secrets_share_one_item(self, backend):
        be, store = backend
        be.set_password("code-puppy", "a", "1")
        be.set_password("code-puppy", "b", "2")
        be.set_password("code-puppy", "c", "3")
        # Exactly one keychain item exists, holding all three.
        assert len(store) == 1
        blob = json.loads(next(iter(store.values())))
        assert blob == {"a": "1", "b": "2", "c": "3"}

    def test_roundtrip(self, backend):
        be, _ = backend
        be.set_password("code-puppy", "tok", "hunter2")
        assert be.get_password("code-puppy", "tok") == "hunter2"

    def test_get_missing_returns_none(self, backend):
        be, _ = backend
        assert be.get_password("code-puppy", "nope") is None

    def test_delete_removes_only_that_key(self, backend):
        be, store = backend
        be.set_password("code-puppy", "a", "1")
        be.set_password("code-puppy", "b", "2")
        be.delete_password("code-puppy", "a")
        blob = json.loads(next(iter(store.values())))
        assert blob == {"b": "2"}

    def test_distinct_services_get_distinct_items(self, backend):
        be, store = backend
        be.set_password("code-puppy", "tok", "oss")
        be.set_password("code-puppy-enterprise", "tok", "ent")
        assert len(store) == 2
        assert be.get_password("code-puppy", "tok") == "oss"
        assert be.get_password("code-puppy-enterprise", "tok") == "ent"


class TestCorruptionSafety:
    def test_corrupt_blob_raises_not_clobbers(self, backend):
        be, store = backend
        # Simulate an unparseable existing blob.
        store[("code-puppy", ssb._BLOB_ACCOUNT)] = "{ not json"
        with pytest.raises(json.JSONDecodeError):
            be.set_password("code-puppy", "a", "1")
        # The bad blob is left intact; no silent overwrite.
        assert store[("code-puppy", ssb._BLOB_ACCOUNT)] == "{ not json"

    def test_non_object_blob_rejected(self, backend):
        be, store = backend
        store[("code-puppy", ssb._BLOB_ACCOUNT)] = json.dumps(["not", "a", "dict"])
        with pytest.raises(ValueError, match="not a JSON object"):
            be.get_password("code-puppy", "a")


# ---------------------------------------------------------------------------
# install_consolidated_backend_if_appropriate
# ---------------------------------------------------------------------------


class TestInstall:
    def test_installs_when_appropriate(self):
        with (
            patch.object(ssb, "should_use_consolidated_backend", return_value=True),
            patch.object(ssb.keyring, "set_keyring") as set_kr,
        ):
            assert ssb.install_consolidated_backend_if_appropriate() is True
            set_kr.assert_called_once()

    def test_skips_when_not_appropriate(self):
        with (
            patch.object(ssb, "should_use_consolidated_backend", return_value=False),
            patch.object(ssb.keyring, "set_keyring") as set_kr,
        ):
            assert ssb.install_consolidated_backend_if_appropriate() is False
            set_kr.assert_not_called()

    def test_never_raises(self):
        with patch.object(
            ssb, "should_use_consolidated_backend", side_effect=RuntimeError("boom")
        ):
            # Must swallow and report False, never propagate.
            assert ssb.install_consolidated_backend_if_appropriate() is False
