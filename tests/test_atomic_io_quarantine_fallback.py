"""Regression coverage for quarantine on platforms without ``os.link``.

Android/Termux (bionic) does not expose ``os.link``, so the hard-link-based
``atomic_io.quarantine_file`` raised ``AttributeError`` instead of quarantining
a corrupt config -- breaking corruption resilience on the daily-driver
platform. These tests pin the platform-compatible fallback while proving the
original quarantine contract (no-overwrite, no-data-loss) is preserved exactly.

Every test forces ``os.link`` absent/unsupported with ``monkeypatch`` so the
guarantees are verified identically on POSIX CI and on Termux.
"""

import errno
import glob
import os

import pytest

from code_puppy import atomic_io


def _corrupt(tmp_path, name="puppy.cfg", data=b"\x96\x97 not [ini at all"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p), data


def test_fallback_used_when_oslink_absent_preserves_content_and_name(
    tmp_path, monkeypatch
):
    """Without os.link: corrupt file is quarantined under the expected name,
    its bytes survive verbatim, and the original location is vacated."""
    monkeypatch.delattr(os, "link", raising=False)  # simulate Android/Termux
    src, data = _corrupt(tmp_path)

    quarantine_path = atomic_io.quarantine_file(src)

    assert quarantine_path.startswith(src + ".corrupted-")  # expected name
    assert os.path.exists(quarantine_path)
    with open(quarantine_path, "rb") as fh:
        assert fh.read() == data  # no-data-loss: bytes preserved verbatim
    assert not os.path.exists(src)  # original location reaches post-quarantine state
    assert glob.glob(f"{src}.corrupted-*") == [quarantine_path]


def test_fallback_never_overwrites_existing_destination(tmp_path, monkeypatch):
    """Under the copy fallback, an existing quarantine destination is never
    clobbered; when every candidate name is taken, we raise rather than
    overwrite, and the original is preserved (no-data-loss)."""
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path)

    # Force every retry onto one fixed name that already holds a prior backup.
    class _Hex:
        hex = "fixed"

    monkeypatch.setattr(atomic_io.time, "time_ns", lambda: 7)
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: _Hex())
    prior = f"{src}.corrupted-7-fixed"
    with open(prior, "wb") as fh:
        fh.write(b"PRIOR-BACKUP")

    with pytest.raises(FileExistsError):
        atomic_io.quarantine_file(src)

    with open(prior, "rb") as fh:
        assert fh.read() == b"PRIOR-BACKUP"  # never overwritten
    assert os.path.exists(src)  # original preserved on exhaustion
    with open(src, "rb") as fh:
        assert fh.read() == data


def test_fallback_partial_failure_does_not_lose_original(tmp_path, monkeypatch):
    """If the backup is created but removing the original fails, roll the
    backup back and re-raise -- the original must never be silently lost."""
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path)

    real_unlink = os.unlink

    def _unlink(target):
        if os.path.abspath(target) == os.path.abspath(src):
            raise OSError(errno.EIO, "simulated removal failure")
        return real_unlink(target)

    monkeypatch.setattr(os, "unlink", _unlink)

    with pytest.raises(OSError):
        atomic_io.quarantine_file(src)

    assert os.path.exists(src)  # original preserved
    with open(src, "rb") as fh:
        assert fh.read() == data
    assert glob.glob(f"{src}.corrupted-*") == []  # rolled-back backup, no orphan


def test_unsupported_errno_falls_back_to_copy(tmp_path, monkeypatch):
    """When os.link EXISTS but the filesystem rejects it (e.g. ENOSYS/EXDEV),
    fall back to the copy path instead of surfacing the error."""
    src, data = _corrupt(tmp_path)

    def _link_enosys(_src, _dst):
        raise OSError(errno.ENOSYS, "hard links not supported here")

    monkeypatch.setattr(os, "link", _link_enosys, raising=False)

    quarantine_path = atomic_io.quarantine_file(src)

    assert os.path.exists(quarantine_path)
    with open(quarantine_path, "rb") as fh:
        assert fh.read() == data
    assert not os.path.exists(src)


def test_hardlink_is_preferred_when_available(tmp_path, monkeypatch):
    """Where os.link works, it is used and the copy fallback is NOT taken."""
    src, data = _corrupt(tmp_path)
    used = {"link": False, "copy": False}
    real_open = os.open

    def _fake_link(source, dest):
        used["link"] = True
        # stand in for a real hard link on a platform that lacks one
        fd = real_open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with open(source, "rb") as sf:
                os.write(fd, sf.read())
        finally:
            os.close(fd)

    def _guard_copy(_src, _dst):
        used["copy"] = True
        raise AssertionError("copy fallback must not run when os.link works")

    monkeypatch.setattr(os, "link", _fake_link, raising=False)
    monkeypatch.setattr(atomic_io, "_create_quarantine_copy", _guard_copy)

    quarantine_path = atomic_io.quarantine_file(src)

    assert used["link"] is True
    assert used["copy"] is False
    assert os.path.exists(quarantine_path)
    with open(quarantine_path, "rb") as fh:
        assert fh.read() == data
    assert not os.path.exists(src)


# --- adversarial fallback hardening -----------------------------------------


def test_copy_loops_until_full_buffer_written(tmp_path, monkeypatch):
    """A single os.write() may accept only part of the buffer; the copy must
    loop until every byte lands, so short writes never truncate the backup."""
    monkeypatch.delattr(os, "link", raising=False)
    payload = bytes((i * 7) % 256 for i in range(5000))
    src, _ = _corrupt(tmp_path, data=payload)

    real_write = os.write

    def short_write(fd, data):  # accept only 1 byte per call
        return real_write(fd, bytes(data[:1]))

    monkeypatch.setattr(os, "write", short_write)
    quarantine_path = atomic_io.quarantine_file(src)
    monkeypatch.undo()

    with open(quarantine_path, "rb") as fh:
        assert fh.read() == payload  # full content despite 1-byte writes
    assert not os.path.exists(src)


def _assert_source_intact_no_partial(src, data):
    assert os.path.exists(src)
    with open(src, "rb") as fh:
        assert fh.read() == data
    assert glob.glob(f"{src}.corrupted-*") == []  # partial dest removed


def test_read_failure_leaves_source_and_removes_partial_dest(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path, data=b"x" * 256)

    def boom_read(_fd, _n):
        raise OSError(errno.EIO, "injected read failure")

    monkeypatch.setattr(os, "read", boom_read)
    with pytest.raises(OSError):
        atomic_io.quarantine_file(src)
    monkeypatch.undo()
    _assert_source_intact_no_partial(src, data)


def test_write_failure_leaves_source_and_removes_partial_dest(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path, data=b"y" * 256)

    def boom_write(_fd, _data):
        raise OSError(errno.ENOSPC, "injected write failure")

    monkeypatch.setattr(os, "write", boom_write)
    with pytest.raises(OSError):
        atomic_io.quarantine_file(src)
    monkeypatch.undo()
    _assert_source_intact_no_partial(src, data)


def test_fsync_failure_leaves_source_and_removes_partial_dest(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path, data=b"z" * 256)

    def boom_fsync(_fd):
        raise OSError(errno.EIO, "injected fsync failure")

    monkeypatch.setattr(os, "fsync", boom_fsync)
    with pytest.raises(OSError):
        atomic_io.quarantine_file(src)
    monkeypatch.undo()
    _assert_source_intact_no_partial(src, data)


def test_destination_close_failure_removes_partial_and_preserves_source(
    tmp_path, monkeypatch
):
    monkeypatch.delattr(os, "link", raising=False)
    src, data = _corrupt(tmp_path, data=b"w" * 256)

    real_close = os.close
    calls = {"n": 0}

    def flaky_close(fd):
        calls["n"] += 1
        if calls["n"] == 2:  # src_fd closes first (#1); this is the dst_fd close
            raise OSError(errno.EIO, "injected close failure")
        return real_close(fd)

    monkeypatch.setattr(os, "close", flaky_close)
    with pytest.raises(OSError):
        atomic_io.quarantine_file(src)
    monkeypatch.undo()
    _assert_source_intact_no_partial(src, data)


def test_eacces_on_link_is_surfaced_not_bypassed(tmp_path, monkeypatch):
    """EACCES (permission denied) is a real restriction, not 'unsupported'.
    It must propagate -- never silently fall back to a copy that could
    circumvent a filesystem permission policy."""
    src, data = _corrupt(tmp_path, data=b"secret")

    def denied_link(_src, _dst):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(os, "link", denied_link, raising=False)
    with pytest.raises(OSError) as excinfo:
        atomic_io.quarantine_file(src)
    assert excinfo.value.errno == errno.EACCES
    _assert_source_intact_no_partial(src, data)  # no copy fallback happened


def test_symlink_source_copies_target_and_preserves_it(tmp_path, monkeypatch):
    """Quarantining a symlinked config removes the symlink and backs up the
    target's bytes, leaving the target file itself intact (no data loss)."""
    monkeypatch.delattr(os, "link", raising=False)
    target = tmp_path / "real.cfg"
    target.write_bytes(b"target payload")
    link = str(tmp_path / "puppy.cfg")
    os.symlink(str(target), link)

    quarantine_path = atomic_io.quarantine_file(link)

    with open(quarantine_path, "rb") as fh:
        assert fh.read() == b"target payload"
    assert not os.path.lexists(link)  # the symlink itself is gone
    assert target.exists()  # target untouched
    with open(target, "rb") as fh:
        assert fh.read() == b"target payload"
