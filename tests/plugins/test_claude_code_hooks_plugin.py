"""
IMMUTABLE TEST FILE — DO NOT MODIFY.

Tests for code_puppy/plugins/claude_code_hooks/
  - config.py: load_hooks_config, get_hooks_config_paths
  - register_callbacks.py: on_pre_tool_call_hook, on_post_tool_call_hook
    callbacks wired correctly into the pre_tool_call / post_tool_call phases.

Implementation targets:
  code_puppy/plugins/claude_code_hooks/config.py
  code_puppy/plugins/claude_code_hooks/register_callbacks.py
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# config.py: get_hooks_config_paths
# ---------------------------------------------------------------------------


class TestGetHooksConfigPaths:
    def test_returns_list(self):
        from code_puppy.plugins.claude_code_hooks.config import get_hooks_config_paths

        paths = get_hooks_config_paths()
        assert isinstance(paths, list)

    def test_returns_two_paths(self):
        from code_puppy.plugins.claude_code_hooks.config import get_hooks_config_paths

        paths = get_hooks_config_paths()
        assert len(paths) == 2

    def test_project_path_contains_claude_settings(self):
        from code_puppy.plugins.claude_code_hooks.config import get_hooks_config_paths

        paths = get_hooks_config_paths()
        # First path must include .claude/settings.json
        assert ".claude" in paths[0] and "settings.json" in paths[0]

    def test_global_path_contains_code_puppy(self):
        from code_puppy.plugins.claude_code_hooks.config import get_hooks_config_paths

        paths = get_hooks_config_paths()
        # Second path is user-level (~/.code_puppy/hooks.json)
        assert ".code_puppy" in paths[1] and "hooks.json" in paths[1]


# ---------------------------------------------------------------------------
# config.py: load_hooks_config — no config files present
# ---------------------------------------------------------------------------


class TestLoadHooksConfigNoFiles:
    def test_returns_none_when_no_config_files(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    os.path.join(tmpdir, "nonexistent_hooks.json"),
                ):
                    result = load_hooks_config()
                    assert result is None


# ---------------------------------------------------------------------------
# config.py: load_hooks_config — project-level settings.json
# ---------------------------------------------------------------------------


class TestLoadHooksConfigProjectLevel:
    def test_loads_hooks_from_project_settings(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        hooks_data = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo project_hook"}],
                }
            ]
        }
        settings = {"hooks": hooks_data}

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps(settings))

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    os.path.join(tmpdir, "nonexistent.json"),
                ):
                    result = load_hooks_config()
                    assert result is not None
                    assert "PreToolUse" in result

    def test_returns_none_when_settings_has_no_hooks_key(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        settings = {"other_key": "value"}  # no 'hooks' section

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps(settings))

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    os.path.join(tmpdir, "nonexistent.json"),
                ):
                    result = load_hooks_config()
                    assert result is None

    def test_handles_invalid_json_in_project_settings(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text("{invalid json!!!")

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    os.path.join(tmpdir, "nonexistent.json"),
                ):
                    result = load_hooks_config()
                    assert result is None  # should handle gracefully, not crash


# ---------------------------------------------------------------------------
# config.py: load_hooks_config — global level hooks.json
# ---------------------------------------------------------------------------


class TestLoadHooksConfigGlobalLevel:
    def test_loads_from_global_hooks_file(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        hooks_data = {
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "echo global_hook"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            global_hooks = os.path.join(tmpdir, "hooks.json")
            with open(global_hooks, "w") as f:
                json.dump(hooks_data, f)

            # No project-level config
            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_hooks,
                ):
                    result = load_hooks_config()
                    assert result is not None
                    assert "PostToolUse" in result

    def test_handles_invalid_global_json(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        with tempfile.TemporaryDirectory() as tmpdir:
            global_hooks = os.path.join(tmpdir, "hooks.json")
            with open(global_hooks, "w") as f:
                f.write("{bad json")

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_hooks,
                ):
                    result = load_hooks_config()
                    assert result is None  # should not crash

    def test_project_level_merges_with_global(self):
        """When both exist, both hooks are merged with global executing first."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo project"}],
                }
            ]
        }
        global_hooks_data = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo global"}],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo post_global"}],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    # Both hooks should be present, merged together
                    assert "PreToolUse" in result
                    assert "PostToolUse" in result
                    # PreToolUse should have both global and project hooks (global first, project second)
                    assert len(result["PreToolUse"]) == 2
                    assert (
                        result["PreToolUse"][0]["hooks"][0]["command"] == "echo global"
                    )
                    assert (
                        result["PreToolUse"][1]["hooks"][0]["command"] == "echo project"
                    )
                    # PostToolUse should only have the global hook
                    assert len(result["PostToolUse"]) == 1
                    assert (
                        result["PostToolUse"][0]["hooks"][0]["command"]
                        == "echo post_global"
                    )


# ---------------------------------------------------------------------------
# register_callbacks.py: on_pre_tool_call_hook
# ---------------------------------------------------------------------------


class TestOnPreToolCallHook:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_engine(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = None
        try:
            result = await register_callbacks.on_pre_tool_call_hook(
                "Bash", {"command": "ls"}
            )
            assert result is None
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_returns_none_when_hook_allows(self):
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_result = ProcessEventResult(blocked=False, executed_hooks=1, results=[])
        mock_engine.process_event = AsyncMock(return_value=mock_result)

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            result = await register_callbacks.on_pre_tool_call_hook(
                "Bash", {"command": "ls"}
            )
            assert result is None
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_returns_blocked_dict_when_hook_blocks(self):
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_result = ProcessEventResult(
            blocked=True,
            executed_hooks=1,
            results=[],
            blocking_reason="dangerous command",
        )
        mock_engine.process_event = AsyncMock(return_value=mock_result)

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            result = await register_callbacks.on_pre_tool_call_hook(
                "Bash", {"command": "rm -rf /"}
            )
            assert isinstance(result, dict)
            assert result.get("blocked") is True
            assert "reason" in result or "error_message" in result
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_passes_tool_name_and_args_to_engine(self):
        from code_puppy.hook_engine.models import EventData, ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_result = ProcessEventResult(blocked=False, executed_hooks=0, results=[])
        mock_engine.process_event = AsyncMock(return_value=mock_result)

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_pre_tool_call_hook(
                "agent_run_shell_command", {"command": "git status"}
            )
            # Verify process_event was called with "PreToolUse"
            call_args = mock_engine.process_event.call_args
            assert call_args[0][0] == "PreToolUse"
            event_data = call_args[0][1]
            assert isinstance(event_data, EventData)
            assert event_data.tool_name == "agent_run_shell_command"
            assert event_data.tool_args == {"command": "git status"}
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_handles_engine_exception_gracefully(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            side_effect=RuntimeError("engine exploded")
        )

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            # Should not raise; should return None
            result = await register_callbacks.on_pre_tool_call_hook("Bash", {})
            assert result is None
        finally:
            register_callbacks._hook_engine = original


# ---------------------------------------------------------------------------
# register_callbacks.py: on_post_tool_call_hook
# ---------------------------------------------------------------------------


class TestOnPostToolCallHook:
    @pytest.mark.asyncio
    async def test_does_nothing_when_no_engine(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = None
        try:
            result = await register_callbacks.on_post_tool_call_hook(
                "Edit", {"file_path": "a.py"}, "ok", 42.0
            )
            assert result is None
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_calls_engine_with_post_tool_use(self):
        from code_puppy.hook_engine.models import EventData, ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_result = ProcessEventResult(blocked=False, executed_hooks=0, results=[])
        mock_engine.process_event = AsyncMock(return_value=mock_result)

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_post_tool_call_hook(
                "Edit", {"file_path": "src/main.py"}, "saved", 100.0
            )
            call_args = mock_engine.process_event.call_args
            assert call_args[0][0] == "PostToolUse"
            event_data = call_args[0][1]
            assert isinstance(event_data, EventData)
            assert event_data.tool_name == "Edit"
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_includes_result_and_duration_in_context(self):
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_result = ProcessEventResult(blocked=False, executed_hooks=0, results=[])
        mock_engine.process_event = AsyncMock(return_value=mock_result)

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_post_tool_call_hook(
                "Edit", {}, "my_result", 123.45
            )
            event_data = mock_engine.process_event.call_args[0][1]
            assert event_data.context["result"] == "my_result"
            assert event_data.context["duration_ms"] == 123.45
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_handles_engine_exception_gracefully(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(side_effect=RuntimeError("post exploded"))

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            # Must not raise
            await register_callbacks.on_post_tool_call_hook("Edit", {}, None, 0.0)
        finally:
            register_callbacks._hook_engine = original


# ---------------------------------------------------------------------------
# Callback registration wiring
# ---------------------------------------------------------------------------


class TestCallbackRegistration:
    def test_pre_tool_call_registered(self):
        """The plugin must register on_pre_tool_call_hook under 'pre_tool_call'."""
        from code_puppy.callbacks import _callbacks
        from code_puppy.plugins.claude_code_hooks.register_callbacks import (
            on_pre_tool_call_hook,
        )

        assert on_pre_tool_call_hook in _callbacks.get("pre_tool_call", [])

    def test_post_tool_call_registered(self):
        """The plugin must register on_post_tool_call_hook under 'post_tool_call'."""
        from code_puppy.callbacks import _callbacks
        from code_puppy.plugins.claude_code_hooks.register_callbacks import (
            on_post_tool_call_hook,
        )

        assert on_post_tool_call_hook in _callbacks.get("post_tool_call", [])
