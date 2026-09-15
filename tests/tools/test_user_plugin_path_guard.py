"""File tools refuse writes under ~/.code_puppy/plugins."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_puppy.tools.file_modifications import (
    _is_user_plugin_tree_path,
    write_to_file,
)


def _fs_is_case_insensitive(path: Path) -> bool:
    probe = path / "CaseGuardProbe"
    probe.mkdir()
    try:
        folded = path / "caseguardprobe"
        return folded.exists() and os.path.samefile(probe, folded)
    finally:
        probe.rmdir()


def test_detects_user_plugin_tree(tmp_path, monkeypatch):
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    monkeypatch.setattr("code_puppy.plugins.USER_PLUGINS_DIR", plugins_root)

    target = plugins_root / "evil" / "register_callbacks.py"
    assert _is_user_plugin_tree_path(str(target)) is True
    assert _is_user_plugin_tree_path(str(tmp_path / "other.py")) is False


def test_write_to_file_refuses_user_plugin_tree(tmp_path, monkeypatch):
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    monkeypatch.setattr("code_puppy.plugins.USER_PLUGINS_DIR", plugins_root)

    target = plugins_root / "evil" / "register_callbacks.py"
    result = write_to_file(MagicMock(), str(target), "print('hi')\n", overwrite=True)

    assert result["success"] is False
    assert result["changed"] is False
    assert "cannot modify" in result["message"]
    assert not target.exists()


def test_write_to_file_allows_project_path(tmp_path, monkeypatch):
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    monkeypatch.setattr("code_puppy.plugins.USER_PLUGINS_DIR", plugins_root)

    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    result = write_to_file(MagicMock(), str(target), "ok\n", overwrite=True)

    assert result.get("success") is True
    assert Path(target).read_text() == "ok\n"


def test_write_to_file_refuses_case_variant_plugin_tree(tmp_path, monkeypatch):
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("filesystem is case-sensitive")

    monkeypatch.setattr("code_puppy.plugins.USER_PLUGINS_DIR", plugins_root)

    mixed_root = plugins_root.parent / (
        "PLUGINS" if plugins_root.name != "PLUGINS" else "plugins"
    )
    target = mixed_root / "evil" / "register_callbacks.py"
    assert _is_user_plugin_tree_path(str(target)) is True

    result = write_to_file(MagicMock(), str(target), "print('hi')\n", overwrite=True)

    assert result["success"] is False
    assert result["changed"] is False
    assert not (plugins_root / "evil" / "register_callbacks.py").exists()
