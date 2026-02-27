# Code Puppy Hooks

Hooks let you intercept and control every tool call the agent makes — before it runs, after it runs, or both. They are compatible with the Claude Code `.claude/settings.json` format, so any hook script that works in Claude Code works in Code Puppy out of the box.

---

## How It Works

```text
User prompt → Agent decides to call a tool
                        ↓
              [PreToolUse hooks run]
                 • match tool name
                 • run your script(s)
                 • exit 1 → BLOCK (tool never runs)
                 • exit 0 → ALLOW
                        ↓
              [Tool executes normally]
                        ↓
              [PostToolUse hooks run]
                 • observe result
                 • exit 2 → send stderr to Claude as feedback
                 • exit 0 → stdout shown in transcript
```

Hook scripts receive a JSON payload on **stdin** and optionally via the `CLAUDE_TOOL_INPUT` environment variable. They communicate back purely through exit codes and stdout/stderr — no special library needed.

---

## Quick Start

Create `.claude/settings.json` in your project root:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|agent_run_shell_command",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/no-git.sh",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

Create the hook script `.claude/hooks/no-git.sh`:

```bash
#!/bin/bash
# Block git commands
input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // empty')

if echo "$command" | grep -qE '(^|\s)git(\s|$)'; then
  echo "[BLOCKED] Git commands are not allowed — use the PR workflow." >&2
  exit 1
fi
exit 0
```

Make it executable: `chmod +x .claude/hooks/no-git.sh`

Restart Code Puppy — any attempt to run a `git` command will be blocked cleanly.

---

## Hook Input Format

Every hook script receives a JSON object on **stdin**:

```json
{
  "session_id": "codepuppy-session",
  "hook_event_name": "PreToolUse",
  "tool_name": "agent_run_shell_command",
  "tool_input": {
    "command": "echo hello"
  },
  "cwd": "/home/user/myproject",
  "permission_mode": "default"
}
```

For `PostToolUse`, the payload also includes `tool_result` and `tool_duration_ms`.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAUDE_TOOL_INPUT` | JSON string of the tool's arguments |
| `CLAUDE_TOOL_NAME` | Name of the tool being called |
| `CLAUDE_HOOK_EVENT` | Event type (`PreToolUse`, `PostToolUse`, …) |
| `CLAUDE_PROJECT_DIR` | Absolute path to the project root |
| `CLAUDE_FILE_PATH` | Extracted file path, if the tool targets a file |
| `CLAUDE_CODE_HOOK` | Always `1` — marks the process as a hook |

### Variable Substitution in Commands

```json
"command": "black ${file}"
"command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/my-hook.sh"
```

---

## Exit Codes

| Code | Meaning | Effect |
|------|---------|--------|
| `0` | Allow | Tool runs. Stdout shown in transcript. |
| `1` | Block | Tool is prevented. Stderr shown as block reason. |
| `2` | Error feedback | Stderr fed back to the agent. Tool still runs. |

---

## Hook Event Types

| Event | Fires | Can Block? |
|-------|-------|-----------|
| `PreToolUse` | Before any tool call | Yes (exit 1) |
| `PostToolUse` | After any tool call | No (observation only) |
| `SessionStart` | When a session begins | No |
| `Stop` | When agent finishes a task | Yes |
| `SubagentStop` | When a sub-agent finishes | Yes |

---

## Matcher Syntax

```text
"Bash|agent_run_shell_command"   regex OR — matches either tool name
"Edit && .py"                     AND — tool is Edit AND file ends in .py
"*"                               wildcard — matches everything
"edit_file"                       exact internal tool name
```

**Code Puppy tool name mapping:**

| Claude Code Name | Code Puppy Internal Name |
|-----------------|--------------------------|
| `Bash` | `agent_run_shell_command` |
| `Edit` / `Write` | `edit_file` |
| `Delete` | `delete_file` |

Use `Bash|agent_run_shell_command` to catch shell commands with either name.

---

## Configuration Reference

```jsonc
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|agent_run_shell_command",
        "hooks": [
          {
            "type": "command",        // "command" or "prompt"
            "command": "bash .claude/hooks/check.sh",
            "timeout": 5000           // milliseconds, default 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/logger.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

**Config locations (priority order):**
1. `.claude/settings.json` — project-level
2. `~/.code_puppy/hooks.json` — global user hooks

---

## Implementation Notes

The hook engine lives in `code_puppy/hook_engine/` and is a self-contained library with no dependency on the rest of Code Puppy.

Hooks are injected at the `pydantic-ai` `ToolManager._call_tool()` level via a patch in `code_puppy/pydantic_patches.py`, so they fire on every tool call regardless of which agent or model is in use.

When a `PreToolUse` hook exits with code `1`, the tool call returns an `ERROR: Hook blocked ...` string as its result. The agent reads this, understands the rejection, and reports it to the user — no crash, no retry loop.

---

## Troubleshooting

**Hook isn't running:**
- Use `"matcher": "*"` temporarily to confirm the engine loads.
- Check startup logs for: `Hook engine ready - Total: N`.
- Ensure the script is executable: `chmod +x .claude/hooks/my-hook.sh`.

**JSON parsing fails in your script:**
- Use `.tool_input.command` (not `.command`) — the Claude Code format nests args under `tool_input`.
- Test standalone: `echo '{"tool_input":{"command":"echo test"}}' | bash .claude/hooks/my-hook.sh`
