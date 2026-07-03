"""Tests for code_puppy.secret_store -- generic OS keyring wrapper.

Covers the three paths called out in the subtask:
    1. keyring available   -- reads/writes route through the OS keyring
    2. keyring missing      -- operations degrade to the file fallback
    3. fallback file        -- 0o600 perms, atomic write, read-repair
"""

import json
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import secret_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_warn_flag():
    """The one-shot fallback warning is process global; reset per test."""
    secret_store._warned_fallback = False
    secret_store._backend_installed = True  # skip lazy install in these tests
    yield
    secret_store._warned_fallback = False
    secret_store._backend_installed = False


@pytest.fixture
def tmp_fallback(tmp_path, monkeypatch):
    """Point the fallback file + config dir at a temp location."""
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    fallback = cfg_dir / "secrets.json"
    monkeypatch.setattr(secret_store, "CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(secret_store, "_FALLBACK_FILE", str(fallback))
    return fallback


@pytest.fixture
def working_keyring():
    """A keyring with a healthy backend and an in-memory store."""
    store: dict[tuple[str, str], str] = {}
    fake = MagicMock()

    fake.get_password = MagicMock(
        side_effect=lambda service, name: store.get((service, name))
    )

    def _set(service, name, value):
        store[(service, name)] = value

    def _delete(service, name):
        key = (service, name)
        if key not in store:
            raise Exception("not found")
        del store[key]

    fake.set_password = MagicMock(side_effect=_set)
    fake.delete_password = MagicMock(side_effect=_delete)

    backend = MagicMock()
    backend.priority = 10
    fake.get_keyring = MagicMock(return_value=backend)

    with patch.object(secret_store, "keyring", fake):
        yield fake, store


@pytest.fixture
def missing_keyring():
    """A keyring whose backend is unavailable (priority 0, ops raise)."""
    fake = MagicMock()
    fake.get_password = MagicMock(side_effect=Exception("no backend"))
    fake.set_password = MagicMock(side_effect=Exception("no backend"))
    fake.delete_password = MagicMock(side_effect=Exception("no backend"))

    backend = MagicMock()
    backend.priority = 0
    fake.get_keyring = MagicMock(return_value=backend)

    with patch.object(secret_store, "keyring", fake):
        yield fake


# ---------------------------------------------------------------------------
# 1. keyring_available
# ---------------------------------------------------------------------------


class TestKeyringAvailable:
    def test_true_for_healthy_backend(self, working_keyring):
        assert secret_store.keyring_available() is True

    def test_false_for_priority_zero(self, missing_keyring):
        assert secret_store.keyring_available() is False

    def test_true_when_priority_missing(self):
        fake = MagicMock()
        backend = MagicMock(spec=[])  # no .priority attribute
        fake.get_keyring = MagicMock(return_value=backend)
        with patch.object(secret_store, "keyring", fake):
            assert secret_store.keyring_available() is True

    def test_false_when_get_keyring_raises(self):
        fake = MagicMock()
        fake.get_keyring = MagicMock(side_effect=RuntimeError("boom"))
        with patch.object(secret_store, "keyring", fake):
            assert secret_store.keyring_available() is False


# ---------------------------------------------------------------------------
# 2. keyring-available path
# ---------------------------------------------------------------------------


class TestKeyringPath:
    def test_set_then_get_roundtrip(self, working_keyring, tmp_fallback):
        _, store = working_keyring
        secret_store.set_secret("my_key", "hunter2")
        assert store[(secret_store._SERVICE_NAME, "my_key")] == "hunter2"
        assert secret_store.get_secret("my_key") == "hunter2"

    def test_get_missing_returns_none(self, working_keyring):
        assert secret_store.get_secret("nope") is None

    def test_get_strips_whitespace(self, working_keyring):
        _, store = working_keyring
        store[(secret_store._SERVICE_NAME, "k")] = "  spaced  "
        assert secret_store.get_secret("k") == "spaced"

    def test_delete_removes_from_keyring(self, working_keyring):
        _, store = working_keyring
        store[(secret_store._SERVICE_NAME, "k")] = "v"
        secret_store.delete_secret("k")
        assert (secret_store._SERVICE_NAME, "k") not in store

    def test_set_does_not_write_fallback_file(self, working_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        assert not os.path.exists(tmp_fallback)

    def test_get_ignores_fallback_when_keyring_healthy(
        self, working_keyring, tmp_fallback
    ):
        # A stale fallback file must not shadow a healthy (empty) keyring.
        tmp_fallback.write_text(json.dumps({"k": "stale"}))
        assert secret_store.get_secret("k") is None


# ---------------------------------------------------------------------------
# 3. keyring-missing / file fallback path
# ---------------------------------------------------------------------------


class TestFallbackPath:
    def test_set_writes_fallback_file(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        assert tmp_fallback.exists()
        assert json.loads(tmp_fallback.read_text())["k"] == "v"

    def test_set_then_get_roundtrip(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        assert secret_store.get_secret("k") == "v"

    def test_get_missing_returns_none(self, missing_keyring, tmp_fallback):
        assert secret_store.get_secret("nope") is None

    def test_fallback_file_is_0600(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        mode = stat.S_IMODE(os.stat(tmp_fallback).st_mode)
        assert mode == 0o600

    def test_read_repairs_loose_permissions(self, missing_keyring, tmp_fallback):
        tmp_fallback.write_text(json.dumps({"k": "v"}))
        os.chmod(tmp_fallback, 0o644)
        assert secret_store.get_secret("k") == "v"
        mode = stat.S_IMODE(os.stat(tmp_fallback).st_mode)
        assert mode == 0o600

    def test_set_blank_is_ignored(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "   ")
        assert not tmp_fallback.exists()

    def test_delete_removes_from_fallback(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        secret_store.set_secret("keep", "me")
        secret_store.delete_secret("k")
        data = json.loads(tmp_fallback.read_text())
        assert "k" not in data
        assert data["keep"] == "me"

    def test_set_preserves_existing_keys(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("a", "1")
        secret_store.set_secret("b", "2")
        data = json.loads(tmp_fallback.read_text())
        assert data == {"a": "1", "b": "2"}

    def test_corrupt_fallback_file_is_tolerated(self, missing_keyring, tmp_fallback):
        tmp_fallback.write_text("{ not valid json")
        assert secret_store.get_secret("k") is None
        # A subsequent write recovers the file.
        secret_store.set_secret("k", "v")
        assert secret_store.get_secret("k") == "v"

    def test_fallback_emits_warning_once(self, missing_keyring, tmp_fallback):
        with pytest.warns(UserWarning, match="fallback"):
            secret_store.set_secret("k", "v")
        # Second op must not warn again (one-shot guard).
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("error")
            secret_store.set_secret("k2", "v2")  # would raise if it warned
