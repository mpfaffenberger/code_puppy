"""Tests for external plugin registry functionality.

This module tests the external plugin registration, loading, and management
features in code_puppy/plugins/__init__.py.
"""

import json
import sys
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins import (
    EXTERNAL_PLUGINS_REGISTRY,
    REGISTRY_VERSION,
    USER_PLUGINS_DIR,
    ExternalPluginEntry,
    ExternalPluginRegistry,
    _create_empty_registry,
    _load_external_plugins,
    _read_external_registry,
    _write_external_registry,
    get_external_plugins_registry_path,
    get_user_plugins_dir,
    list_external_plugins,
    register_external_plugin,
    unregister_external_plugin,
)


@pytest.fixture
def temp_registry(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary external plugins registry file.

    Patches EXTERNAL_PLUGINS_REGISTRY to point to a temp location.

    Yields:
        Path to the temporary registry file.
    """
    registry_path = tmp_path / "external_plugins.json"

    with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", registry_path):
        yield registry_path


@pytest.fixture
def temp_plugin_dir(tmp_path: Path) -> Path:
    """Create a temporary plugin directory with register_callbacks.py.

    Returns:
        Path to the temporary plugin directory.
    """
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()

    callbacks_file = plugin_dir / "register_callbacks.py"
    callbacks_file.write_text(
        '"""Test plugin callbacks."""\n'
        "# This is a test plugin that does nothing\n"
        "TEST_PLUGIN_LOADED = True\n",
        encoding="utf-8",
    )

    return plugin_dir


class TestExternalPluginRegistry:
    """Tests for external plugin registry CRUD operations."""

    def test_create_empty_registry(self) -> None:
        """Test creating an empty registry returns correct structure."""
        registry = _create_empty_registry()

        assert registry["version"] == REGISTRY_VERSION
        assert registry["plugins"] == []
        assert isinstance(registry["plugins"], list)

    def test_write_and_read_registry(self, temp_registry: Path, tmp_path: Path) -> None:
        """Test writing and reading a registry file."""
        registry: ExternalPluginRegistry = {
            "version": 1,
            "plugins": [
                {
                    "name": "test-plugin",
                    "path": str(tmp_path / "test-plugin"),
                    "enabled": True,
                    "installed_at": "2025-12-17T12:00:00",
                }
            ],
        }

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _write_external_registry(registry)

            assert temp_registry.exists()

            loaded = _read_external_registry()

            assert loaded["version"] == 1
            assert len(loaded["plugins"]) == 1
            assert loaded["plugins"][0]["name"] == "test-plugin"

    def test_read_registry_warns_on_newer_version(
        self, temp_registry: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that reading a newer version registry logs a warning."""
        registry = {"version": 999, "plugins": []}
        temp_registry.parent.mkdir(parents=True, exist_ok=True)
        temp_registry.write_text(json.dumps(registry), encoding="utf-8")

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _read_external_registry()

        assert "newer than supported version" in caplog.text

    def test_read_registry_invalid_json(self, temp_registry: Path) -> None:
        """Test that reading invalid JSON raises JSONDecodeError."""
        temp_registry.parent.mkdir(parents=True, exist_ok=True)
        temp_registry.write_text("not valid json", encoding="utf-8")

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            with pytest.raises(json.JSONDecodeError):
                _read_external_registry()


class TestRegisterExternalPlugin:
    """Tests for register_external_plugin function."""

    def test_register_new_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test registering a new external plugin."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = register_external_plugin(
                name="my-plugin",
                path=temp_plugin_dir,
                description="A test plugin",
                enabled=True,
            )

            assert result is True
            assert temp_registry.exists()

            registry = json.loads(temp_registry.read_text())
            assert len(registry["plugins"]) == 1
            assert registry["plugins"][0]["name"] == "my-plugin"
            assert registry["plugins"][0]["description"] == "A test plugin"
            assert registry["plugins"][0]["enabled"] is True
            assert "installed_at" in registry["plugins"][0]

    def test_register_updates_existing_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that registering an existing plugin updates it."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            # First registration
            register_external_plugin(
                name="my-plugin",
                path=temp_plugin_dir,
                description="Original",
            )

            # Second registration (update)
            register_external_plugin(
                name="my-plugin",
                path=temp_plugin_dir,
                description="Updated",
            )

            registry = json.loads(temp_registry.read_text())

            # Should still have only one entry
            assert len(registry["plugins"]) == 1
            assert registry["plugins"][0]["description"] == "Updated"

    def test_register_nonexistent_path(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that registering a nonexistent path fails."""
        nonexistent = tmp_path / "does-not-exist"

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = register_external_plugin(
                name="bad-plugin",
                path=nonexistent,
            )

            assert result is False

    def test_register_missing_callbacks_file(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that registering a plugin without register_callbacks.py fails."""
        plugin_dir = tmp_path / "no-callbacks"
        plugin_dir.mkdir()

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = register_external_plugin(
                name="bad-plugin",
                path=plugin_dir,
            )

            assert result is False

    def test_register_without_description(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test registering a plugin without a description."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = register_external_plugin(
                name="minimal-plugin",
                path=temp_plugin_dir,
            )

            assert result is True

            registry = json.loads(temp_registry.read_text())
            assert "description" not in registry["plugins"][0]


class TestUnregisterExternalPlugin:
    """Tests for unregister_external_plugin function."""

    def test_unregister_existing_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test unregistering an existing plugin."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin(
                name="to-remove",
                path=temp_plugin_dir,
            )

            result = unregister_external_plugin("to-remove")

            assert result is True

            registry = json.loads(temp_registry.read_text())
            assert len(registry["plugins"]) == 0

    def test_unregister_nonexistent_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test unregistering a plugin that doesn't exist."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            # Create registry with one plugin
            register_external_plugin(
                name="existing",
                path=temp_plugin_dir,
            )

            result = unregister_external_plugin("nonexistent")

            assert result is False

    def test_unregister_no_registry_file(self, temp_registry: Path) -> None:
        """Test unregistering when registry file doesn't exist."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = unregister_external_plugin("any-plugin")

            assert result is False


class TestListExternalPlugins:
    """Tests for list_external_plugins function."""

    def test_list_empty_registry(self, temp_registry: Path) -> None:
        """Test listing plugins when registry is empty."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _write_external_registry(_create_empty_registry())

            plugins = list_external_plugins()

            assert plugins == []

    def test_list_no_registry_file(self, temp_registry: Path) -> None:
        """Test listing plugins when registry doesn't exist."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            plugins = list_external_plugins()

            assert plugins == []

    def test_list_multiple_plugins(self, temp_registry: Path, tmp_path: Path) -> None:
        """Test listing multiple registered plugins."""
        # Create two plugin directories
        for name in ["plugin-a", "plugin-b"]:
            plugin_dir = tmp_path / name
            plugin_dir.mkdir()
            (plugin_dir / "register_callbacks.py").write_text(
                "# Test", encoding="utf-8"
            )

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin("plugin-a", tmp_path / "plugin-a")
            register_external_plugin("plugin-b", tmp_path / "plugin-b")

            plugins = list_external_plugins()

            assert len(plugins) == 2
            names = [p["name"] for p in plugins]
            assert "plugin-a" in names
            assert "plugin-b" in names

    def test_list_handles_invalid_registry(self, temp_registry: Path) -> None:
        """Test that list_external_plugins handles corrupt registry gracefully."""
        temp_registry.parent.mkdir(parents=True, exist_ok=True)
        temp_registry.write_text("invalid json", encoding="utf-8")

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            plugins = list_external_plugins()

            assert plugins == []


class TestLoadExternalPlugins:
    """Tests for _load_external_plugins function."""

    def test_load_no_registry(self, temp_registry: Path) -> None:
        """Test loading when no registry file exists."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            loaded = _load_external_plugins()

            assert loaded == []

    def test_load_enabled_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test loading an enabled plugin."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin(
                name="loadable",
                path=temp_plugin_dir,
                enabled=True,
            )

            loaded = _load_external_plugins()

            assert "loadable" in loaded

    def test_load_skips_disabled_plugin(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that disabled plugins are not loaded."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin(
                name="disabled-plugin",
                path=temp_plugin_dir,
                enabled=False,
            )

            loaded = _load_external_plugins()

            assert "disabled-plugin" not in loaded

    def test_load_skips_nonexistent_path(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that plugins with nonexistent paths are skipped."""
        # Manually create registry with bad path
        registry: ExternalPluginRegistry = {
            "version": 1,
            "plugins": [
                {
                    "name": "ghost-plugin",
                    "path": str(tmp_path / "nonexistent"),
                    "enabled": True,
                }
            ],
        }

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _write_external_registry(registry)

            loaded = _load_external_plugins()

            assert "ghost-plugin" not in loaded

    def test_load_skips_path_not_directory(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that plugins where path is a file are skipped."""
        # Create a file instead of directory
        file_path = tmp_path / "not-a-dir.txt"
        file_path.write_text("I'm a file", encoding="utf-8")

        registry: ExternalPluginRegistry = {
            "version": 1,
            "plugins": [
                {
                    "name": "file-plugin",
                    "path": str(file_path),
                    "enabled": True,
                }
            ],
        }

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _write_external_registry(registry)

            loaded = _load_external_plugins()

            assert "file-plugin" not in loaded

    def test_load_skips_missing_callbacks(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that plugins without register_callbacks.py are skipped."""
        plugin_dir = tmp_path / "no-callbacks"
        plugin_dir.mkdir()

        registry: ExternalPluginRegistry = {
            "version": 1,
            "plugins": [
                {
                    "name": "no-callbacks",
                    "path": str(plugin_dir),
                    "enabled": True,
                }
            ],
        }

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            _write_external_registry(registry)

            loaded = _load_external_plugins()

            assert "no-callbacks" not in loaded

    def test_load_handles_import_error(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that import errors are handled gracefully."""
        plugin_dir = tmp_path / "bad-import"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text(
            "import nonexistent_module_xyz",
            encoding="utf-8",
        )

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin("bad-import", plugin_dir)

            # Should not raise, just skip
            loaded = _load_external_plugins()

            assert "bad-import" not in loaded

    def test_load_handles_syntax_error(
        self, temp_registry: Path, tmp_path: Path
    ) -> None:
        """Test that syntax errors are handled gracefully."""
        plugin_dir = tmp_path / "syntax-error"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text(
            "def broken(:\n",  # Invalid syntax
            encoding="utf-8",
        )

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin("syntax-error", plugin_dir)

            # Should not raise, just skip
            loaded = _load_external_plugins()

            assert "syntax-error" not in loaded

    def test_load_handles_corrupt_registry(self, temp_registry: Path) -> None:
        """Test loading with corrupt registry file."""
        temp_registry.parent.mkdir(parents=True, exist_ok=True)
        temp_registry.write_text("{invalid json", encoding="utf-8")

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            loaded = _load_external_plugins()

            assert loaded == []

    def test_load_adds_plugin_to_sys_path(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that loaded plugins have their directory added to sys.path."""
        plugin_path_str = str(temp_plugin_dir)

        # Ensure it's not in sys.path initially
        if plugin_path_str in sys.path:
            sys.path.remove(plugin_path_str)

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin("path-test", temp_plugin_dir)
            _load_external_plugins()

            assert plugin_path_str in sys.path

        # Cleanup
        if plugin_path_str in sys.path:
            sys.path.remove(plugin_path_str)


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_user_plugins_dir(self) -> None:
        """Test get_user_plugins_dir returns expected path."""
        result = get_user_plugins_dir()

        assert result == USER_PLUGINS_DIR
        assert result == Path.home() / ".code_puppy" / "plugins"

    def test_get_external_plugins_registry_path(self) -> None:
        """Test get_external_plugins_registry_path returns expected path."""
        result = get_external_plugins_registry_path()

        assert result == EXTERNAL_PLUGINS_REGISTRY
        assert result == Path.home() / ".code_puppy" / "external_plugins.json"


class TestTypeDefinitions:
    """Tests for TypedDict definitions."""

    def test_external_plugin_entry_structure(self) -> None:
        """Test ExternalPluginEntry accepts valid data."""
        entry: ExternalPluginEntry = {
            "name": "test",
            "path": "/some/path",
            "enabled": True,
            "installed_at": "2025-12-17T12:00:00",
            "description": "A test plugin",
        }

        assert entry["name"] == "test"
        assert entry["enabled"] is True

    def test_external_plugin_entry_optional_fields(self) -> None:
        """Test ExternalPluginEntry works with minimal required fields."""
        # total=False means all fields are optional for type checking
        entry: ExternalPluginEntry = {
            "name": "minimal",
            "path": "/path",
        }

        assert entry["name"] == "minimal"

    def test_external_plugin_registry_structure(self) -> None:
        """Test ExternalPluginRegistry accepts valid data."""
        registry: ExternalPluginRegistry = {
            "version": 1,
            "plugins": [
                {"name": "test", "path": "/path"},
            ],
        }

        assert registry["version"] == 1
        assert len(registry["plugins"]) == 1


class TestLoadPluginCallbacks:
    """Tests for load_plugin_callbacks function."""

    def test_load_plugin_callbacks_includes_external(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that load_plugin_callbacks includes external plugins."""
        from code_puppy.plugins import load_plugin_callbacks

        with (
            patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry),
            patch("code_puppy.plugins._PLUGINS_LOADED", False),
        ):
            register_external_plugin("test-external", temp_plugin_dir)

            # Mock the builtin and user loaders to isolate external
            with (
                patch("code_puppy.plugins._load_builtin_plugins", return_value=[]),
                patch("code_puppy.plugins._load_user_plugins", return_value=[]),
            ):
                result = load_plugin_callbacks()

                assert "external" in result
                assert "test-external" in result["external"]

    def test_load_plugin_callbacks_idempotent(self) -> None:
        """Test that load_plugin_callbacks only loads once."""
        from code_puppy.plugins import load_plugin_callbacks

        # Set _PLUGINS_LOADED to True to simulate already loaded
        with patch("code_puppy.plugins._PLUGINS_LOADED", True):
            result = load_plugin_callbacks()

            # Should return empty lists since already loaded
            assert result == {"builtin": [], "user": [], "external": []}


class TestEnsureUserPluginsDir:
    """Tests for ensure_user_plugins_dir function."""

    def test_ensure_creates_directory(self, tmp_path: Path) -> None:
        """Test that ensure_user_plugins_dir creates the directory."""
        from code_puppy.plugins import ensure_user_plugins_dir

        test_dir = tmp_path / "plugins"

        with patch("code_puppy.plugins.USER_PLUGINS_DIR", test_dir):
            result = ensure_user_plugins_dir()

            assert result == test_dir
            assert test_dir.exists()
            assert test_dir.is_dir()

    def test_ensure_existing_directory(self, tmp_path: Path) -> None:
        """Test that ensure_user_plugins_dir handles existing directory."""
        from code_puppy.plugins import ensure_user_plugins_dir

        test_dir = tmp_path / "plugins"
        test_dir.mkdir()

        with patch("code_puppy.plugins.USER_PLUGINS_DIR", test_dir):
            result = ensure_user_plugins_dir()

            assert result == test_dir
            assert test_dir.exists()


class TestLoadExternalPluginsEdgeCases:
    """Additional edge case tests for external plugin loading."""

    def test_load_plugin_with_hyphenated_name(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test loading a plugin with hyphens in the name."""
        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            register_external_plugin(
                name="my-awesome-plugin",
                path=temp_plugin_dir,
            )

            loaded = _load_external_plugins()

            # Hyphens should be converted to underscores in module name
            assert "my-awesome-plugin" in loaded

    def test_load_plugin_module_spec_none(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test handling when spec_from_file_location returns None."""
        with (
            patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry),
            patch("importlib.util.spec_from_file_location", return_value=None),
        ):
            register_external_plugin("spec-none", temp_plugin_dir)

            loaded = _load_external_plugins()

            assert "spec-none" not in loaded

    def test_load_plugin_with_none_loader(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test handling when spec has None loader."""
        mock_spec = MagicMock()
        mock_spec.loader = None

        with (
            patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry),
            patch("importlib.util.spec_from_file_location", return_value=mock_spec),
        ):
            register_external_plugin("no-loader", temp_plugin_dir)

            loaded = _load_external_plugins()

            assert "no-loader" not in loaded


class TestRegisterExternalPluginEdgeCases:
    """Additional edge case tests for register_external_plugin."""

    def test_register_handles_write_error(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that register handles write errors gracefully."""
        with (
            patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry),
            patch(
                "code_puppy.plugins._write_external_registry",
                side_effect=OSError("Disk full"),
            ),
        ):
            result = register_external_plugin("error-plugin", temp_plugin_dir)

            assert result is False

    def test_register_resolves_relative_path(
        self, temp_registry: Path, temp_plugin_dir: Path
    ) -> None:
        """Test that register resolves relative paths to absolute."""

        with patch("code_puppy.plugins.EXTERNAL_PLUGINS_REGISTRY", temp_registry):
            result = register_external_plugin(
                name="relative-path",
                path=temp_plugin_dir,  # Using absolute for test reliability
            )

            assert result is True

            registry = json.loads(temp_registry.read_text())
            # Path should be stored as absolute
            stored_path = registry["plugins"][0]["path"]
            assert Path(stored_path).is_absolute()
