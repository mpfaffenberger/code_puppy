"""Tests for the plugin_list plugin (/plugins slash command)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from code_puppy.plugins.plugin_list.register_callbacks import (
    _build_output,
    _custom_help,
    _format_plugin_list,
    _handle_custom_command,
)

# Patch targets live on the source module because _build_output() uses
# lazy imports: ``from code_puppy.plugins import …``.
_PLUGINS_MOD = "code_puppy.plugins"
_PLUGINS_CONFIG_MOD = "code_puppy.plugins.config"


# ── Unit tests for helpers ────────────────────────────────────────────────


class TestFormatPluginList:
    def test_empty_list(self):
        assert _format_plugin_list([], set()) == "  (none)"

    def test_single_plugin(self):
        result = _format_plugin_list(["shell_safety"], set())
        assert "shell_safety" in result

    def test_multiple_sorted(self):
        result = _format_plugin_list(["zebra", "alpha", "mid"], set())
        lines = result.split("\n")
        assert len(lines) == 3
        assert "alpha" in lines[0]
        assert "mid" in lines[1]
        assert "zebra" in lines[2]

    def test_disabled_shown(self):
        result = _format_plugin_list(["alpha", "beta"], {"beta"})
        lines = result.split("\n")
        assert "(disabled)" not in lines[0]  # alpha
        assert "(disabled)" in lines[1]  # beta


class TestBuildOutput:
    def test_all_tiers_populated(self):
        loaded = {
            "builtin": ["shell_safety", "agent_skills"],
            "user": ["my_tool"],
            "project": ["repo_guard"],
        }
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=Path("/tmp/proj/.code_puppy/plugins"),
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            assert "Loaded Plugins" in output
            assert "Builtin (" in output
            assert "agent_skills" in output
            assert "shell_safety" in output
            assert "User (~/.code_puppy/plugins/):" in output
            assert "my_tool" in output
            assert "Project (/tmp/proj/.code_puppy/plugins/):" in output
            assert "repo_guard" in output

    def test_empty_tiers_show_none(self):
        loaded = {"builtin": ["one"], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            lines = output.split("\n")
            user_idx = next(
                i for i, line in enumerate(lines) if line.startswith("User")
            )
            project_idx = next(
                i for i, line in enumerate(lines) if line.startswith("Project")
            )
            assert lines[user_idx + 1].strip() == "(none)"
            assert lines[project_idx + 1].strip() == "(none)"

    def test_project_path_placeholder_when_no_dir(self):
        loaded = {"builtin": [], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            assert "<CWD>/.code_puppy/plugins/" in output


# ── Slash command tests ───────────────────────────────────────────────────


class TestHandleCustomCommand:
    def test_unrelated_command_returns_none(self):
        assert _handle_custom_command("/foo", "foo") is None
        assert _handle_custom_command("/help", "help") is None

    def test_bare_plugins_launches_tui(self):
        with patch(
            "code_puppy.plugins.plugin_list.plugins_menu.run_plugins_menu",
        ) as mock_menu:
            result = _handle_custom_command("/plugins", "plugins")
            assert result is True
            mock_menu.assert_called_once()

    def test_plugins_list_returns_text(self):
        loaded = {"builtin": ["a"], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
            patch(
                "code_puppy.messaging.emit_info",
            ) as mock_emit,
        ):
            result = _handle_custom_command("/plugins list", "plugins")
            assert result is True
            mock_emit.assert_called_once()
            assert "Loaded Plugins" in mock_emit.call_args[0][0]


class TestCustomHelp:
    def test_returns_plugins_entry(self):
        entries = _custom_help()
        assert len(entries) == 1
        cmd, desc = entries[0]
        assert cmd == "plugins"
        assert "plugin" in desc.lower()
