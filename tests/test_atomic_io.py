"""Direct tests for code_puppy.atomic_io -- the shared bounded-read /
cross-process-lock / atomic-write primitives that code_puppy.config_file
(INI) and code_puppy.atomic_json (JSON) both build on.

These pin the generic contract independent of any file format, since a bug
here would silently affect every config surface built on top.
"""

import glob
import os
import time
from unittest.mock import patch

import pytest

from code_puppy import atomic_io


@pytest.fixture
def target_path(tmp_path):
    return tmp_path / "state.bin"


class TestReadBoundedBytes:
    def test_missing_file_returns_empty_bytes(self, target_path):
        assert atomic_io.read_bounded_bytes(str(target_path)) == b""

    def test_reads_small_file_fully(self, target_path):
        target_path.write_bytes(b"hello world")

        assert atomic_io.read_bounded_bytes(str(target_path)) == b"hello world"

    def test_oversized_file_raises_without_reading_it_all(self, target_path):
        target_path.write_bytes(b"z" * 4096)

        with pytest.raises(atomic_io.ContentTooLarge):
            atomic_io.read_bounded_bytes(str(target_path), max_bytes=1024)

    def test_read_call_itself_is_bounded_even_if_stat_lies(
        self, target_path, monkeypatch
    ):
        """A sparse file or unreliable stat() must not defeat the bound --
        the actual read() call is capped independent of the size pre-check."""
        target_path.write_bytes(b"y" * (5 * 1024 * 1024))
        monkeypatch.setattr(atomic_io.os.path, "getsize", lambda _p: 10)

        real_open = open
        captured = []

        class _Tracking:
            def __init__(self, fh):
                self._fh = fh

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._fh.close()
                return False

            def read(self, n=-1):
                data = self._fh.read(n)
                captured.append(len(data))
                return data

        def _tracking_open(path, mode="r"):
            if mode == "rb":
                return _Tracking(real_open(path, mode))
            return real_open(path, mode)

        with patch("code_puppy.atomic_io.open", _tracking_open, create=True):
            with pytest.raises(atomic_io.ContentTooLarge):
                atomic_io.read_bounded_bytes(str(target_path), max_bytes=1024)

        assert captured
        assert all(n <= 1025 for n in captured)


class TestQuarantineFile:
    def test_moves_original_and_returns_new_path(self, target_path):
        target_path.write_bytes(b"corrupt payload")

        quarantine_path = atomic_io.quarantine_file(str(target_path))

        assert not target_path.exists()
        assert os.path.exists(quarantine_path)
        assert open(quarantine_path, "rb").read() == b"corrupt payload"

    def test_never_overwrites_a_prior_backup(self, target_path):
        target_path.write_bytes(b"first")
        first_backup = atomic_io.quarantine_file(str(target_path))

        target_path.write_bytes(b"second")
        second_backup = atomic_io.quarantine_file(str(target_path))

        assert first_backup != second_backup
        assert open(first_backup, "rb").read() == b"first"
        assert open(second_backup, "rb").read() == b"second"

    def test_forced_name_collision_retries_instead_of_overwriting(self, target_path):
        target_path.write_bytes(b"my payload")
        real_link = os.link
        call_count = {"n": 0}

        def _flaky_link(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 1:
                with open(dst, "wb") as f:
                    f.write(b"someone else's backup")
                raise FileExistsError(dst)
            return real_link(src, dst)

        with patch("os.link", side_effect=_flaky_link):
            atomic_io.quarantine_file(str(target_path))

        backups = glob.glob(f"{target_path}.corrupted-*")
        assert len(backups) == 2
        contents = {open(b, "rb").read() for b in backups}
        assert contents == {b"someone else's backup", b"my payload"}


class TestAtomicWriteBytes:
    def test_write_then_read_roundtrips(self, target_path):
        atomic_io.atomic_write_bytes(str(target_path), b"payload")

        assert target_path.read_bytes() == b"payload"

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c.bin"

        atomic_io.atomic_write_bytes(str(nested), b"payload")

        assert nested.read_bytes() == b"payload"

    def test_preserves_existing_file_permissions(self, target_path):
        target_path.write_bytes(b"old")
        os.chmod(target_path, 0o640)

        atomic_io.atomic_write_bytes(str(target_path), b"new")

        assert target_path.read_bytes() == b"new"
        assert (os.stat(target_path).st_mode & 0o777) == 0o640

    def test_failure_mid_write_leaves_original_untouched_and_no_temp_litter(
        self, target_path
    ):
        target_path.write_bytes(b"original")

        with patch("os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_io.atomic_write_bytes(str(target_path), b"new")

        assert target_path.read_bytes() == b"original"
        leftovers = [
            f for f in os.listdir(target_path.parent) if f.startswith(".state.bin-")
        ]
        assert leftovers == []


class _FakeMsvcrt:
    LK_NBLCK = 1
    LK_UNLCK = 2

    def locking(self, _fd, _mode, _nbytes):
        return None


class TestPathLock:
    def test_lock_is_reentrant_safe_after_release(self, target_path):
        with atomic_io.path_lock(str(target_path)):
            pass
        # A second, independent acquisition after release must not hang.
        with atomic_io.path_lock(str(target_path)):
            pass

    def test_contended_lock_times_out_instead_of_hanging_forever(self, target_path):
        with atomic_io.path_lock(str(target_path)):
            with pytest.raises(atomic_io.LockTimeout):
                with atomic_io.path_lock(str(target_path), timeout=0.2):
                    pass  # pragma: no cover - should never be reached

    def test_lock_file_created_alongside_target(self, target_path):
        with atomic_io.path_lock(str(target_path)):
            assert os.path.exists(f"{target_path}.lock")

    def test_windows_lock_sidecar_stays_one_byte_even_if_fd_starts_at_end(
        self, target_path, monkeypatch
    ):
        """Guard against sidecar ballooning on Windows-style lock paths."""
        lock_file = f"{target_path}.lock"
        real_open = os.open

        def _open_at_end(path, flags, mode=0o777):
            fd = real_open(path, flags, mode)
            os.lseek(fd, 0, os.SEEK_END)
            return fd

        monkeypatch.setattr(atomic_io, "fcntl", None)
        monkeypatch.setattr(atomic_io, "msvcrt", _FakeMsvcrt())
        monkeypatch.setattr(atomic_io.os, "open", _open_at_end)

        for _ in range(5):
            with atomic_io.path_lock(str(target_path)):
                pass

        assert os.path.getsize(lock_file) == 1

    def test_windows_lock_sidecar_stays_one_byte_without_os_ftruncate(
        self, target_path, monkeypatch
    ):
        lock_file = f"{target_path}.lock"
        real_open = os.open

        def _open_at_end(path, flags, mode=0o777):
            fd = real_open(path, flags, mode)
            os.lseek(fd, 0, os.SEEK_END)
            return fd

        monkeypatch.setattr(atomic_io, "fcntl", None)
        monkeypatch.setattr(atomic_io, "msvcrt", _FakeMsvcrt())
        monkeypatch.setattr(atomic_io.os, "open", _open_at_end)
        monkeypatch.setattr(atomic_io.os, "ftruncate", None, raising=False)

        for _ in range(5):
            with atomic_io.path_lock(str(target_path)):
                pass

        assert os.path.getsize(lock_file) == 1

    def test_windows_contention_does_not_mutate_sidecar_until_lock_acquired(
        self, target_path, monkeypatch
    ):
        lock_file = f"{target_path}.lock"
        with open(lock_file, "wb") as lock:
            lock.write(b"oversized-lock")

        attempts = {"n": 0}

        def _contended_then_acquired(_fd):
            attempts["n"] += 1
            if attempts["n"] == 1:
                # Simulate another process owning the byte lock: first attempt
                # must observe the untouched oversized sidecar.
                assert os.path.getsize(lock_file) == len(b"oversized-lock")
                return False
            return True

        monkeypatch.setattr(atomic_io, "fcntl", None)
        monkeypatch.setattr(atomic_io, "msvcrt", _FakeMsvcrt())
        monkeypatch.setattr(atomic_io, "_try_lock", _contended_then_acquired)

        with atomic_io.path_lock(str(target_path), timeout=0.5):
            assert os.path.getsize(lock_file) == 1

        assert attempts["n"] >= 2

    def test_windows_prime_swallows_write_error_on_empty_sidecar(
        self, target_path, monkeypatch
    ):
        lock_file = f"{target_path}.lock"
        open(lock_file, "wb").close()

        real_write = os.write
        write_calls = {"n": 0}

        def _flaky_write(fd, data):
            write_calls["n"] += 1
            if write_calls["n"] == 1:
                raise OSError("simulated share violation")
            return real_write(fd, data)

        monkeypatch.setattr(atomic_io, "fcntl", None)
        monkeypatch.setattr(atomic_io, "msvcrt", _FakeMsvcrt())
        monkeypatch.setattr(atomic_io.os, "write", _flaky_write)

        with atomic_io.path_lock(str(target_path), timeout=0.5):
            pass

        assert write_calls["n"] >= 1


class TestConcurrentWritersDoNotLoseUpdates:
    def test_eight_threads_racing_a_lock_protected_counter_dont_lose_increments(
        self, target_path
    ):
        target_path.write_bytes(b"0")

        def _increment():
            with atomic_io.path_lock(str(target_path)):
                current = int(target_path.read_bytes())
                # Give a competing thread a real chance to interleave if the
                # lock weren't actually exclusive.
                time.sleep(0.001)
                atomic_io.atomic_write_bytes(
                    str(target_path), str(current + 1).encode()
                )

        import threading

        threads = [threading.Thread(target=_increment) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert int(target_path.read_bytes()) == 8
