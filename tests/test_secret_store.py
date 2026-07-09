"""Tests for code_puppy.secret_store -- generic OS keyring wrapper.

Covers the three paths called out in the subtask:
    1. keyring available   -- reads/writes route through the OS keyring
    2. keyring missing      -- operations degrade to the file fallback
    3. fallback file        -- 0o600 perms, atomic write, read-repair

Plus the configurable service name for downstream distributions.
"""

import json
import os
import stat
import sys
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import secret_store


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset process-global state between tests."""
    secret_store._warned_fallback = False
    secret_store._service_name = "code-puppy"
    secret_store._backend_installed = True  # skip lazy install in these tests
    yield
    secret_store._warned_fallback = False
    secret_store._service_name = "code-puppy"
    secret_store._backend_installed = False


@pytest.fixture
def tmp_fallback(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    fallback = cfg_dir / "secrets.json"
    monkeypatch.setattr(secret_store, "CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(secret_store, "_FALLBACK_FILE", str(fallback))
    return fallback


@pytest.fixture
def working_keyring():
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
# configure_service_name
# ---------------------------------------------------------------------------


class TestServiceName:
    def test_default(self):
        assert secret_store.get_service_name() == "code-puppy"

    def test_override(self):
        secret_store.configure_service_name("my-custom-distribution")
        assert secret_store.get_service_name() == "my-custom-distribution"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="non-empty"):
            secret_store.configure_service_name("  ")

    def test_secrets_land_under_configured_name(self, working_keyring):
        _, store = working_keyring
        secret_store.configure_service_name("my-custom-distribution")
        secret_store.set_secret("tok", "v")
        assert ("my-custom-distribution", "tok") in store
        assert ("code-puppy", "tok") not in store


# ---------------------------------------------------------------------------
# keyring_available
# ---------------------------------------------------------------------------


class TestKeyringAvailable:
    def test_true_for_healthy_backend(self, working_keyring):
        assert secret_store.keyring_available() is True

    def test_false_for_priority_zero(self, missing_keyring):
        assert secret_store.keyring_available() is False

    def test_true_when_priority_missing(self):
        fake = MagicMock()
        backend = MagicMock(spec=[])
        fake.get_keyring = MagicMock(return_value=backend)
        with patch.object(secret_store, "keyring", fake):
            assert secret_store.keyring_available() is True

    def test_false_when_get_keyring_raises(self):
        fake = MagicMock()
        fake.get_keyring = MagicMock(side_effect=RuntimeError("boom"))
        with patch.object(secret_store, "keyring", fake):
            assert secret_store.keyring_available() is False


# ---------------------------------------------------------------------------
# keyring-available path
# ---------------------------------------------------------------------------


class TestKeyringPath:
    def test_set_then_get_roundtrip(self, working_keyring, tmp_fallback):
        _, store = working_keyring
        secret_store.set_secret("my_key", "hunter2")
        assert store[(secret_store._service_name, "my_key")] == "hunter2"
        assert secret_store.get_secret("my_key") == "hunter2"

    def test_get_missing_returns_none(self, working_keyring):
        assert secret_store.get_secret("nope") is None

    def test_get_preserves_whitespace(self, working_keyring):
        """Secrets are stored/returned verbatim -- leading/trailing whitespace
        that is part of the value must survive the round-trip (F8)."""
        _, store = working_keyring
        store[(secret_store._service_name, "k")] = "  spaced  "
        assert secret_store.get_secret("k") == "  spaced  "

    def test_delete_removes_from_keyring(self, working_keyring):
        _, store = working_keyring
        store[(secret_store._service_name, "k")] = "v"
        secret_store.delete_secret("k")
        assert (secret_store._service_name, "k") not in store

    def test_set_does_not_write_fallback_file(self, working_keyring, tmp_fallback):
        """A successful keyring write must never touch the fallback file."""
        secret_store.set_secret("k", "v")
        assert not os.path.exists(tmp_fallback)

    def test_get_falls_through_to_fallback_as_last_resort(
        self, working_keyring, tmp_fallback
    ):
        """When keyring has no entry, the fallback file is consulted.

        This covers recovery from a prior session where both keyring strategies
        failed and set_secret wrote to the file as a last resort.
        """
        tmp_fallback.write_text(json.dumps({"k": "rescued"}))
        assert secret_store.get_secret("k") == "rescued"

    def test_keyring_value_takes_precedence_over_fallback(
        self, working_keyring, tmp_fallback
    ):
        """Keyring entry wins when both stores have a value for the same key."""
        _, store = working_keyring
        store[(secret_store._service_name, "k")] = "from-keyring"
        tmp_fallback.write_text(json.dumps({"k": "from-file"}))
        assert secret_store.get_secret("k") == "from-keyring"

    def test_set_warns_and_writes_file_when_keyring_fails(
        self, working_keyring, tmp_fallback
    ):
        """When all keyring writes fail despite a healthy backend, set_secret
        emits a warning then persists to the fallback file so the secret is
        not lost."""
        fake, _ = working_keyring
        fake.set_password.side_effect = Exception("backend crash")

        with pytest.warns(UserWarning, match="despite a healthy backend"):
            secret_store.set_secret("k", "v")

        assert tmp_fallback.exists()
        assert json.loads(tmp_fallback.read_text())["k"] == "v"

    def test_delete_also_cleans_fallback(self, working_keyring, tmp_fallback):
        """delete_secret always scrubs the fallback file, in case a prior write
        landed there as a last resort."""
        tmp_fallback.write_text(json.dumps({"k": "leftover", "other": "keep"}))
        secret_store.delete_secret("k")
        data = json.loads(tmp_fallback.read_text())
        assert "k" not in data
        assert data["other"] == "keep"


# ---------------------------------------------------------------------------
# Transparent chunking (Windows Credential Manager size-limit)
# ---------------------------------------------------------------------------


class TestChunking:
    """Verify that oversized secrets are split into <=_CHUNK_SIZE pieces and
    reassembled transparently.  Chunking keeps the keyring as the primary store;
    the file fallback is only reached if chunking itself also fails.
    """

    def test_large_value_stored_as_chunks(self, working_keyring):
        """A value that exceeds _CHUNK_SIZE is split into chunk keys."""
        _, store = working_keyring
        svc = secret_store._service_name
        big = "A" * (secret_store._CHUNK_SIZE * 2 + 100)  # 3 chunks
        secret_store.set_secret("tok", big)

        count_key = secret_store._chunk_count_key("tok")
        assert store.get((svc, count_key)) == "3"
        for i in range(3):
            assert (svc, secret_store._chunk_key("tok", i)) in store
        # Direct entry must NOT exist (unambiguous read path)
        assert (svc, "tok") not in store

    def test_large_value_roundtrip(self, working_keyring):
        """get_secret reassembles chunks to return the original value."""
        big = "Z" * (secret_store._CHUNK_SIZE * 3 + 50)
        secret_store.set_secret("tok", big)
        assert secret_store.get_secret("tok") == big

    def test_small_value_uses_direct_entry(self, working_keyring):
        """Values under the chunk threshold go to the direct key, not chunks."""
        _, store = working_keyring
        svc = secret_store._service_name
        secret_store.set_secret("small", "tiny")
        assert store.get((svc, "small")) == "tiny"
        assert (svc, secret_store._chunk_count_key("small")) not in store

    def test_stale_chunks_pruned_on_smaller_write(self, working_keyring):
        """If a secret shrinks from 3 chunks to 2, the 3rd chunk is removed."""
        _, store = working_keyring
        svc = secret_store._service_name
        big3 = "B" * (secret_store._CHUNK_SIZE * 2 + 100)  # 3 chunks
        secret_store.set_secret("tok", big3)
        assert store.get((svc, secret_store._chunk_count_key("tok"))) == "3"

        big2 = "C" * (secret_store._CHUNK_SIZE + 100)  # 2 chunks
        secret_store.set_secret("tok", big2)
        assert store.get((svc, secret_store._chunk_count_key("tok"))) == "2"
        assert (svc, secret_store._chunk_key("tok", 2)) not in store
        assert secret_store.get_secret("tok") == big2

    def test_delete_removes_all_chunk_keys(self, working_keyring):
        """delete_secret wipes the count key and every chunk entry."""
        _, store = working_keyring
        svc = secret_store._service_name
        big = "D" * (secret_store._CHUNK_SIZE * 2 + 1)  # 3 chunks
        secret_store.set_secret("tok", big)
        secret_store.delete_secret("tok")

        assert (svc, secret_store._chunk_count_key("tok")) not in store
        for i in range(3):
            assert (svc, secret_store._chunk_key("tok", i)) not in store

    def test_old_single_entry_still_readable(self, working_keyring):
        """Pre-chunking entries written without a count key are still readable."""
        _, store = working_keyring
        svc = secret_store._service_name
        store[(svc, "legacy")] = "old-value"
        assert secret_store.get_secret("legacy") == "old-value"

    def test_missing_chunk_returns_none(self, working_keyring):
        """A partially-written chunk sequence (count present, chunk missing)
        is treated as absent rather than returning corrupt data."""
        _, store = working_keyring
        svc = secret_store._service_name
        store[(svc, secret_store._chunk_count_key("tok"))] = "3"
        store[(svc, secret_store._chunk_key("tok", 0))] = "part0"
        # chunk 1 and 2 missing
        assert secret_store.get_secret("tok") is None

    def test_direct_entry_removed_after_chunked_write(self, working_keyring):
        """Writing a small value then a large one leaves no direct entry."""
        _, store = working_keyring
        svc = secret_store._service_name
        secret_store.set_secret("tok", "small")
        assert (svc, "tok") in store

        secret_store.set_secret("tok", "X" * (secret_store._CHUNK_SIZE * 2))
        assert (svc, "tok") not in store

    def test_chunk_keys_cleaned_on_revert_to_small(self, working_keyring):
        """Writing a large value then a small one removes all chunk keys."""
        _, store = working_keyring
        svc = secret_store._service_name
        secret_store.set_secret("tok", "X" * (secret_store._CHUNK_SIZE * 2))
        assert (svc, secret_store._chunk_count_key("tok")) in store

        secret_store.set_secret("tok", "small")
        assert (svc, secret_store._chunk_count_key("tok")) not in store
        assert store.get((svc, "tok")) == "small"


# ---------------------------------------------------------------------------
# keyring-missing / file fallback path
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

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="NTFS does not enforce POSIX permission bits via os.chmod",
    )
    def test_fallback_file_is_0600(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        assert stat.S_IMODE(os.stat(tmp_fallback).st_mode) == 0o600

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="NTFS does not enforce POSIX permission bits via os.chmod",
    )
    def test_read_repairs_loose_permissions(self, missing_keyring, tmp_fallback):
        tmp_fallback.write_text(json.dumps({"k": "v"}))
        os.chmod(tmp_fallback, 0o644)
        assert secret_store.get_secret("k") == "v"
        assert stat.S_IMODE(os.stat(tmp_fallback).st_mode) == 0o600

    def test_set_blank_raises(self, missing_keyring, tmp_fallback):
        """Empty/whitespace-only values raise ValueError instead of silently
        no-oping and emitting a misleading backend-failure warning (F8)."""
        with pytest.raises(ValueError, match="non-empty"):
            secret_store.set_secret("k", "   ")
        assert not tmp_fallback.exists()

    def test_delete_removes_from_fallback(self, missing_keyring, tmp_fallback):
        secret_store.set_secret("k", "v")
        secret_store.set_secret("keep", "me")
        secret_store.delete_secret("k")
        data = json.loads(tmp_fallback.read_text())
        assert "k" not in data
        assert data["keep"] == "me"

    def test_corrupt_fallback_tolerated(self, missing_keyring, tmp_fallback):
        tmp_fallback.write_text("{ not valid json")
        assert secret_store.get_secret("k") is None
        secret_store.set_secret("k", "v")
        assert secret_store.get_secret("k") == "v"

    def test_fallback_warns_once(self, missing_keyring, tmp_fallback):
        import warnings as _w

        with pytest.warns(UserWarning, match="fallback"):
            secret_store.set_secret("k", "v")
        with _w.catch_warnings():
            _w.simplefilter("error")
            secret_store.set_secret("k2", "v2")


# ---------------------------------------------------------------------------
# Cross-platform fixes
# ---------------------------------------------------------------------------


class TestCrossPlatform:
    def test_ensure_backend_survives_import_error(self):
        """_ensure_backend must not crash when secret_store_backends is
        unimportable (e.g. Windows where fcntl doesn't exist)."""
        secret_store._backend_installed = False
        with patch.dict("sys.modules", {"code_puppy.secret_store_backends": None}):
            # Should complete without raising.
            secret_store._ensure_backend()
        assert secret_store._backend_installed is True

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="NTFS does not enforce POSIX permission bits via os.chmod",
    )
    def test_write_fallback_uses_chmod(self, tmp_fallback):
        """_write_fallback uses os.chmod (cross-platform), not os.fchmod."""
        assert secret_store._write_fallback({"k": "v"}) is True
        assert json.loads(tmp_fallback.read_text()) == {"k": "v"}
        mode = stat.S_IMODE(os.stat(tmp_fallback).st_mode)
        assert mode == 0o600


# ---------------------------------------------------------------------------
# F9 -- reserved ':cp:' namespace is enforced on caller-supplied names
# ---------------------------------------------------------------------------


class TestReservedNamespace:
    """A caller name containing ':cp:' must be rejected before it can shadow
    or destroy chunk metadata (PR #531 review finding F9)."""

    def test_set_rejects_reserved_substring(self, working_keyring):
        with pytest.raises(ValueError, match="reserved substring"):
            secret_store.set_secret("foo:cp:n", "3")

    def test_get_rejects_reserved_substring(self, working_keyring):
        with pytest.raises(ValueError, match="reserved substring"):
            secret_store.get_secret("foo:cp:0")

    def test_delete_rejects_reserved_substring(self, working_keyring):
        with pytest.raises(ValueError, match="reserved substring"):
            secret_store.delete_secret("foo:cp:n")

    def test_empty_name_rejected(self, working_keyring):
        with pytest.raises(ValueError, match="non-empty string"):
            secret_store.set_secret("", "v")

    def test_shadow_attack_cannot_poison_count_marker(self, working_keyring):
        """Rejecting 'foo:cp:n' means a real 'foo' entry can't be shadowed by
        a bogus chunk-count marker."""
        secret_store.set_secret("foo", "legit")
        with pytest.raises(ValueError):
            secret_store.set_secret("foo:cp:n", "3")
        assert secret_store.get_secret("foo") == "legit"


# ---------------------------------------------------------------------------
# F8 -- empty value raises; whitespace-bearing values are preserved verbatim
# ---------------------------------------------------------------------------


class TestValueNormalization:
    def test_empty_string_raises(self, working_keyring):
        with pytest.raises(ValueError, match="non-empty"):
            secret_store.set_secret("k", "")

    def test_whitespace_only_raises(self, working_keyring):
        with pytest.raises(ValueError, match="non-empty"):
            secret_store.set_secret("k", "\t \n")

    def test_surrounding_whitespace_preserved_keyring(self, working_keyring):
        secret_store.set_secret("k", "  tok-with-spaces  ")
        assert secret_store.get_secret("k") == "  tok-with-spaces  "

    def test_surrounding_whitespace_preserved_fallback(
        self, missing_keyring, tmp_fallback
    ):
        with pytest.warns(UserWarning):
            secret_store.set_secret("k", "  tok  ")
        assert secret_store.get_secret("k") == "  tok  "

    def test_no_false_alarm_warning_on_empty(self, working_keyring, tmp_fallback):
        """An empty value must not reach the 'keyring write failed' path."""
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("error")
            with pytest.raises(ValueError):
                secret_store.set_secret("k", "  ")


# ---------------------------------------------------------------------------
# F3/F4/F10 -- uniform fallback failure contract; callers surface failures
# ---------------------------------------------------------------------------


class TestFallbackFailureContract:
    def test_write_fallback_returns_false_on_mkstemp_error(self, tmp_fallback):
        """F3: a mkstemp failure returns False instead of raising raw OSError."""
        with patch("tempfile.mkstemp", side_effect=OSError("read-only fs")):
            assert secret_store._write_fallback({"k": "v"}) is False

    def test_write_fallback_returns_false_on_replace_error(self, tmp_fallback):
        with patch("os.replace", side_effect=OSError("disk full")):
            assert secret_store._write_fallback({"k": "v"}) is False

    def test_set_raises_when_fallback_write_fails(self, missing_keyring, tmp_fallback):
        """F4: a lost credential must not report success."""
        with patch.object(secret_store, "_write_fallback", return_value=False):
            with pytest.warns(UserWarning):
                with pytest.raises(secret_store.SecretStoreError, match="NOT saved"):
                    secret_store.set_secret("k", "v")

    def test_delete_raises_when_scrub_write_fails(self, missing_keyring, tmp_fallback):
        """F10: a failed scrub must not report a successful delete."""
        tmp_fallback.write_text(json.dumps({"k": "leftover"}))
        with patch.object(secret_store, "_write_fallback", return_value=False):
            with pytest.raises(secret_store.SecretStoreError, match="still be present"):
                secret_store.delete_secret("k")

    def test_delete_absent_key_does_not_raise(self, missing_keyring, tmp_fallback):
        """No fallback entry -> nothing to scrub -> no error even if write would fail."""
        tmp_fallback.write_text(json.dumps({"other": "keep"}))
        with patch.object(secret_store, "_write_fallback", return_value=False):
            secret_store.delete_secret("k")  # must not raise
