"""find_ripgrep: the single ripgrep locator shared by every rg consumer."""

from __future__ import annotations

import os
import sys

import pytest

from code_puppy.tools import ripgrep


@pytest.fixture
def interpreter_dir(tmp_path, monkeypatch):
    """Pretend the interpreter lives in tmp_path, with nothing on PATH."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(ripgrep.shutil, "which", lambda name: None)
    return tmp_path


def test_prefers_path(interpreter_dir, monkeypatch):
    (interpreter_dir / "rg").touch()
    monkeypatch.setattr(ripgrep.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(ripgrep, "_executable_works", lambda path: True)
    assert ripgrep.find_ripgrep() == "/usr/bin/rg"


def test_falls_back_when_path_rg_is_broken(interpreter_dir, monkeypatch):
    """Regression: a PATH entry that exists but won't run (a broken pyenv
    shim, say) must not shadow a working bundled copy."""
    (interpreter_dir / "rg").touch()
    monkeypatch.setattr(ripgrep.shutil, "which", lambda name: "/broken/pyenv/shim/rg")
    monkeypatch.setattr(ripgrep, "_executable_works", lambda path: False)
    assert ripgrep.find_ripgrep() == os.path.join(str(interpreter_dir), "rg")


def test_broken_path_rg_is_last_resort_when_nothing_bundled(
    interpreter_dir, monkeypatch
):
    """No working rg anywhere: better to hand back the broken PATH entry
    (callers already surface rg invocation failures) than None."""
    monkeypatch.setattr(ripgrep.shutil, "which", lambda name: "/broken/pyenv/shim/rg")
    monkeypatch.setattr(ripgrep, "_executable_works", lambda path: False)
    assert ripgrep.find_ripgrep() == "/broken/pyenv/shim/rg"


@pytest.mark.parametrize("name", ["rg", "rg.exe"])
def test_falls_back_to_binary_beside_interpreter(interpreter_dir, name):
    (interpreter_dir / name).touch()
    assert ripgrep.find_ripgrep() == os.path.join(str(interpreter_dir), name)


def test_none_when_missing_everywhere(interpreter_dir):
    assert ripgrep.find_ripgrep() is None


def test_executable_works_true_for_a_real_runnable_binary():
    assert ripgrep._executable_works(sys.executable) is True


def test_executable_works_false_for_a_missing_path():
    assert ripgrep._executable_works("/definitely/not/a/real/path/rg") is False


def test_file_completion_index_finds_bundled_ripgrep(interpreter_dir, monkeypatch):
    """Regression: the @-completion index used to check PATH only, so it never
    saw the rg bundled with Code Puppy that grep/list_files already used."""
    from code_puppy import file_completion_io
    from code_puppy.command_line import file_index

    (interpreter_dir / "rg").touch()
    seen = {}

    def fake_read_paths(rg, root, limit, timeout):
        seen["rg"] = rg
        return ["a.py"]

    monkeypatch.setattr(file_completion_io, "read_paths", fake_read_paths)
    assert file_index._run_ripgrep(str(interpreter_dir)) == ["a.py"]
    assert seen["rg"] == os.path.join(str(interpreter_dir), "rg")
