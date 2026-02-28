"""Tests for hook engine command executor."""

import pytest

from code_puppy.hook_engine.executor import (
    _substitute_variables,
    execute_hook,
    execute_hooks_sequential,
    get_blocking_result,
)
from code_puppy.hook_engine.models import EventData, ExecutionResult, HookConfig


@pytest.mark.asyncio
class TestExecuteHook:
    async def test_successful_command(self):
        hook = HookConfig(
            matcher="*", type="command", command="echo 'test'", timeout=1000
        )
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event_data)
        assert result.success is True
        assert result.blocked is False
        assert result.exit_code == 0
        assert "test" in result.stdout

    async def test_failed_command(self):
        hook = HookConfig(matcher="*", type="command", command="exit 1", timeout=1000)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event_data)
        assert result.success is False
        assert result.blocked is True
        assert result.exit_code == 1

    async def test_command_timeout(self):
        hook = HookConfig(matcher="*", type="command", command="sleep 10", timeout=100)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event_data)
        assert result.blocked is True
        assert "timed out" in result.error.lower()

    async def test_prompt_hook(self):
        hook = HookConfig(matcher="*", type="prompt", command="This is a prompt")
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event_data)
        assert result.success is True
        assert result.blocked is False
        assert result.stdout == "This is a prompt"

    async def test_exit_code_2_not_blocked(self):
        """Exit code 2 = feedback to Claude, not a block."""
        hook = HookConfig(matcher="*", type="command", command="exit 2", timeout=1000)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event_data)
        assert result.blocked is False
        assert result.exit_code == 2

    async def test_stdin_payload_sent(self):
        """Verify hook receives JSON on stdin."""
        hook = HookConfig(
            matcher="*",
            type="command",
            command="python3 -c \"import sys,json; d=json.load(sys.stdin); print(d['tool_name'])\"",
            timeout=5000,
        )
        event_data = EventData(event_type="PreToolUse", tool_name="TestTool")
        result = await execute_hook(hook, event_data)
        assert result.exit_code == 0
        assert "TestTool" in result.stdout

    async def test_env_var_available(self):
        """Verify CLAUDE_TOOL_NAME env var is set."""
        hook = HookConfig(
            matcher="*",
            type="command",
            command="echo $CLAUDE_TOOL_NAME",
            timeout=1000,
        )
        event_data = EventData(event_type="PreToolUse", tool_name="MyTool")
        result = await execute_hook(hook, event_data)
        assert "MyTool" in result.stdout


class TestSubstituteVariables:
    def test_claude_project_dir(self):
        import os

        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = _substitute_variables("${CLAUDE_PROJECT_DIR}/hook.sh", event_data, {})
        assert os.getcwd() in result

    def test_tool_name(self):
        event_data = EventData(event_type="PreToolUse", tool_name="MyTool")
        result = _substitute_variables("echo ${tool_name}", event_data, {})
        assert "MyTool" in result

    def test_file_variable(self):
        event_data = EventData(
            event_type="PreToolUse",
            tool_name="Edit",
            tool_args={"file_path": "test.py"},
        )
        result = _substitute_variables("black ${file}", event_data, {})
        assert "test.py" in result

    def test_custom_env_var(self):
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = _substitute_variables("${MY_VAR}", event_data, {"MY_VAR": "hello"})
        assert "hello" in result


@pytest.mark.asyncio
class TestExecuteHooksSequential:
    async def test_stops_on_block(self):
        hooks = [
            HookConfig(matcher="*", type="command", command="exit 1", timeout=1000),
            HookConfig(
                matcher="*", type="command", command="echo second", timeout=1000
            ),
        ]
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        results = await execute_hooks_sequential(hooks, event_data, stop_on_block=True)
        # Should stop after first block
        assert len(results) == 1
        assert results[0].blocked is True

    async def test_continues_past_non_block(self):
        hooks = [
            HookConfig(matcher="*", type="command", command="echo first", timeout=1000),
            HookConfig(
                matcher="*", type="command", command="echo second", timeout=1000
            ),
        ]
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        results = await execute_hooks_sequential(hooks, event_data)
        assert len(results) == 2


class TestGetBlockingResult:
    def test_finds_first_blocking(self):
        results = [
            ExecutionResult(blocked=False, hook_command="cmd1", exit_code=0),
            ExecutionResult(
                blocked=True, hook_command="cmd2", exit_code=1, error="blocked"
            ),
        ]
        blocking = get_blocking_result(results)
        assert blocking is not None
        assert blocking.hook_command == "cmd2"

    def test_returns_none_when_no_block(self):
        results = [
            ExecutionResult(blocked=False, hook_command="cmd1", exit_code=0),
            ExecutionResult(blocked=False, hook_command="cmd2", exit_code=0),
        ]
        assert get_blocking_result(results) is None
