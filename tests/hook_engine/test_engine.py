"""Tests for hook engine main class."""

import pytest

from code_puppy.hook_engine import EventData, HookConfig, HookEngine


class TestHookEngineInit:
    def test_init_without_config(self):
        engine = HookEngine()
        assert engine.is_loaded is True
        assert engine.count_hooks() == 0

    def test_init_with_valid_config(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo test"}]}
            ]
        }
        engine = HookEngine(config)
        assert engine.is_loaded is True
        assert engine.count_hooks() > 0

    def test_init_with_invalid_config_strict(self):
        config = {"InvalidEvent": []}
        with pytest.raises(ValueError):
            HookEngine(config, strict_validation=True)

    def test_init_with_invalid_config_non_strict(self):
        config = {"InvalidEvent": []}
        engine = HookEngine(config, strict_validation=False)
        assert engine.is_loaded is True


@pytest.mark.asyncio
class TestProcessEvent:
    async def test_no_hooks_for_event(self):
        engine = HookEngine()
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await engine.process_event("PreToolUse", event_data)
        assert result.blocked is False
        assert result.executed_hooks == 0

    async def test_matching_hook_executes(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo test", "timeout": 2000}
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 1
        assert result.blocked is False

    async def test_blocking_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "exit 1", "timeout": 2000}
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await engine.process_event("PreToolUse", event_data)
        assert result.blocked is True
        assert result.blocking_reason is not None

    async def test_non_matching_hook_skipped(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "exit 1", "timeout": 2000}
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await engine.process_event("PreToolUse", event_data)
        assert result.blocked is False
        assert result.executed_hooks == 0

    async def test_once_per_session_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo once",
                            "timeout": 2000,
                            "once": True,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")

        result1 = await engine.process_event("PreToolUse", event_data)
        assert result1.executed_hooks == 1

        result2 = await engine.process_event("PreToolUse", event_data)
        assert result2.executed_hooks == 0

    async def test_multiple_hooks_sequential(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo first", "timeout": 2000},
                        {"type": "command", "command": "echo second", "timeout": 2000},
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 2


class TestHookEngineManagement:
    def test_add_hook(self):
        engine = HookEngine()
        hook = HookConfig(matcher="*", type="command", command="echo test")
        engine.add_hook("PreToolUse", hook)
        assert engine.count_hooks("PreToolUse") == 1

    def test_remove_hook(self):
        engine = HookEngine()
        hook = HookConfig(matcher="*", type="command", command="echo test")
        engine.add_hook("PreToolUse", hook)
        removed = engine.remove_hook("PreToolUse", hook.id)
        assert removed is True
        assert engine.count_hooks("PreToolUse") == 0

    def test_get_stats(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo test"}]}
            ]
        }
        engine = HookEngine(config)
        stats = engine.get_stats()
        assert stats["total_hooks"] == 1
        assert stats["enabled_hooks"] == 1
