"""Regression tests for duplicate built-in/user plugin loading."""

import sys

from code_puppy.plugins import _load_user_plugins


def test_user_plugin_skipped_when_builtin_name_loaded(tmp_path):
    """A built-in plugin should suppress same-named user plugin loading."""
    user_plugins_dir = tmp_path / "user_plugins"
    user_plugins_dir.mkdir()

    for plugin_name in ["builtin_copy", "unique_user_plugin"]:
        plugin_dir = user_plugins_dir / plugin_name
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# User plugin")

    try:
        loaded = _load_user_plugins(user_plugins_dir, skip_names={"builtin_copy"})
    finally:
        user_plugins_str = str(user_plugins_dir)
        if user_plugins_str in sys.path:
            sys.path.remove(user_plugins_str)

    assert loaded == ["unique_user_plugin"]
