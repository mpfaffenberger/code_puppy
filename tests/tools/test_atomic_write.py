"""Tests for code_puppy.tools.common.atomic_write_text + the wired call sites."""

import os
import stat

import pytest

from code_puppy.tools.common import atomic_write_text


def _tmp_orphans(directory: str) -> list[str]:
    """Return any leftover *.tmp files in a directory."""
    return [name for name in os.listdir(directory) if name.endswith(".tmp")]


def test_creates_new_file(tmp_path):
    p = tmp_path / "new.txt"
    atomic_write_text(str(p), "hello puppy")
    assert p.read_text(encoding="utf-8") == "hello puppy"


def test_overwrites_existing_file(tmp_path):
    p = tmp_path / "existing.txt"
    p.write_text("old content", encoding="utf-8")
    atomic_write_text(str(p), "brand new content")
    assert p.read_text(encoding="utf-8") == "brand new content"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits not on Windows")
def test_mode_preservation(tmp_path):
    p = tmp_path / "script.sh"
    p.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    os.chmod(p, 0o755)
    atomic_write_text(str(p), "#!/bin/sh\necho bye\n")
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o755
    assert p.read_text(encoding="utf-8") == "#!/bin/sh\necho bye\n"


def test_no_orphan_temp_on_success(tmp_path):
    p = tmp_path / "target.txt"
    atomic_write_text(str(p), "content one")
    atomic_write_text(str(p), "content two")
    assert _tmp_orphans(str(tmp_path)) == []


def test_cleanup_and_original_intact_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "precious.txt"
    p.write_text("DO NOT LOSE ME", encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(str(p), "new content that should never land")

    # Original untouched...
    assert p.read_text(encoding="utf-8") == "DO NOT LOSE ME"
    # ...and no orphan temp left behind.
    assert _tmp_orphans(str(tmp_path)) == []


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_symlink_preserved(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("original", encoding="utf-8")
    link = tmp_path / "link.txt"
    os.symlink(str(real), str(link))

    atomic_write_text(str(link), "updated through symlink")

    # The link is still a link...
    assert os.path.islink(str(link))
    # ...and the real file received the new content.
    assert real.read_text(encoding="utf-8") == "updated through symlink"


def test_unicode_round_trip(tmp_path):
    p = tmp_path / "unicode.txt"
    payload = "puppy  woof ünïcödé 日本語"
    atomic_write_text(str(p), payload)
    assert p.read_text(encoding="utf-8") == payload


def test_creates_nested_directories(tmp_path):
    p = tmp_path / "deeply" / "nested" / "path" / "file.txt"
    atomic_write_text(str(p), "nested content")
    assert p.read_text(encoding="utf-8") == "nested content"


def test_write_to_file_returns_error_dict_on_atomic_failure(tmp_path, monkeypatch):
    """The user-facing wrapper must surface failures as an error dict.

    The agent relies on _write_to_file returning {"error": ...} rather than
    propagating exceptions, so a failing atomic_write_text must not crash it.
    """
    import code_puppy.tools.file_modifications as fmod

    def boom(*args, **kwargs):
        raise OSError("simulated atomic write failure")

    monkeypatch.setattr(fmod, "write_project_file", boom)

    p = tmp_path / "out.txt"
    result = fmod._write_to_file(None, str(p), "some content", overwrite=True)

    assert not result.get("success")
    assert "error" in result
    assert "simulated atomic write failure" in result["error"]


def test_replace_in_file_leaves_no_tmp_orphan(tmp_path):
    """Regression: the wired _replace_in_file site must not leak *.tmp."""
    from code_puppy.tools.file_modifications import _replace_in_file

    p = tmp_path / "code.py"
    p.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = _replace_in_file(
        None,
        str(p),
        [{"old_str": "beta", "new_str": "BETA"}],
    )

    assert result.get("success") is True
    assert p.read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    assert _tmp_orphans(str(tmp_path)) == []
