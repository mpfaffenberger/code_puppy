"""Tests for hook engine models."""

import pytest

from code_puppy.hook_engine.models import (
    EventData,
    ExecutionResult,
    HookConfig,
    HookRegistry,
    ProcessEventResult,
)


class TestHookConfig:
    def test_valid_command_hook(self):
        hook = HookConfig(matcher="*", type="command", command="echo test")
        assert hook.matcher == "*"
        assert hook.type == "command"
        assert hook.command == "echo test"
        assert hook.timeout == 5000
        assert hook.enabled is True
        assert hook.id is not None

    def test_valid_prompt_hook(self):
        hook = HookConfig(matcher="Edit", type="prompt", command="validate this")
        assert hook.type == "prompt"

    def test_empty_matcher_raises(self):
        with pytest.raises(ValueError, match="matcher"):
            HookConfig(matcher="", type="command", command="echo test")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="type"):
            HookConfig(matcher="*", type="invalid", command="echo test")

    def test_empty_command_raises(self):
        with pytest.raises(ValueError, match="command"):
            HookConfig(matcher="*", type="command", command="")

    def test_timeout_too_low_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            HookConfig(matcher="*", type="command", command="echo test", timeout=50)

    def test_auto_generated_id(self):
        hook1 = HookConfig(matcher="*", type="command", command="echo test")
        hook2 = HookConfig(matcher="*", type="command", command="echo test")
        assert hook1.id == hook2.id

    def test_custom_id(self):
        hook = HookConfig(
            matcher="*", type="command", command="echo test", id="custom-id"
        )
        assert hook.id == "custom-id"

    def test_different_commands_different_ids(self):
        hook1 = HookConfig(matcher="*", type="command", command="echo test1")
        hook2 = HookConfig(matcher="*", type="command", command="echo test2")
        assert hook1.id != hook2.id


class TestEventData:
    def test_valid_event(self):
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        assert event.event_type == "PreToolUse"
        assert event.tool_name == "Edit"
        assert event.tool_args == {}
        assert event.context == {}

    def test_empty_event_type_raises(self):
        with pytest.raises(ValueError, match="Event type"):
            EventData(event_type="", tool_name="Edit")

    def test_empty_tool_name_raises(self):
        with pytest.raises(ValueError, match="Tool name"):
            EventData(event_type="PreToolUse", tool_name="")

    def test_with_tool_args(self):
        event = EventData(
            event_type="PreToolUse",
            tool_name="Edit",
            tool_args={"file_path": "test.py"},
        )
        assert event.tool_args == {"file_path": "test.py"}


class TestExecutionResult:
    def test_successful_result(self):
        result = ExecutionResult(
            blocked=False, hook_command="echo test", stdout="test\n", exit_code=0
        )
        assert result.success is True
        assert result.blocked is False

    def test_blocked_result(self):
        result = ExecutionResult(
            blocked=True,
            hook_command="exit 1",
            stderr="blocked",
            exit_code=1,
            error="blocked",
        )
        assert result.success is False
        assert result.blocked is True

    def test_output_property(self):
        result = ExecutionResult(
            blocked=False, hook_command="cmd", stdout="out", stderr="err"
        )
        assert "out" in result.output
        assert "err" in result.output


class TestHookRegistry:
    def test_add_and_get_hooks(self):
        registry = HookRegistry()
        hook = HookConfig(matcher="*", type="command", command="echo test")
        registry.add_hook("PreToolUse", hook)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 1
        assert hooks[0] == hook

    def test_unknown_event_type(self):
        registry = HookRegistry()
        hooks = registry.get_hooks_for_event("UnknownEvent")
        assert hooks == []

    def test_disabled_hook_filtered(self):
        registry = HookRegistry()
        hook = HookConfig(
            matcher="*", type="command", command="echo test", enabled=False
        )
        registry.add_hook("PreToolUse", hook)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 0

    def test_once_hook_runs_only_once(self):
        registry = HookRegistry()
        hook = HookConfig(matcher="*", type="command", command="echo test", once=True)
        registry.add_hook("PreToolUse", hook)

        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 1

        registry.mark_hook_executed(hook.id)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 0

    def test_reset_once_hooks(self):
        registry = HookRegistry()
        hook = HookConfig(matcher="*", type="command", command="echo test", once=True)
        registry.add_hook("PreToolUse", hook)
        registry.mark_hook_executed(hook.id)
        registry.reset_once_hooks()
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 1

    def test_count_hooks(self):
        registry = HookRegistry()
        registry.add_hook(
            "PreToolUse", HookConfig(matcher="*", type="command", command="echo 1")
        )
        registry.add_hook(
            "PreToolUse", HookConfig(matcher="*", type="command", command="echo 2")
        )
        registry.add_hook(
            "PostToolUse", HookConfig(matcher="*", type="command", command="echo 3")
        )
        assert registry.count_hooks() == 3
        assert registry.count_hooks("PreToolUse") == 2
        assert registry.count_hooks("PostToolUse") == 1

    def test_remove_hook(self):
        registry = HookRegistry()
        hook = HookConfig(matcher="*", type="command", command="echo test")
        registry.add_hook("PreToolUse", hook)
        removed = registry.remove_hook("PreToolUse", hook.id)
        assert removed is True
        assert len(registry.get_hooks_for_event("PreToolUse")) == 0

    def test_remove_nonexistent_hook(self):
        registry = HookRegistry()
        removed = registry.remove_hook("PreToolUse", "nonexistent")
        assert removed is False

    def test_normalize_event_type(self):
        assert HookRegistry._normalize_event_type("PreToolUse") == "pre_tool_use"
        assert HookRegistry._normalize_event_type("PostToolUse") == "post_tool_use"
        assert HookRegistry._normalize_event_type("SessionStart") == "session_start"


class TestProcessEventResult:
    def test_all_successful(self):
        results = [
            ExecutionResult(blocked=False, hook_command="cmd1", exit_code=0),
            ExecutionResult(blocked=False, hook_command="cmd2", exit_code=0),
        ]
        event_result = ProcessEventResult(
            blocked=False, executed_hooks=2, results=results
        )
        assert event_result.all_successful is True

    def test_not_all_successful(self):
        results = [
            ExecutionResult(blocked=False, hook_command="cmd1", exit_code=0),
            ExecutionResult(
                blocked=True, hook_command="cmd2", exit_code=1, error="fail"
            ),
        ]
        event_result = ProcessEventResult(
            blocked=True, executed_hooks=2, results=results
        )
        assert event_result.all_successful is False
        assert len(event_result.failed_hooks) == 1
