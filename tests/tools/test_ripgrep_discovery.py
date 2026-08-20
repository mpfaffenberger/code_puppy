"""Regression tests for ripgrep discovery under environment managers."""

import subprocess

from code_puppy.tools import file_operations


def test_find_ripgrep_prefers_active_python_environment(monkeypatch):
    """A broken pyenv PATH shim must not hide the environment's executable."""
    environment_rg = "/active-environment/bin/rg"
    monkeypatch.setattr(
        file_operations.sys, "executable", "/active-environment/bin/python"
    )
    monkeypatch.setattr(
        file_operations.os.path,
        "isfile",
        lambda path: path == environment_rg,
    )
    monkeypatch.setattr(
        file_operations.shutil,
        "which",
        lambda _name: "/pyenv/shims/rg",
    )

    assert file_operations._find_ripgrep() == environment_rg


def test_recursive_listing_bypasses_broken_path_shim(monkeypatch, tmp_path):
    environment_bin = tmp_path / "environment" / "bin"
    environment_bin.mkdir(parents=True)
    environment_python = environment_bin / "python"
    environment_rg = environment_bin / "rg"
    environment_rg.touch()
    listed_file = tmp_path / "listed.txt"
    listed_file.write_text("hello")

    monkeypatch.setattr(file_operations.sys, "executable", str(environment_python))
    monkeypatch.setattr(
        file_operations.shutil, "which", lambda _name: "/pyenv/shims/rg"
    )

    def run(command, **_kwargs):
        assert command[0] == str(environment_rg)
        return subprocess.CompletedProcess(command, 0, f"{listed_file}\n", "")

    monkeypatch.setattr(file_operations.subprocess, "run", run)

    result = file_operations._list_files(None, str(tmp_path), recursive=True)

    assert result.error is None
    assert "listed.txt" in result.content


def test_find_ripgrep_falls_back_to_path(monkeypatch):
    monkeypatch.setattr(file_operations.os.path, "isfile", lambda _path: False)
    monkeypatch.setattr(
        file_operations.shutil, "which", lambda _name: "/usr/local/bin/rg"
    )

    assert file_operations._find_ripgrep() == "/usr/local/bin/rg"
