"""
IMMUTABLE TEST FILE — DO NOT MODIFY.

Integration tests for hook_engine covering:
  - Cross-provider alias matching end-to-end (matcher + aliases)
  - executor: execute_hooks_parallel, _build_stdin_payload, _build_environment,
              format_execution_summary, get_failed_results
  - registry: build_registry_from_config, get_registry_stats
  - engine: validate_config_file, reload_config, parallel execution, env_vars,
            stop-on-block=False, once-reset
  - __init__ public API

Implementation targets:
  code_puppy/hook_engine/aliases.py
  code_puppy/hook_engine/matcher.py  (alias integration)
  code_puppy/hook_engine/executor.py
  code_puppy/hook_engine/registry.py
  code_puppy/hook_engine/engine.py
  code_puppy/hook_engine/__init__.py
"""

import json
import os

import pytest

from code_puppy.hook_engine import EventData, HookConfig, HookEngine
from code_puppy.hook_engine.engine import validate_config_file
from code_puppy.hook_engine.executor import (
    _build_environment,
    _build_stdin_payload,
    execute_hooks_parallel,
    format_execution_summary,
    get_failed_results,
)
from code_puppy.hook_engine.matcher import matches
from code_puppy.hook_engine.models import ExecutionResult
from code_puppy.hook_engine.registry import (
    build_registry_from_config,
    get_registry_stats,
)

# ---------------------------------------------------------------------------
# Cross-provider alias matching — the centrepiece of the whole feature
# ---------------------------------------------------------------------------


class TestCrossProviderMatching:
    """
    Verifies that a hook configured with a Claude Code tool name ("Bash") fires
    correctly when code_puppy calls the equivalent internal tool
    ("agent_run_shell_command"), and vice-versa.
    """

    # Bash ↔ agent_run_shell_command
    def test_bash_matches_internal_shell(self):
        assert matches("Bash", "agent_run_shell_command", {}) is True

    def test_internal_shell_matches_bash(self):
        assert matches("agent_run_shell_command", "Bash", {}) is True

    # Glob ↔ list_files
    def test_glob_matches_list_files(self):
        assert matches("Glob", "list_files", {}) is True

    def test_list_files_matches_glob(self):
        assert matches("list_files", "Glob", {}) is True

    # Read ↔ read_file
    def test_read_matches_read_file(self):
        assert matches("Read", "read_file", {}) is True

    def test_read_file_matches_read(self):
        assert matches("read_file", "Read", {}) is True

    # Grep ↔ grep
    def test_grep_provider_matches_internal(self):
        assert matches("Grep", "grep", {}) is True

    def test_grep_internal_matches_provider(self):
        assert matches("grep", "Grep", {}) is True

    # Edit ↔ edit_file
    def test_edit_matches_edit_file(self):
        assert matches("Edit", "edit_file", {}) is True

    def test_edit_file_matches_edit(self):
        assert matches("edit_file", "Edit", {}) is True

    # Write ↔ edit_file  (Write is also mapped to edit_file)
    def test_write_matches_edit_file(self):
        assert matches("Write", "edit_file", {}) is True

    # AskUserQuestion ↔ ask_user_question
    def test_ask_user_question_alias(self):
        assert matches("AskUserQuestion", "ask_user_question", {}) is True
        assert matches("ask_user_question", "AskUserQuestion", {}) is True

    # Task ↔ invoke_agent
    def test_task_invoke_agent_alias(self):
        assert matches("Task", "invoke_agent", {}) is True
        assert matches("invoke_agent", "Task", {}) is True

    # Skill ↔ activate_skill
    def test_skill_activate_skill_alias(self):
        assert matches("Skill", "activate_skill", {}) is True
        assert matches("activate_skill", "Skill", {}) is True

    # ToolSearch ↔ list_or_search_skills
    def test_toolsearch_alias(self):
        assert matches("ToolSearch", "list_or_search_skills", {}) is True
        assert matches("list_or_search_skills", "ToolSearch", {}) is True

    # Case-insensitive alias matching
    def test_bash_lowercase_matches_internal(self):
        assert matches("bash", "agent_run_shell_command", {}) is True

    def test_bash_uppercase_matches_internal(self):
        assert matches("BASH", "agent_run_shell_command", {}) is True

    # Non-aliases should NOT cross-match
    def test_bash_does_not_match_edit(self):
        assert matches("Bash", "edit_file", {}) is False

    def test_glob_does_not_match_read_file(self):
        assert matches("Glob", "read_file", {}) is False


class TestAliasMatchingInEngine:
    """End-to-end: hook configured with Claude name fires on internal tool name."""

    @pytest.mark.asyncio
    async def test_hook_configured_with_bash_fires_on_internal_tool(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo alias_fired",
                            "timeout": 2000,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(
            event_type="PreToolUse",
            tool_name="agent_run_shell_command",
            tool_args={"command": "ls"},
        )
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 1
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_hook_configured_with_internal_name_fires_on_bash(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "agent_run_shell_command",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo alias_fired",
                            "timeout": 2000,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(
            event_type="PreToolUse",
            tool_name="Bash",
            tool_args={"command": "ls"},
        )
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 1

    @pytest.mark.asyncio
    async def test_glob_hook_fires_on_list_files_call(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "Glob",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo glob_fired",
                            "timeout": 2000,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(
            event_type="PreToolUse",
            tool_name="list_files",
            tool_args={"pattern": "*.py"},
        )
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 1

    @pytest.mark.asyncio
    async def test_edit_hook_fires_on_write_call(self):
        """Edit and Write are both aliased to edit_file — hook on Edit fires for Write."""
        config = {
            "PreToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo edit_fired",
                            "timeout": 2000,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event_data = EventData(
            event_type="PreToolUse",
            tool_name="Write",
            tool_args={"file_path": "test.py"},
        )
        result = await engine.process_event("PreToolUse", event_data)
        assert result.executed_hooks == 1


# ---------------------------------------------------------------------------
# executor: _build_stdin_payload
# ---------------------------------------------------------------------------


class TestBuildStdinPayload:
    def test_returns_bytes(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls"}
        )
        payload = _build_stdin_payload(event)
        assert isinstance(payload, bytes)

    def test_is_valid_json(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls"}
        )
        payload = _build_stdin_payload(event)
        parsed = json.loads(payload.decode("utf-8"))
        assert isinstance(parsed, dict)

    def test_contains_tool_name(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls"}
        )
        parsed = json.loads(_build_stdin_payload(event))
        assert parsed["tool_name"] == "Bash"

    def test_contains_hook_event_name(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        parsed = json.loads(_build_stdin_payload(event))
        assert parsed["hook_event_name"] == "PreToolUse"

    def test_contains_tool_input(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls -la"}
        )
        parsed = json.loads(_build_stdin_payload(event))
        assert parsed["tool_input"]["command"] == "ls -la"

    def test_contains_cwd(self):
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        parsed = json.loads(_build_stdin_payload(event))
        assert parsed["cwd"] == os.getcwd()

    def test_contains_permission_mode(self):
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        parsed = json.loads(_build_stdin_payload(event))
        assert "permission_mode" in parsed

    def test_contains_session_id(self):
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        parsed = json.loads(_build_stdin_payload(event))
        assert "session_id" in parsed

    def test_post_tool_includes_result(self):
        event = EventData(
            event_type="PostToolUse",
            tool_name="Edit",
            context={"result": "file saved", "duration_ms": 42.0},
        )
        parsed = json.loads(_build_stdin_payload(event))
        assert "tool_result" in parsed
        assert "tool_duration_ms" in parsed

    def test_handles_non_serializable_gracefully(self):
        class WeirdObj:
            def __str__(self):
                return "weird"

        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"obj": WeirdObj()}
        )
        payload = _build_stdin_payload(event)
        parsed = json.loads(payload.decode("utf-8"))
        assert parsed["tool_input"]["obj"] == "weird"


# ---------------------------------------------------------------------------
# executor: _build_environment
# ---------------------------------------------------------------------------


class TestBuildEnvironment:
    def test_returns_dict(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        env = _build_environment(event)
        assert isinstance(env, dict)

    def test_claude_project_dir(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        env = _build_environment(event)
        assert env["CLAUDE_PROJECT_DIR"] == os.getcwd()

    def test_claude_tool_name(self):
        event = EventData(event_type="PreToolUse", tool_name="MyTool")
        env = _build_environment(event)
        assert env["CLAUDE_TOOL_NAME"] == "MyTool"

    def test_claude_hook_event(self):
        event = EventData(event_type="PostToolUse", tool_name="Edit")
        env = _build_environment(event)
        assert env["CLAUDE_HOOK_EVENT"] == "PostToolUse"

    def test_claude_tool_input_is_json(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls"}
        )
        env = _build_environment(event)
        parsed = json.loads(env["CLAUDE_TOOL_INPUT"])
        assert parsed["command"] == "ls"

    def test_claude_code_hook_marker(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        env = _build_environment(event)
        assert env["CLAUDE_CODE_HOOK"] == "1"

    def test_file_path_env_var_set_when_present(self):
        event = EventData(
            event_type="PreToolUse",
            tool_name="Edit",
            tool_args={"file_path": "src/main.py"},
        )
        env = _build_environment(event)
        assert env.get("CLAUDE_FILE_PATH") == "src/main.py"

    def test_file_path_env_var_absent_when_no_file(self):
        event = EventData(
            event_type="PreToolUse", tool_name="Bash", tool_args={"command": "ls"}
        )
        env = _build_environment(event)
        assert "CLAUDE_FILE_PATH" not in env

    def test_custom_env_vars_merged(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        env = _build_environment(event, {"MY_CUSTOM_VAR": "hello"})
        assert env["MY_CUSTOM_VAR"] == "hello"

    def test_inherits_os_environment(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        env = _build_environment(event)
        # PATH should be inherited from os.environ
        assert "PATH" in env


# ---------------------------------------------------------------------------
# executor: execute_hooks_parallel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecuteHooksParallel:
    async def test_empty_list_returns_empty(self):
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        results = await execute_hooks_parallel([], event)
        assert results == []

    async def test_runs_all_hooks(self):
        hooks = [
            HookConfig(
                matcher="*", type="command", command="echo parallel1", timeout=2000
            ),
            HookConfig(
                matcher="*", type="command", command="echo parallel2", timeout=2000
            ),
            HookConfig(
                matcher="*", type="command", command="echo parallel3", timeout=2000
            ),
        ]
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        results = await execute_hooks_parallel(hooks, event)
        assert len(results) == 3

    async def test_all_successful(self):
        hooks = [
            HookConfig(matcher="*", type="command", command="echo a", timeout=2000),
            HookConfig(matcher="*", type="command", command="echo b", timeout=2000),
        ]
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        results = await execute_hooks_parallel(hooks, event)
        assert all(r.success for r in results)

    async def test_one_fails_others_still_run(self):
        hooks = [
            HookConfig(matcher="*", type="command", command="echo ok", timeout=2000),
            HookConfig(matcher="*", type="command", command="exit 1", timeout=2000),
            HookConfig(matcher="*", type="command", command="echo ok2", timeout=2000),
        ]
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        results = await execute_hooks_parallel(hooks, event)
        # All three must have a result (parallel = no stop-on-block)
        assert len(results) == 3

    async def test_returns_execution_results(self):
        hooks = [
            HookConfig(matcher="*", type="command", command="echo hello", timeout=2000)
        ]
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        results = await execute_hooks_parallel(hooks, event)
        assert isinstance(results[0], ExecutionResult)


# ---------------------------------------------------------------------------
# executor: format_execution_summary
# ---------------------------------------------------------------------------


class TestFormatExecutionSummary:
    def test_empty_returns_no_hooks_string(self):
        summary = format_execution_summary([])
        assert (
            "No hooks" in summary or len(summary) > 0
        )  # must not crash, must return something

    def test_summary_contains_executed_count(self):
        results = [
            ExecutionResult(
                blocked=False, hook_command="echo a", exit_code=0, stdout="a"
            ),
            ExecutionResult(
                blocked=False, hook_command="echo b", exit_code=0, stdout="b"
            ),
        ]
        summary = format_execution_summary(results)
        assert "2" in summary

    def test_summary_mentions_blocked(self):
        results = [
            ExecutionResult(
                blocked=True, hook_command="exit 1", exit_code=1, error="blocked"
            ),
        ]
        summary = format_execution_summary(results)
        assert "block" in summary.lower() or "1" in summary

    def test_returns_string(self):
        results = [ExecutionResult(blocked=False, hook_command="echo x", exit_code=0)]
        assert isinstance(format_execution_summary(results), str)


# ---------------------------------------------------------------------------
# executor: get_failed_results
# ---------------------------------------------------------------------------


class TestGetFailedResults:
    def test_empty_list(self):
        assert get_failed_results([]) == []

    def test_all_success(self):
        results = [
            ExecutionResult(blocked=False, hook_command="a", exit_code=0),
            ExecutionResult(blocked=False, hook_command="b", exit_code=0),
        ]
        assert get_failed_results(results) == []

    def test_one_failed(self):
        results = [
            ExecutionResult(blocked=False, hook_command="a", exit_code=0),
            ExecutionResult(blocked=True, hook_command="b", exit_code=1, error="fail"),
        ]
        failed = get_failed_results(results)
        assert len(failed) == 1
        assert failed[0].hook_command == "b"

    def test_all_failed(self):
        results = [
            ExecutionResult(blocked=True, hook_command="a", exit_code=1, error="x"),
            ExecutionResult(blocked=True, hook_command="b", exit_code=1, error="y"),
        ]
        assert len(get_failed_results(results)) == 2


# ---------------------------------------------------------------------------
# registry: build_registry_from_config
# ---------------------------------------------------------------------------


class TestBuildRegistryFromConfig:
    def test_empty_config(self):
        registry = build_registry_from_config({})
        assert registry.count_hooks() == 0

    def test_single_pre_tool_use(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo test"}],
                }
            ]
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks("PreToolUse") == 1

    def test_multiple_event_types(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo pre"}]}
            ],
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "echo post"}],
                }
            ],
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks("PreToolUse") == 1
        assert registry.count_hooks("PostToolUse") == 1
        assert registry.count_hooks() == 2

    def test_multiple_hooks_in_group(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo a"},
                        {"type": "command", "command": "echo b"},
                    ],
                }
            ]
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks("PreToolUse") == 2

    def test_hook_gets_correct_matcher(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo test"}],
                }
            ]
        }
        registry = build_registry_from_config(config)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert hooks[0].matcher == "Bash"

    def test_hook_once_flag(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo once", "once": True}
                    ],
                }
            ]
        }
        registry = build_registry_from_config(config)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert hooks[0].once is True

    def test_hook_disabled_flag(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo off", "enabled": False}
                    ],
                }
            ]
        }
        registry = build_registry_from_config(config)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 0  # disabled hooks not returned

    def test_comment_keys_skipped(self):
        config = {
            "_comment": "ignored",
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo ok"}]}
            ],
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks() == 1

    def test_missing_command_hook_skipped(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command"}],  # no command field
                }
            ]
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks() == 0

    def test_prompt_type_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "prompt", "prompt": "validate this"}],
                }
            ]
        }
        registry = build_registry_from_config(config)
        assert registry.count_hooks("PreToolUse") == 1

    def test_default_matcher_is_wildcard(self):
        """When matcher is absent, it defaults to '*'."""
        config = {
            "PreToolUse": [
                {
                    "hooks": [{"type": "command", "command": "echo test"}],
                }
            ]
        }
        registry = build_registry_from_config(config)
        hooks = registry.get_hooks_for_event("PreToolUse")
        assert len(hooks) == 1
        assert hooks[0].matcher == "*"


# ---------------------------------------------------------------------------
# registry: get_registry_stats
# ---------------------------------------------------------------------------


class TestGetRegistryStats:
    def test_empty_registry_stats(self):
        config = {}
        registry = build_registry_from_config(config)
        stats = get_registry_stats(registry)
        assert stats["total_hooks"] == 0
        assert stats["enabled_hooks"] == 0
        assert stats["disabled_hooks"] == 0

    def test_one_enabled_hook(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo a"}]}
            ]
        }
        registry = build_registry_from_config(config)
        stats = get_registry_stats(registry)
        assert stats["total_hooks"] == 1
        assert stats["enabled_hooks"] == 1
        assert stats["disabled_hooks"] == 0

    def test_one_disabled_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo a", "enabled": False}
                    ],
                }
            ]
        }
        registry = build_registry_from_config(config)
        stats = get_registry_stats(registry)
        assert stats["total_hooks"] == 1
        assert stats["disabled_hooks"] == 1
        assert stats["enabled_hooks"] == 0

    def test_by_event_section_present(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo a"}]}
            ]
        }
        registry = build_registry_from_config(config)
        stats = get_registry_stats(registry)
        assert "by_event" in stats
        # should have at least one event listed
        assert len(stats["by_event"]) >= 1

    def test_multiple_events_stats(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo pre1"},
                        {"type": "command", "command": "echo pre2"},
                    ],
                }
            ],
            "PostToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo post"}]}
            ],
        }
        registry = build_registry_from_config(config)
        stats = get_registry_stats(registry)
        assert stats["total_hooks"] == 3
        assert stats["enabled_hooks"] == 3


# ---------------------------------------------------------------------------
# engine: validate_config_file
# ---------------------------------------------------------------------------


class TestValidateConfigFile:
    def test_valid_config_returns_valid_string(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo ok"}]}
            ]
        }
        report = validate_config_file(config)
        assert isinstance(report, str)
        assert "valid" in report.lower()

    def test_invalid_config_returns_error_string(self):
        config = {"BadEvent": []}
        report = validate_config_file(config)
        assert isinstance(report, str)
        assert "error" in report.lower() or "BadEvent" in report or "✗" in report


# ---------------------------------------------------------------------------
# engine: reload_config
# ---------------------------------------------------------------------------


class TestReloadConfig:
    def test_reload_replaces_hooks(self):
        config1 = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo first"}],
                }
            ]
        }
        config2 = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo a"}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo b"}]},
            ]
        }
        engine = HookEngine(config1)
        assert engine.count_hooks() == 1
        engine.reload_config(config2)
        assert engine.count_hooks() == 2

    def test_reload_with_empty_config(self):
        config1 = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo a"}]}
            ]
        }
        engine = HookEngine(config1)
        engine.reload_config({})
        assert engine.count_hooks() == 0


# ---------------------------------------------------------------------------
# engine: env_vars passed through to hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEngineEnvVars:
    async def test_env_var_available_in_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo $MY_HOOK_VAR",
                            "timeout": 2000,
                        }
                    ],
                }
            ]
        }
        engine = HookEngine(config, env_vars={"MY_HOOK_VAR": "injected_value"})
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        result = await engine.process_event("PreToolUse", event)
        # The hook ran
        assert result.executed_hooks == 1
        # The env var appeared in stdout
        combined_output = result.get_combined_output()
        assert "injected_value" in combined_output

    async def test_set_env_vars_replaces(self):
        engine = HookEngine()
        engine.set_env_vars({"A": "1", "B": "2"})
        assert engine.env_vars == {"A": "1", "B": "2"}

    async def test_update_env_vars_merges(self):
        engine = HookEngine(env_vars={"A": "1"})
        engine.update_env_vars({"B": "2"})
        assert engine.env_vars["A"] == "1"
        assert engine.env_vars["B"] == "2"


# ---------------------------------------------------------------------------
# engine: parallel execution path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestParallelExecution:
    async def test_parallel_runs_all_hooks(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo p1", "timeout": 2000},
                        {"type": "command", "command": "echo p2", "timeout": 2000},
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        result = await engine.process_event("PreToolUse", event, sequential=False)
        assert result.executed_hooks == 2


# ---------------------------------------------------------------------------
# engine: stop_on_block=False continues past blocking hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStopOnBlockFalse:
    async def test_continues_past_block_when_disabled(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "exit 1", "timeout": 2000},
                        {
                            "type": "command",
                            "command": "echo continued",
                            "timeout": 2000,
                        },
                    ],
                }
            ]
        }
        engine = HookEngine(config)
        event = EventData(event_type="PreToolUse", tool_name="Bash")
        result = await engine.process_event("PreToolUse", event, stop_on_block=False)
        assert result.executed_hooks == 2  # both hooks ran


# ---------------------------------------------------------------------------
# engine: once-per-session reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOnceReset:
    async def test_reset_once_hooks_allows_re_execution(self):
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
        event = EventData(event_type="PreToolUse", tool_name="Bash")

        result1 = await engine.process_event("PreToolUse", event)
        assert result1.executed_hooks == 1
        result2 = await engine.process_event("PreToolUse", event)
        assert result2.executed_hooks == 0  # exhausted
        engine.reset_once_hooks()
        result3 = await engine.process_event("PreToolUse", event)
        assert result3.executed_hooks == 1  # fires again after reset


# ---------------------------------------------------------------------------
# Public API: __init__ exports
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_hook_engine_importable(self):
        from code_puppy.hook_engine import HookEngine

        assert HookEngine is not None

    def test_hook_config_importable(self):
        from code_puppy.hook_engine import HookConfig

        assert HookConfig is not None

    def test_event_data_importable(self):
        from code_puppy.hook_engine import EventData

        assert EventData is not None

    def test_execution_result_importable(self):
        from code_puppy.hook_engine import ExecutionResult

        assert ExecutionResult is not None

    def test_process_event_result_importable(self):
        from code_puppy.hook_engine import ProcessEventResult

        assert ProcessEventResult is not None

    def test_aliases_module_importable(self):
        from code_puppy.hook_engine import aliases

        assert aliases is not None

    def test_hook_registry_importable(self):
        from code_puppy.hook_engine import HookRegistry

        assert HookRegistry is not None
