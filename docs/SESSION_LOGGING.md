# Session Logging

Code Puppy supports configurable session logging to record your interactive sessions in markdown or JSON format.

## Configuration

Session logging is configured via `session_logging.json` (located at `~/.code_puppy/session_logging.json`):

```json
{
  "enabled": true,
  "log_file": "~/.code_puppy/sessions/{session_id}.md",
  "format": "markdown",
  "user_prompts": true,
  "agent_reasoning": true,
  "agent_responses": true,
  "tool_calls": true,
  "tool_outputs": true,
  "timestamp_format": "ISO8601"
}
```

The configuration file is automatically created with default values on first run.

## Runtime Control

You can control session logging at runtime using the `/session_logging` command:

```bash
# Check current status
/session_logging
/session_logging status

# Enable logging
/session_logging on

# Disable logging
/session_logging off

# Toggle on/off
/session_logging toggle
```

**Aliases:** `/log`, `/logging`

The runtime toggle **persists to the JSON config file**, so your preference is remembered across sessions.

## Status Display

The `/show` command includes session logging status:

```
[bold]session_logging:[/bold]       enabled (toggle: /session_logging)
```

## Configuration Options

### `enabled`
- **Type**: boolean
- **Default**: `false`
- **Description**: Enable or disable session logging

### `log_file`
- **Type**: string (file path)
- **Default**: `~/.code_puppy/sessions/{session_id}.md`
- **Description**: Path template for log files. Use `{session_id}` as a placeholder for the unique session identifier.

### `format`
- **Type**: string
- **Default**: `markdown`
- **Values**: `markdown`, `json`
- **Description**: Output format for session logs

### `user_prompts`
- **Type**: boolean
- **Default**: `true`
- **Description**: Include user prompts in the log

### `agent_reasoning`
- **Type**: boolean
- **Default**: `true`
- **Description**: Include agent reasoning (from `agent_share_your_reasoning` tool)

### `agent_responses`
- **Type**: boolean
- **Default**: `true`
- **Description**: Include agent responses in the log

### `tool_calls`
- **Type**: boolean
- **Default**: `true`
- **Description**: Include tool invocations in the log

### `tool_outputs`
- **Type**: boolean
- **Default**: `true`
- **Description**: Include tool outputs in the log

### `timestamp_format`
- **Type**: string
- **Default**: `ISO8601`
- **Values**: `ISO8601`, `unix`, `human`
- **Description**: Timestamp format for log entries
  - `ISO8601`: `2025-12-11T08:09:01.718544`
  - `unix`: `1765458541` (Unix epoch)
  - `human`: `2025-12-11 08:09:01`

## Context Clearing

When you use the `/clear` command, a context cleared marker is added to the session log to indicate where conversation history was reset. The session continues in the same log file with clear visual separation.

## Example Markdown Log

```markdown
# Session Log: code_puppy.20251211.140948

**Started:** 2025-12-11T08:09:01.718544

---

## 👤 User Prompt
**Time:** 2025-12-11T08:09:01.718641

Create a hello world script

---

### 🤔 Agent Reasoning
**Time:** 2025-12-11T08:09:01.718662

I need to create a Python script. I'll use edit_file to create it.

### 🔧 Tool Call: `edit_file`
**Time:** 2025-12-11T08:09:01.718674

```json
{
  "file_path": "hello.py",
  "content": "print(\"Hello, World!\")"
}
```

### ✅ Tool Output: `edit_file`
**Time:** 2025-12-11T08:09:01.718729

```json
{
  "success": true,
  "path": "hello.py"
}
```

## 🤖 Agent Response
**Time:** 2025-12-11T08:09:01.718751

I've created a hello world script in hello.py

---

## 🔄 CONTEXT CLEARED
**Time:** 2025-12-11T09:15:30.123456

User cleared conversation history. Starting new conversation in same session.

---

## 👤 User Prompt
**Time:** 2025-12-11T09:15:35.654321

Now create a goodbye script

---
```

## Example JSON Log

With `"format": "json"`, each log entry is a separate JSON object on its own line:

```json
{"type": "session_start", "session_id": "code_puppy.20251211.140948", "timestamp": "2025-12-11T08:09:01.718544"}
{"type": "user_prompt", "timestamp": "2025-12-11T08:09:01.718641", "content": "Create a hello world script"}
{"type": "agent_reasoning", "timestamp": "2025-12-11T08:09:01.718662", "content": "I need to create a Python script..."}
{"type": "tool_call", "timestamp": "2025-12-11T08:09:01.718674", "tool_name": "edit_file", "arguments": {"file_path": "hello.py", "content": "print(\"Hello, World!\")"}}
{"type": "tool_output", "timestamp": "2025-12-11T08:09:01.718729", "tool_name": "edit_file", "output": {"success": true, "path": "hello.py"}}
{"type": "agent_response", "timestamp": "2025-12-11T08:09:01.718751", "content": "I've created a hello world script in hello.py"}
{"type": "context_cleared", "timestamp": "2025-12-11T09:15:30.123456", "message": "User cleared conversation history. Starting new conversation in same session."}
{"type": "user_prompt", "timestamp": "2025-12-11T09:15:35.654321", "content": "Now create a goodbye script"}
```

## Session IDs

Each terminal session gets a unique session ID based on the git repository (or current directory) and timestamp:
```
{repo_name}.{YYYYMMDD}.{HHMMSS}
```

**Examples:**

In a git repository:
```
code_puppy.20251211.140948
```

Not in a git repository (uses current directory name):
```
my-scripts.20251211.140948
home.20251211.153022
```

This ensures that:
- Session logs are human-readable and organized by project/directory
- Each session has a unique timestamp
- You can easily find logs for a specific project and time
- Sessions don't overwrite each other
- Works intelligently whether you're in a git repo or not

## Log Location

By default, logs are stored in:
```
~/.code_puppy/sessions/{session_id}.md
```

You can customize this path in `session_logging.json` using the `{session_id}` placeholder.

## Use Cases

### 1. Auditing and Compliance
Keep detailed records of all AI-assisted code changes for security audits and compliance requirements.

### 2. Learning and Training
Review your interaction patterns to learn how to prompt the agent more effectively.

### 3. Debugging
Trace back through a session to understand what went wrong and why.

### 4. Documentation
Generate documentation from session logs showing how specific features were implemented.

### 5. Analysis
Parse JSON logs to analyze agent performance, tool usage patterns, and response times.

## Privacy Considerations

⚠️ **Important**: Session logs may contain:
- Proprietary code
- API keys or secrets (if mentioned in prompts)
- System information
- Project structure details

Ensure logs are stored securely and excluded from version control:

```bash
# Add to .gitignore
.code_puppy/sessions/
```

## Performance Impact

Session logging is designed to be non-intrusive:
- Asynchronous file writes
- Thread-safe operations
- Automatic output truncation (>5000 chars)
- Silent error handling (logging failures don't crash the session)

Typical overhead: **< 1ms per log entry**

## Selective Logging

You can disable specific log categories in your `session_logging.json`:

```json
{
  "enabled": true,
  "log_file": "~/.code_puppy/sessions/{session_id}.md",
  "format": "markdown",
  "user_prompts": true,
  "agent_reasoning": false,
  "agent_responses": true,
  "tool_calls": false,
  "tool_outputs": false,
  "timestamp_format": "ISO8601"
}
```

## Programmatic Access

For JSON logs, you can easily parse and analyze them:

```python
import json
from pathlib import Path

log_file = Path("~/.code_puppy/sessions/terminal-pid-12345-a3f2b1.json").expanduser()

for line in log_file.read_text().strip().split("\n"):
    entry = json.loads(line)
    if entry["type"] == "tool_call":
        print(f"Tool: {entry['tool_name']}, Args: {entry['arguments']}")
```

## FAQ

### Q: Can I change the log format mid-session?
A: No, the format is set when the session starts. You'd need to restart Code Puppy.

### Q: Are logs rotated or archived?
A: Not automatically. Each session creates a new log file. You can implement your own rotation script.

### Q: What's the performance impact?
A: Minimal. Writes are async and non-blocking. Even on slow disks, overhead is < 1ms per entry.

### Q: Can I log to stdout instead of a file?
A: Not currently, but this could be added as a future enhancement.

### Q: Are multi-agent invocations logged?
A: Agent reasoning from sub-agents is logged when they use `agent_share_your_reasoning`.

## Troubleshooting

### Logs not being created
1. Check that `"enabled": true` in `~/.code_puppy/session_logging.json`
2. Verify the log directory exists and is writable
3. Look for error messages on startup

### Incomplete logs
1. Ensure Code Puppy exited cleanly (not killed)
2. Check disk space
3. Verify file permissions

### Large log files
1. Tool outputs are automatically truncated at 5000 characters
2. Consider disabling `"tool_outputs": false` in your config if not needed
3. Implement a log rotation script
