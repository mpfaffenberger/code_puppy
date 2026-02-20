# Hook Engine

A standalone, testable hook execution system for processing events and executing
configured hooks with pattern matching, timeout handling, and blocking capabilities.

## Overview

The Hook Engine provides a complete system for implementing event-driven automation
through configurable hooks. It is compatible with Anthropic's Claude Code
`.claude/settings.json` format.

Features:
- **Pattern matching** - Wildcards, file extensions, `&&` / `||` compound logic, regex
- **Event types** - PreToolUse, PostToolUse, SessionStart, Stop, and more
- **Async execution** - Non-blocking subprocess execution with per-hook timeouts
- **Claude Code compatible stdin** - JSON payload on stdin, env vars for compatibility
- **Blocking capability** - Exit code 1 vetoes the tool call
- **Once-per-session** - Hooks that only run once per session
- **Comprehensive validation** - Clear error messages for misconfigured hooks

## Quick Start

```python
from code_puppy.hook_engine import HookEngine, EventData

config = {
    "PreToolUse": [{
        "matcher": "Bash|agent_run_shell_command",
        "hooks": [{
            "type": "command",
            "command": "bash .claude/hooks/my-check.sh",
            "timeout": 5000
        }]
    }]
}

engine = HookEngine(config)
event_data = EventData(
    event_type="PreToolUse",
    tool_name="agent_run_shell_command",
    tool_args={"command": "git status"}
)

result = await engine.process_event("PreToolUse", event_data)
if result.blocked:
    print(f"Blocked: {result.blocking_reason}")
```

## Hook Input Format

Scripts receive JSON on stdin (Claude Code compatible):

```json
{
    "session_id": "codepuppy-session",
    "hook_event_name": "PreToolUse",
    "tool_name": "agent_run_shell_command",
    "tool_input": {"command": "git status"},
    "cwd": "/path/to/project",
    "permission_mode": "default"
}
```

Also available as environment variables: `CLAUDE_TOOL_INPUT`, `CLAUDE_TOOL_NAME`,
`CLAUDE_PROJECT_DIR`, `CLAUDE_HOOK_EVENT`, `CLAUDE_FILE_PATH`.

## Exit Codes

- `0` - Allow (stdout shown in transcript)
- `1` - Block (stderr shown as block reason)
- `2` - Error feedback to Claude without blocking

See `docs/HOOKS.md` for the full user-facing guide.
