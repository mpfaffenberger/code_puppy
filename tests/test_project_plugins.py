"""Tests for project-level plugin discovery (_load_project_plugins).

Covers the feature implemented in code_puppy_oss-864:
- Project plugin loading from <CWD>/.code_puppy/plugins/
- Name collision warnings (builtin and user shadows)
- Error handling (ImportError, RuntimeError)
- get_project_plugins_directory() helper
- Skipping dotfiles/underscore dirs
- __init__.py fallback when no register_callbacks.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins import (
    _load_project_plugins,
    get_project_plugins_directory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin(plugins_dir: Path, name: str, *, via_init: bool = False) -> Path:
    """Create a minimal plugin directory with register_callbacks.py or __init__.py."""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(parents=True)
    target = "__init__.py" if via_init else "register_callbacks.py"
    (plugin_dir / target).write_text(f"# {name} plugin\n")
    return plugin_dir


@pytest.fixture()
def project_plugins_dir(tmp_path: Path) -> Path:
    """Provide a fresh project plugins directory."""
    d = tmp_path / ".code_puppy" / "plugins"
    d.mkdir(parents=True)
    return d


@pytest.fixture(autouse=True)
def _cleanup_sys_path():
    """Remove any tmp_path entries from sys.path after each test."""
    before = list(sys.path)
    yield
    # Restore to pre-test state
    for entry in sys.path[:]:
        if entry not in before:
            sys.path.remove(entry)


# ---------------------------------------------------------------------------
# 1. Project dir does not exist → no plugins loaded, no errors
# ---------------------------------------------------------------------------


class TestProjectDirMissing:
    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        nonexistent = tmp_path / "nope"
        result = _load_project_plugins(nonexistent, set(), set())
        assert result == []

    def test_nonexistent_dir_no_errors(self, tmp_path: Path, caplog):
        nonexistent = tmp_path / "nope"
        _load_project_plugins(nonexistent, set(), set())
        assert "error" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# 2. Valid plugin with register_callbacks.py → loaded successfully
# ---------------------------------------------------------------------------


class TestValidPlugin:
    def test_loads_register_callbacks(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "good_plugin")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

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
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "good_plugin" in result

    def test_uses_project_plugins_namespace(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "ns_plugin")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ) as mock_sfl,
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            _load_project_plugins(project_plugins_dir, set(), set())

        # Should use the project_plugins.{name} namespace to avoid sys.modules clash
        call_args = mock_sfl.call_args
        assert call_args[0][0] == "project_plugins.ns_plugin.register_callbacks"


# ---------------------------------------------------------------------------
# 3. Name collision with builtin → warning logged, both load
# ---------------------------------------------------------------------------


class TestBuiltinCollision:
    def test_warns_on_builtin_shadow(self, project_plugins_dir: Path, caplog):
        _make_plugin(project_plugins_dir, "shell_safety")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

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
            result = _load_project_plugins(
                project_plugins_dir, builtin_names={"shell_safety"}, user_names=set()
            )

        assert "shell_safety" in result
        assert "shadows builtin plugin" in caplog.text


# ---------------------------------------------------------------------------
# 4. Name collision with user plugin → warning logged, both load
# ---------------------------------------------------------------------------


class TestUserCollision:
    def test_user_plugin_skipped_when_project_overrides(
        self, project_plugins_dir: Path, caplog
    ):
        """When a project plugin has the same name as a user plugin,
        the user plugin is skipped (dedup) and _load_project_plugins
        does NOT see it in user_names at all."""
        _make_plugin(project_plugins_dir, "my_tool")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

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
            # user_names is empty because _load_user_plugins already
            # skipped the colliding plugin via the pre-scan dedup.
            result = _load_project_plugins(
                project_plugins_dir, builtin_names=set(), user_names=set()
            )

        assert "my_tool" in result
        # No shadow warning — dedup happens at the user tier, not here.
        assert "shadows user plugin" not in caplog.text


# ---------------------------------------------------------------------------
# 5. Broken plugin → error caught, other plugins still load
# ---------------------------------------------------------------------------


class TestBrokenPlugin:
    def test_import_error_caught(self, project_plugins_dir: Path, caplog):
        _make_plugin(project_plugins_dir, "bad_import")
        _make_plugin(project_plugins_dir, "healthy")

        mock_spec_bad = MagicMock()
        mock_spec_bad.loader = MagicMock()
        mock_spec_bad.loader.exec_module.side_effect = ImportError("no such module")

        mock_spec_ok = MagicMock()
        mock_spec_ok.loader = MagicMock()

        call_count = 0

        def spec_side_effect(_name, _path):
            nonlocal call_count
            call_count += 1
            # Return bad spec for first call, good for second
            if "bad_import" in str(_path):
                return mock_spec_bad
            return mock_spec_ok

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                side_effect=spec_side_effect,
            ),
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "bad_import" not in result
        assert "healthy" in result
        assert "Failed to import callbacks from project plugin" in caplog.text

    def test_runtime_error_caught(self, project_plugins_dir: Path, caplog):
        _make_plugin(project_plugins_dir, "exploder")

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_spec.loader.exec_module.side_effect = RuntimeError("boom")

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
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "exploder" not in result
        assert "Unexpected error loading project plugin" in caplog.text


# ---------------------------------------------------------------------------
# 6. get_project_plugins_directory() returns None when dir missing
# ---------------------------------------------------------------------------


class TestGetProjectPluginsDirectory:
    def test_returns_none_when_missing(self, tmp_path: Path):
        with patch("code_puppy.plugins.Path.cwd", return_value=tmp_path):
            assert get_project_plugins_directory() is None

    # -----------------------------------------------------------------------
    # 7. returns Path when dir exists
    # -----------------------------------------------------------------------

    def test_returns_path_when_exists(self, tmp_path: Path):
        plugins_dir = tmp_path / ".code_puppy" / "plugins"
        plugins_dir.mkdir(parents=True)

        with patch("code_puppy.plugins.Path.cwd", return_value=tmp_path):
            result = get_project_plugins_directory()
            assert result is not None
            assert result == plugins_dir


# ---------------------------------------------------------------------------
# 8. load_plugin_callbacks() includes "project" key in result dict
# ---------------------------------------------------------------------------


class TestLoadPluginCallbacksProjectKey:
    def test_result_dict_has_project_key(self):
        import code_puppy.plugins as plugins_module

        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = False

        with (
            patch("code_puppy.plugins._load_builtin_plugins", return_value=["bp"]),
            patch("code_puppy.plugins._load_user_plugins", return_value=["up"]),
            patch(
                "code_puppy.plugins.get_project_plugins_directory",
                return_value=None,
            ),
        ):
            try:
                result = plugins_module.load_plugin_callbacks()
                assert "project" in result
                assert result["project"] == []
            finally:
                plugins_module._PLUGINS_LOADED = original_loaded

    def test_idempotent_returns_project_key(self):
        import code_puppy.plugins as plugins_module

        original_loaded = plugins_module._PLUGINS_LOADED
        plugins_module._PLUGINS_LOADED = True

        try:
            result = plugins_module.load_plugin_callbacks()
            assert "project" in result
            assert result == {"builtin": [], "user": [], "project": []}
        finally:
            plugins_module._PLUGINS_LOADED = original_loaded


# ---------------------------------------------------------------------------
# 9. Skips dirs starting with _ or .
# ---------------------------------------------------------------------------


class TestSkipSpecialDirs:
    def test_skips_underscore_dirs(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "_private")

        result = _load_project_plugins(project_plugins_dir, set(), set())
        assert result == []

    def test_skips_dot_dirs(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, ".hidden")

        result = _load_project_plugins(project_plugins_dir, set(), set())
        assert result == []

    def test_skips_files_not_directories(self, project_plugins_dir: Path):
        (project_plugins_dir / "not_a_plugin.py").write_text("# nope")

        result = _load_project_plugins(project_plugins_dir, set(), set())
        assert result == []


# ---------------------------------------------------------------------------
# 10. Falls back to __init__.py when no register_callbacks.py
# ---------------------------------------------------------------------------


class TestInitFallback:
    def test_loads_via_init_fallback(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "init_only", via_init=True)

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

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
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "init_only" in result

    def test_init_fallback_uses_project_namespace(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "init_ns", via_init=True)

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()

        with (
            patch(
                "code_puppy.plugins.importlib.util.spec_from_file_location",
                return_value=mock_spec,
            ) as mock_sfl,
            patch(
                "code_puppy.plugins.importlib.util.module_from_spec",
                return_value=MagicMock(),
            ),
        ):
            _load_project_plugins(project_plugins_dir, set(), set())

        call_args = mock_sfl.call_args
        assert call_args[0][0] == "project_plugins.init_ns"

    def test_init_fallback_error_caught(self, project_plugins_dir: Path, caplog):
        _make_plugin(project_plugins_dir, "broken_init", via_init=True)

        mock_spec = MagicMock()
        mock_spec.loader = MagicMock()
        mock_spec.loader.exec_module.side_effect = RuntimeError("init boom")

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
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "broken_init" not in result
        assert "Unexpected error loading project plugin" in caplog.text

    def test_init_fallback_spec_none_skips(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "no_spec_init", via_init=True)

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=None,
        ):
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "no_spec_init" not in result

    def test_init_fallback_loader_none_skips(self, project_plugins_dir: Path):
        _make_plugin(project_plugins_dir, "no_loader_init", via_init=True)

        mock_spec = MagicMock()
        mock_spec.loader = None

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=mock_spec,
        ):
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "no_loader_init" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_path_is_file_not_dir(self, tmp_path: Path, caplog):
        fake_dir = tmp_path / "plugins_file"
        fake_dir.write_text("oops")

        result = _load_project_plugins(fake_dir, set(), set())
        assert result == []
        assert "not a directory" in caplog.text

    def test_spec_none_skips_register_callbacks(
        self, project_plugins_dir: Path, caplog
    ):
        _make_plugin(project_plugins_dir, "no_spec")

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=None,
        ):
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "no_spec" not in result
        assert "Could not create module spec for project plugin" in caplog.text

    def test_spec_loader_none_skips(self, project_plugins_dir: Path, caplog):
        _make_plugin(project_plugins_dir, "no_loader")

        mock_spec = MagicMock()
        mock_spec.loader = None

        with patch(
            "code_puppy.plugins.importlib.util.spec_from_file_location",
            return_value=mock_spec,
        ):
            result = _load_project_plugins(project_plugins_dir, set(), set())

        assert "no_loader" not in result
        assert "Could not create module spec for project plugin" in caplog.text

    def test_dir_without_callbacks_or_init_skipped(self, project_plugins_dir: Path):
        empty = project_plugins_dir / "empty_plugin"
        empty.mkdir()

        result = _load_project_plugins(project_plugins_dir, set(), set())
        assert result == []

    def test_adds_project_dir_to_sys_path(self, project_plugins_dir: Path):
        project_str = str(project_plugins_dir)
        if project_str in sys.path:
            sys.path.remove(project_str)

        _load_project_plugins(project_plugins_dir, set(), set())
        assert project_str in sys.path

    def test_no_duplicate_sys_path_entries(self, project_plugins_dir: Path):
        project_str = str(project_plugins_dir)
        if project_str not in sys.path:
            sys.path.insert(0, project_str)

        count_before = sys.path.count(project_str)
        _load_project_plugins(project_plugins_dir, set(), set())
        assert sys.path.count(project_str) == count_before
