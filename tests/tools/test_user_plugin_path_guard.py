"""File tools refuse writes under ~/.code_puppy/plugins."""

from pathlib import Path
from unittest.mock import MagicMock

from code_puppy.tools.file_modifications import (
    _is_user_plugin_tree_path,
    write_to_file,
)


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
