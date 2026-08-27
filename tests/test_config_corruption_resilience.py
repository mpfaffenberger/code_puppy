"""Regression tests for code_puppy.config_file's corruption tolerance.

Background: a user hit an uncaught ``MemoryError`` bubbling out of
``configparser.ConfigParser().read(CONFIG_FILE)`` deep inside a startup
callback (theme plugin -> set_config_value -> config.read). The first pass
at a fix (catch-and-quarantine around a raw ``config.read()``) survived an
adversarial review that found it would misclassify transient I/O errors as
corruption, race with concurrent processes between read and quarantine, and
let same-instant quarantine attempts clobber each other. This suite pins the
hardened design in :mod:`code_puppy.config_file`:

* reads are byte-bounded, so a pathological file can never balloon memory;
* only confirmed parse/decode/oversize corruption is quarantined;
* transient OSError (e.g. permission errors) propagates untouched;
* quarantine is collision-resistant and never overwrites a prior backup;
* recovery re-checks under a cross-process lock before moving anything; and
* writes go through a locked, atomic temp-file-then-replace transaction.
"""

import glob
import os
import threading
import time
from unittest.mock import patch

import configparser
import pytest

from code_puppy import atomic_io, config as cp_config
from code_puppy import config_file


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    """Point CONFIG_FILE at a real (temp) path so os.link/replace behave."""
    cfg_dir = tmp_path / "cfgdir"
    cfg_dir.mkdir()
    path = cfg_dir / "puppy.cfg"
    monkeypatch.setattr(cp_config, "CONFIG_FILE", str(path))
    return path


class TestLoadConfigCorruption:
    def test_malformed_ini_does_not_raise(self, cfg_path):
        cfg_path.write_text("this is not [valid ini at all\nnope=nope=nope\n")

        config = config_file.load_config(str(cfg_path))

        assert isinstance(config, configparser.ConfigParser)

    def test_malformed_ini_gets_quarantined_not_deleted(self, cfg_path):
        cfg_path.write_text("this is not [valid ini at all\nnope=nope=nope\n")

        config_file.load_config(str(cfg_path))

        assert not cfg_path.exists()
        backups = glob.glob(f"{cfg_path}.corrupted-*")
        assert len(backups) == 1
        assert "not [valid ini" in open(backups[0]).read()

    def test_invalid_utf8_is_quarantined(self, cfg_path):
        cfg_path.write_bytes(b"\xff\xfe garbage \x00\x00 noutf8 [[[" )

        config = config_file.load_config(str(cfg_path))

        assert isinstance(config, configparser.ConfigParser)
        assert glob.glob(f"{cfg_path}.corrupted-*")

    def test_utf8_bom_is_accepted_without_quarantine(self, cfg_path):
        cfg_path.write_bytes("[puppy]\nowner_name = María\n".encode("utf-8-sig"))

        config = config_file.load_config(str(cfg_path))

        assert config.get("puppy", "owner_name") == "María"
        assert not glob.glob(f"{cfg_path}.corrupted-*")

    def test_windows_locale_encoded_config_is_accepted(self, cfg_path, monkeypatch):
        cfg_path.write_bytes("[puppy]\nowner_name = María\n".encode("cp1252"))
        monkeypatch.setattr(config_file.os, "name", "nt", raising=False)
        monkeypatch.setattr(
            config_file.locale,
            "getpreferredencoding",
            lambda _do_setlocale=False: "cp1252",
        )

        config = config_file.load_config(str(cfg_path))

        assert config.get("puppy", "owner_name") == "María"
        assert not glob.glob(f"{cfg_path}.corrupted-*")

    def test_windows_locale_fallback_logs_warning(self, cfg_path, monkeypatch, caplog):
        cfg_path.write_bytes("[puppy]\nowner_name = María\n".encode("cp1252"))
        monkeypatch.setattr(config_file.os, "name", "nt", raising=False)
        monkeypatch.setattr(
            config_file.locale,
            "getpreferredencoding",
            lambda _do_setlocale=False: "cp1252",
        )

        with caplog.at_level("WARNING"):
            config_file.load_config(str(cfg_path))

        assert any(
            "Windows locale fallback encoding" in message
            for message in caplog.messages
        )

    def test_windows_locale_fallback_rejects_non_ini_text(self, cfg_path, monkeypatch):
        cfg_path.write_bytes(b"\x96\x97\x98\x99\x80")
        monkeypatch.setattr(config_file.os, "name", "nt", raising=False)
        monkeypatch.setattr(
            config_file.locale,
            "getpreferredencoding",
            lambda _do_setlocale=False: "cp1252",
        )

        config = config_file.load_config(str(cfg_path))

        assert isinstance(config, configparser.ConfigParser)
        assert glob.glob(f"{cfg_path}.corrupted-*")

    def test_healthy_config_is_left_untouched(self, cfg_path):
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        config = config_file.load_config(str(cfg_path))

        assert config.get("puppy", "puppy_name") == "leoncito"
        assert not glob.glob(f"{cfg_path}.corrupted-*")

    def test_missing_file_returns_empty_config_without_error(self, cfg_path):
        # cfg_path was never created.
        config = config_file.load_config(str(cfg_path))

        assert isinstance(config, configparser.ConfigParser)
        assert config.sections() == []


class TestOversizedConfigIsBoundedNotBallooned:
    """Pins the actual field-report scenario: a pathological file must never
    reach configparser's own unbounded line reader in the first place."""

    def test_oversized_file_is_quarantined_without_full_read(
        self, cfg_path, monkeypatch
    ):
        monkeypatch.setattr(config_file, "MAX_CONFIG_BYTES", 1024)
        # One giant unterminated "line" -- the exact shape that made stdlib
        # configparser's buffered readline balloon memory in the field report.
        cfg_path.write_bytes(b"x" * 4096)

        config = config_file.load_config(str(cfg_path))

        assert isinstance(config, configparser.ConfigParser)
        assert glob.glob(f"{cfg_path}.corrupted-*")

    def test_read_never_buffers_past_the_bound(self, cfg_path, monkeypatch):
        """Even if the file's reported size lies (e.g. a sparse file, or a
        pipe/device whose ``stat`` size is unreliable), the actual ``read()``
        call itself must still be bounded rather than pulling the whole
        pathological file into memory. This directly targets the field
        report's failure mode: stdlib configparser's buffered readline
        ballooning memory on a giant unterminated line. The bound now lives
        in the shared ``code_puppy.atomic_io`` primitive."""
        monkeypatch.setattr(config_file, "MAX_CONFIG_BYTES", 1024)
        cfg_path.write_bytes(b"y" * (5 * 1024 * 1024))
        # Make the pre-flight os.path.getsize check lie about the size so
        # execution reaches the actual bounded read() call below.
        monkeypatch.setattr(atomic_io.os.path, "getsize", lambda _p: 10)

        real_open = open
        captured_sizes = []

        class _TrackingFile:
            def __init__(self, fh):
                self._fh = fh

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._fh.close()
                return False

            def read(self, n=-1):
                data = self._fh.read(n)
                captured_sizes.append(len(data))
                return data

        def _tracking_open(path, mode="r"):
            if mode == "rb":
                return _TrackingFile(real_open(path, mode))
            return real_open(path, mode)

        with patch("code_puppy.atomic_io.open", _tracking_open, create=True):
            config_file.load_config(str(cfg_path))

        assert captured_sizes, "expected the bounded read to be exercised"
        assert all(size <= 1025 for size in captured_sizes)


class TestQuarantineCollisionSafety:
    """Pins the reviewer's collision finding: two recoveries landing on the
    same name must never clobber each other's backup."""

    def test_repeated_corruption_never_overwrites_prior_backup(self, cfg_path):
        cfg_path.write_text("first corrupt payload [[[")
        config_file.load_config(str(cfg_path))
        first_backup = glob.glob(f"{cfg_path}.corrupted-*")
        assert len(first_backup) == 1

        cfg_path.write_text("second corrupt payload [[[")
        config_file.load_config(str(cfg_path))

        backups = sorted(glob.glob(f"{cfg_path}.corrupted-*"))
        assert len(backups) == 2
        contents = {open(b).read() for b in backups}
        assert contents == {"first corrupt payload [[[", "second corrupt payload [[["}

    def test_forced_name_collision_retries_instead_of_overwriting(self, cfg_path):
        """Simulates two processes computing the identical quarantine name."""
        cfg_path.write_text("corrupt payload [[[")

        real_link = os.link
        call_count = {"n": 0}

        def _flaky_link(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Pre-create the "colliding" destination as another process
                # would have, forcing our retry loop to pick a new name.
                with open(dst, "w") as f:
                    f.write("someone else's backup")
                raise FileExistsError(dst)
            return real_link(src, dst)

        with patch("os.link", side_effect=_flaky_link):
            config_file.load_config(str(cfg_path))

        backups = glob.glob(f"{cfg_path}.corrupted-*")
        # The pre-created collision file plus our own successfully-retried backup.
        assert len(backups) == 2
        contents = {open(b).read() for b in backups}
        assert "someone else's backup" in contents
        assert "corrupt payload [[[" in contents


class TestTransientIoErrorsPropagate:
    """A permissions blip or flaky network mount is not proof of corruption;
    quarantining (and silently losing) a healthy file on transient I/O
    failure was one of the reviewer's HIGH findings."""

    def test_permission_error_on_read_propagates_and_is_not_quarantined(self, cfg_path):
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        with patch("builtins.open", side_effect=PermissionError("locked by AV")):
            with pytest.raises(PermissionError):
                config_file.load_config(str(cfg_path))

        # The healthy file must still be exactly where it was.
        assert cfg_path.exists()
        assert not glob.glob(f"{cfg_path}.corrupted-*")

    def test_get_value_does_not_swallow_transient_os_errors(self, cfg_path):
        """Public accessors should not pretend a disk hiccup means 'no value'."""
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        with patch("builtins.open", side_effect=OSError("device not ready")):
            with pytest.raises(OSError):
                cp_config.get_value("puppy_name")


class TestRecoveryTocTou:
    """Pins the reviewer's race finding: if another process fixes the file
    between our first bad read and quarantine, we must not clobber the fix."""

    def test_second_read_under_lock_wins_over_stale_corruption(self, cfg_path):
        original_read_unlocked = config_file._read_unlocked
        call_count = {"n": 0}

        def _fake_read(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise config_file.ConfigFileCorrupt("simulated first-pass failure")
            # Simulate a concurrent process having repaired the file just
            # before we acquired the lock for the confirming re-read.
            return original_read_unlocked(path)

        cfg_path.write_text("[puppy]\npuppy_name = fixed-by-another-process\n")

        with patch.object(config_file, "_read_unlocked", side_effect=_fake_read):
            config = config_file.load_config(str(cfg_path))

        assert config.get("puppy", "puppy_name") == "fixed-by-another-process"
        assert not glob.glob(f"{cfg_path}.corrupted-*")
        assert cfg_path.exists()


class TestAtomicWriteAndLocking:
    def test_set_config_value_survives_corrupted_config(self, cfg_path):
        """The exact field-report call chain: theme plugin -> _apply_theme
        -> set_config_value -> config read/write."""
        cfg_path.write_text("not\nvalid\nini\n[[[")

        cp_config.set_config_value("active_theme", "dracula")

        assert cp_config.get_value("active_theme") == "dracula"

    def test_write_failure_never_touches_the_original_file(self, cfg_path):
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        with patch("os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                cp_config.set_config_value("active_theme", "dracula")

        # Original content must be intact -- no partial/truncated write.
        assert cfg_path.read_text() == "[puppy]\npuppy_name = leoncito\n"
        # And no stray temp files left behind in the config directory.
        leftovers = [
            f for f in os.listdir(cfg_path.parent) if f.startswith(".puppy.cfg-")
        ]
        assert leftovers == []

    def test_concurrent_mutations_do_not_lose_updates(self, cfg_path):
        """Two threads racing set_config_value must not stomp each other --
        this is what the shared cross-process lock in mutate_config buys us."""
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        def _writer(key, value):
            cp_config.set_config_value(key, value)

        threads = [
            threading.Thread(target=_writer, args=(f"key_{i}", f"value_{i}"))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for i in range(8):
            assert cp_config.get_value(f"key_{i}") == f"value_{i}"

    def test_reset_value_skips_write_when_key_absent(self, cfg_path):
        """mutate_config's False-return short-circuit must avoid a no-op write."""
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")
        original_mtime_ns = os.stat(cfg_path).st_mtime_ns
        time.sleep(0.01)

        cp_config.reset_value("does_not_exist")

        assert os.stat(cfg_path).st_mtime_ns == original_mtime_ns

    def test_lock_timeout_raises_rather_than_hanging_forever(self, cfg_path):
        cfg_path.write_text("[puppy]\npuppy_name = leoncito\n")

        with patch.object(config_file, "_LOCK_TIMEOUT_SECONDS", 0.2):
            with config_file._config_lock(str(cfg_path)):
                # Lock is held (this thread simulates "another process") for
                # longer than the bounded wait attempted below.
                with pytest.raises(config_file.ConfigLockTimeout):
                    with config_file._config_lock(str(cfg_path)):
                        pass  # pragma: no cover - should never be reached
