"""Comprehensive tests for code_puppy/plugins/__init__.py.

Tests cover plugin loading functions including:
- Built-in plugin loading with various edge cases
- User plugin loading from ~/.code_puppy/plugins/
- Error handling paths
- Idempotent loading behavior
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import code_puppy.plugins as plugins_module
from code_puppy.plugins import (
    USER_PLUGINS_DIR,
    _load_builtin_plugins,
    _load_user_plugins,
    ensure_user_plugins_dir,
    get_user_plugins_dir,
    load_plugin_callbacks,
)


class TestGetUserPluginsDir:
    """Test get_user_plugins_dir function."""

    def test_returns_user_plugins_path(self):
        """Test that function returns the USER_PLUGINS_DIR constant."""
        result = get_user_plugins_dir()
        assert result == USER_PLUGINS_DIR
        assert result == Path.home() / ".code_puppy" / "plugins"


class TestEnsureUserPluginsDir:
    """Test ensure_user_plugins_dir function."""

    def test_creates_directory_if_not_exists(self, tmp_path):
        """Test that directory is created if it doesn't exist."""
        test_dir = tmp_path / ".code_puppy" / "plugins"
        assert not test_dir.exists()

        with patch.object(plugins_module, "USER_PLUGINS_DIR", test_dir):
            result = ensure_user_plugins_dir()
            assert result == test_dir
            assert test_dir.exists()
            assert test_dir.is_dir()

    def test_returns_existing_directory(self, tmp_path):
        """Test that existing directory is returned without error."""
        test_dir = tmp_path / ".code_puppy" / "plugins"
        test_dir.mkdir(parents=True)
        assert test_dir.exists()

        with patch.object(plugins_module, "USER_PLUGINS_DIR", test_dir):
            result = ensure_user_plugins_dir()
            assert result == test_dir
            assert test_dir.exists()


class TestLoadBuiltinPlugins:
    """Test _load_builtin_plugins function."""

    def test_loads_valid_plugin(self, tmp_path):
        """Test loading a valid built-in plugin."""
        # Create a plugin directory with register_callbacks.py
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()
        callbacks_file = plugin_dir / "register_callbacks.py"
        callbacks_file.write_text("# Plugin callbacks")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "my_plugin" in result
            mock_import.assert_called_once_with(
                "code_puppy.plugins.my_plugin.register_callbacks"
            )

    def test_skips_directories_starting_with_underscore(self, tmp_path):
        """Test that directories starting with _ are skipped."""
        # Create a _private plugin directory
        private_dir = tmp_path / "_private"
        private_dir.mkdir()
        (private_dir / "register_callbacks.py").write_text("# Private")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert result == []
            mock_import.assert_not_called()

    def test_skips_files_not_directories(self, tmp_path):
        """Test that regular files are skipped."""
        # Create a file instead of directory
        (tmp_path / "some_file.py").write_text("# Just a file")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert result == []
            mock_import.assert_not_called()

    def test_skips_directories_without_register_callbacks(self, tmp_path):
        """Test that directories without register_callbacks.py are skipped."""
        # Create a plugin directory without register_callbacks.py
        plugin_dir = tmp_path / "incomplete_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# Just init")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert result == []
            mock_import.assert_not_called()

    def test_skips_shell_safety_when_safety_level_high(self, tmp_path):
        """Test shell_safety plugin is skipped when safety_permission_level is high."""
        # Create shell_safety plugin directory
        plugin_dir = tmp_path / "shell_safety"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Shell safety")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "shell_safety" not in result
            mock_import.assert_not_called()

    def test_skips_shell_safety_when_safety_level_medium(self, tmp_path):
        """Test shell_safety plugin is skipped when safety_permission_level is medium."""
        plugin_dir = tmp_path / "shell_safety"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Shell safety")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="medium"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "shell_safety" not in result
            mock_import.assert_not_called()

    def test_loads_shell_safety_when_safety_level_low(self, tmp_path):
        """Test shell_safety plugin is loaded when safety_permission_level is low."""
        plugin_dir = tmp_path / "shell_safety"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Shell safety")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="low"
            ),
            patch("code_puppy.plugins.importlib.import_module") as mock_import,
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "shell_safety" in result
            mock_import.assert_called_once_with(
                "code_puppy.plugins.shell_safety.register_callbacks"
            )

    def test_loads_shell_safety_when_safety_level_none(self, tmp_path):
        """Test shell_safety plugin is loaded when safety_permission_level is none."""
        plugin_dir = tmp_path / "shell_safety"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Shell safety")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="none"
            ),
            patch("code_puppy.plugins.importlib.import_module"),
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "shell_safety" in result

    def test_handles_import_error(self, tmp_path, caplog):
        """Test graceful handling of ImportError during plugin loading."""
        plugin_dir = tmp_path / "broken_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Broken")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch(
                "code_puppy.plugins.importlib.import_module",
                side_effect=ImportError("Module not found"),
            ),
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "broken_plugin" not in result
            assert "Failed to import callbacks from built-in plugin" in caplog.text

    def test_handles_generic_exception(self, tmp_path, caplog):
        """Test graceful handling of unexpected exceptions during plugin loading."""
        plugin_dir = tmp_path / "exploding_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Exploding")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch(
                "code_puppy.plugins.importlib.import_module",
                side_effect=RuntimeError("Something went wrong"),
            ),
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "exploding_plugin" not in result
            assert "Unexpected error loading built-in plugin" in caplog.text

    def test_loads_multiple_plugins(self, tmp_path):
        """Test loading multiple plugins."""
        # Create multiple plugin directories
        for name in ["plugin_a", "plugin_b", "plugin_c"]:
            plugin_dir = tmp_path / name
            plugin_dir.mkdir()
            (plugin_dir / "register_callbacks.py").write_text(f"# {name}")

        with (
            patch(
                "code_puppy.config.get_safety_permission_level", return_value="high"
            ),
            patch("code_puppy.plugins.importlib.import_module"),
        ):
            result = _load_builtin_plugins(tmp_path)
            assert len(result) == 3
            assert set(result) == {"plugin_a", "plugin_b", "plugin_c"}


class TestLoadUserPlugins:
    """Test _load_user_plugins function."""

    def test_returns_empty_for_nonexistent_directory(self, tmp_path):
        """Test that non-existent directory returns empty list."""
        nonexistent = tmp_path / "does_not_exist"
        result = _load_user_plugins(nonexistent)
        assert result == []

    def test_warns_if_path_is_file_not_directory(self, tmp_path, caplog):
        """Test that warning is logged if path is a file, not directory."""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("I'm a file")

        result = _load_user_plugins(file_path)
        assert result == []
        assert "User plugins path is not a directory" in caplog.text

    def test_adds_user_plugins_dir_to_sys_path(self, tmp_path):
        """Test that user plugins directory is added to sys.path."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()
        user_plugins_str = str(user_plugins_dir)

        # Ensure it's not already in sys.path
        if user_plugins_str in sys.path:
            sys.path.remove(user_plugins_str)

        try:
            _load_user_plugins(user_plugins_dir)
            assert user_plugins_str in sys.path
        finally:
            # Clean up
            if user_plugins_str in sys.path:
                sys.path.remove(user_plugins_str)

    def test_does_not_duplicate_sys_path_entry(self, tmp_path):
        """Test that sys.path entry is not duplicated on multiple calls."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()
        user_plugins_str = str(user_plugins_dir)

        # Add it to sys.path first
        if user_plugins_str not in sys.path:
            sys.path.insert(0, user_plugins_str)

        original_count = sys.path.count(user_plugins_str)

        try:
            _load_user_plugins(user_plugins_dir)
            assert sys.path.count(user_plugins_str) == original_count
        finally:
            # Clean up
            while user_plugins_str in sys.path:
                sys.path.remove(user_plugins_str)

    def test_skips_directories_starting_with_underscore(self, tmp_path):
        """Test that directories starting with _ are skipped."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        private_dir = user_plugins_dir / "_private"
        private_dir.mkdir()
        (private_dir / "register_callbacks.py").write_text("# Private")

        try:
            result = _load_user_plugins(user_plugins_dir)
            assert result == []
        finally:
            if str(user_plugins_dir) in sys.path:
                sys.path.remove(str(user_plugins_dir))

    def test_skips_directories_starting_with_dot(self, tmp_path):
        """Test that directories starting with . are skipped."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        hidden_dir = user_plugins_dir / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "register_callbacks.py").write_text("# Hidden")

        try:
            result = _load_user_plugins(user_plugins_dir)
            assert result == []
        finally:
            if str(user_plugins_dir) in sys.path:
                sys.path.remove(str(user_plugins_dir))

    def test_skips_files_not_directories(self, tmp_path):
        """Test that regular files are skipped."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()
        (user_plugins_dir / "some_file.py").write_text("# Just a file")

        try:
            result = _load_user_plugins(user_plugins_dir)
            assert result == []
        finally:
            if str(user_plugins_dir) in sys.path:
                sys.path.remove(str(user_plugins_dir))

    def test_loads_plugin_with_register_callbacks(self, tmp_path):
        """Test loading a user plugin with register_callbacks.py."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "my_user_plugin"
        plugin_dir.mkdir()
        callbacks_file = plugin_dir / "register_callbacks.py"
        callbacks_file.write_text("# User plugin callbacks")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_module = MagicMock()

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=mock_module,
            ),
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "my_user_plugin" in result
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_spec_is_none(self, tmp_path, caplog):
        """Test handling when spec_from_file_location returns None."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "bad_spec_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Bad spec")

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=None,
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "bad_spec_plugin" not in result
                assert "Could not create module spec" in caplog.text
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_spec_loader_is_none(self, tmp_path, caplog):
        """Test handling when spec.loader is None."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "no_loader_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# No loader")

        mock_spec = MagicMock()
        mock_spec.loader = None

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=mock_spec,
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "no_loader_plugin" not in result
                assert "Could not create module spec" in caplog.text
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_import_error_for_register_callbacks(self, tmp_path, caplog):
        """Test graceful handling of ImportError during user plugin loading."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "import_error_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Import error")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_spec.loader.exec_module.side_effect = ImportError("Missing dependency")

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "import_error_plugin" not in result
                assert "Failed to import callbacks from user plugin" in caplog.text
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_generic_exception_for_register_callbacks(self, tmp_path, caplog):
        """Test graceful handling of unexpected exceptions during user plugin loading."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "exploding_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# Exploding")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_spec.loader.exec_module.side_effect = RuntimeError("Boom!")

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "exploding_plugin" not in result
                assert "Unexpected error loading user plugin" in caplog.text
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_loads_plugin_with_init_fallback(self, tmp_path):
        """Test loading a user plugin that only has __init__.py (no register_callbacks)."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "simple_plugin"
        plugin_dir.mkdir()
        # Only __init__.py, no register_callbacks.py
        init_file = plugin_dir / "__init__.py"
        init_file.write_text("# Simple plugin")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_module = MagicMock()

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=mock_module,
            ),
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "simple_plugin" in result
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_spec_is_none_for_init_fallback(self, tmp_path):
        """Test handling when spec is None for __init__.py fallback."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "bad_init_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# Bad init")

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=None,
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "bad_init_plugin" not in result
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_spec_loader_is_none_for_init_fallback(self, tmp_path):
        """Test handling when spec.loader is None for __init__.py fallback."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "no_loader_init_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# No loader")

        mock_spec = MagicMock()
        mock_spec.loader = None

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=mock_spec,
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "no_loader_init_plugin" not in result
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_handles_exception_for_init_fallback(self, tmp_path, caplog):
        """Test graceful handling of exception during __init__.py fallback loading."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        plugin_dir = user_plugins_dir / "exploding_init_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# Exploding init")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_spec.loader.exec_module.side_effect = RuntimeError("Init boom!")

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            try:
                result = _load_user_plugins(user_plugins_dir)
                assert "exploding_init_plugin" not in result
                assert "Unexpected error loading user plugin" in caplog.text
            finally:
                if str(user_plugins_dir) in sys.path:
                    sys.path.remove(str(user_plugins_dir))

    def test_skips_directory_without_callbacks_or_init(self, tmp_path):
        """Test that directories without register_callbacks.py or __init__.py are skipped."""
        user_plugins_dir = tmp_path / "user_plugins"
        user_plugins_dir.mkdir()

        # Empty plugin directory
        plugin_dir = user_plugins_dir / "empty_plugin"
        plugin_dir.mkdir()

        try:
            result = _load_user_plugins(user_plugins_dir)
            assert result == []
        finally:
            if str(user_plugins_dir) in sys.path:
                sys.path.remove(str(user_plugins_dir))


class TestLoadPluginCallbacks:
    """Test load_plugin_callbacks function."""

    def test_idempotent_loading(self):
        """Test that plugins are only loaded once (idempotent)."""
        # Reset the global flag for this test
        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = True

        try:
            result = load_plugin_callbacks()
            # Should return empty since plugins are "already loaded"
            assert result == {"builtin": [], "user": []}
        finally:
            plugins_module._PLUGINS_LOADED = original_loaded

    def test_calls_load_functions(self, tmp_path):
        """Test that load_plugin_callbacks calls both load functions."""
        # Reset the global flag
        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = False

        with (
            patch(
                "code_puppy.plugins._load_builtin_plugins",
                return_value=["builtin_plugin"],
            ) as mock_builtin,
            patch(
                "code_puppy.plugins._load_user_plugins", return_value=["user_plugin"]
            ) as mock_user,
        ):
            try:
                result = load_plugin_callbacks()

                assert result["builtin"] == ["builtin_plugin"]
                assert result["user"] == ["user_plugin"]
                mock_builtin.assert_called_once()
                mock_user.assert_called_once()
                # Check that the flag was set
                assert plugins_module._PLUGINS_LOADED is True
            finally:
                plugins_module._PLUGINS_LOADED = original_loaded

    def test_sets_plugins_loaded_flag(self):
        """Test that _PLUGINS_LOADED flag is set after loading."""
        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = False

        with (
            patch("code_puppy.plugins._load_builtin_plugins", return_value=[]),
            patch("code_puppy.plugins._load_user_plugins", return_value=[]),
        ):
            try:
                load_plugin_callbacks()
                assert plugins_module._PLUGINS_LOADED is True
            finally:
                plugins_module._PLUGINS_LOADED = original_loaded

    def test_logs_loaded_plugins(self, caplog):
        """Test that loaded plugins are logged."""
        import logging

        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = False

        with (
            patch(
                "code_puppy.plugins._load_builtin_plugins",
                return_value=["test_builtin"],
            ),
            patch(
                "code_puppy.plugins._load_user_plugins", return_value=["test_user"]
            ),
            caplog.at_level(logging.DEBUG),
        ):
            try:
                load_plugin_callbacks()
                assert "Loaded plugins" in caplog.text
            finally:
                plugins_module._PLUGINS_LOADED = original_loaded

    def test_skips_loading_when_already_loaded_logs_debug(self, caplog):
        """Test that skipping duplicate load is logged."""
        import logging

        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = True

        with caplog.at_level(logging.DEBUG):
            try:
                load_plugin_callbacks()
                assert "Plugins already loaded" in caplog.text
            finally:
                plugins_module._PLUGINS_LOADED = original_loaded
