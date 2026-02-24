"""
Hook knowledge base for Code Puppy.

Unified catalog of:
- Code Puppy lifecycle callbacks (callbacks.py phases)
- Code Puppy event-based hooks (hook_engine events)
- Claude Code hook events (for reference/parity)
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class HookEvent:
    """Metadata for a hook event."""
    name: str
    category: str  # "lifecycle" or "event"
    description: str
    matcher_support: bool
    matcher_examples: List[str]
    input_fields: Dict[str, str]
    output_options: List[str]
    timeout_default: int
    code_example: str


# Code Puppy Lifecycle Callbacks (from callbacks.py)
LIFECYCLE_CALLBACKS = [
    HookEvent(
        name="startup",
        category="lifecycle",
        description="Application boot, after plugin loader runs",
        matcher_support=False,
        matcher_examples=[],
        input_fields={},
        output_options=["None"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback

async def _on_startup():
    # Initialize resources
    print("Plugin started!")

register_callback("startup", _on_startup)
""",
    ),
    HookEvent(
        name="shutdown",
        category="lifecycle",
        description="Application is exiting gracefully",
        matcher_support=False,
        matcher_examples=[],
        input_fields={},
        output_options=["None"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback

async def _on_shutdown():
    # Cleanup resources
    print("Plugin shutting down!")

register_callback("shutdown", _on_shutdown)
""",
    ),
    HookEvent(
        name="custom_command",
        category="lifecycle",
        description="User types a /slash command",
        matcher_support=False,
        matcher_examples=[],
        input_fields={"command": "str", "name": "str"},
        output_options=["None (not handled)", "True (handled, no model)", "str (send to model)"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info

def _handle_custom_command(command: str, name: str):
    if name == "greet":
        emit_info("Hello! 👋")
        return True
    return None

register_callback("custom_command", _handle_custom_command)
""",
    ),
    HookEvent(
        name="custom_command_help",
        category="lifecycle",
        description="Build the /help menu",
        matcher_support=False,
        matcher_examples=[],
        input_fields={},
        output_options=["list[tuple[str, str]]"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback

def _custom_help():
    return [
        ("greet", "Emit a greeting"),
        ("ping", "Check if active"),
    ]

register_callback("custom_command_help", _custom_help)
""",
    ),
    HookEvent(
        name="pre_tool_call",
        category="lifecycle",
        description="Before any tool executes",
        matcher_support=False,
        matcher_examples=[],
        input_fields={"tool_name": "str", "tool_args": "dict"},
        output_options=["None"],
        timeout_default=5000,
        code_example="""from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

async def _on_pre_tool_call(tool_name, tool_args, context=None):
    logger.debug(f"Tool: {tool_name}")

register_callback("pre_tool_call", _on_pre_tool_call)
""",
    ),
    HookEvent(
        name="post_tool_call",
        category="lifecycle",
        description="After a tool finishes executing",
        matcher_support=False,
        matcher_examples=[],
        input_fields={"tool_name": "str", "tool_args": "dict", "result": "Any", "duration_ms": "float"},
        output_options=["None"],
        timeout_default=5000,
        code_example="""from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

async def _on_post_tool_call(tool_name, tool_args, result, duration_ms, context=None):
    if duration_ms > 5000:
        logger.warning(f"Slow tool: {tool_name} took {duration_ms/1000:.1f}s")

register_callback("post_tool_call", _on_post_tool_call)
""",
    ),
    HookEvent(
        name="agent_run_start",
        category="lifecycle",
        description="Agent run begins",
        matcher_support=False,
        matcher_examples=[],
        input_fields={"agent_name": "str", "model_name": "str", "session_id": "str | None"},
        output_options=["None"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback
import time

_timers = {}

async def _on_agent_run_start(agent_name, model_name, session_id=None):
    key = session_id or "default"
    _timers[key] = time.monotonic()

register_callback("agent_run_start", _on_agent_run_start)
""",
    ),
    HookEvent(
        name="agent_run_end",
        category="lifecycle",
        description="Agent run completes (in finally block)",
        matcher_support=False,
        matcher_examples=[],
        input_fields={"agent_name": "str", "model_name": "str", "success": "bool", "error": "Exception | None"},
        output_options=["None"],
        timeout_default=0,
        code_example="""from code_puppy.callbacks import register_callback
import time, logging

logger = logging.getLogger(__name__)
_timers = {}

async def _on_agent_run_end(agent_name, model_name, session_id=None, success=True, error=None, **kwargs):
    key = session_id or "default"
    start = _timers.pop(key, None)
    if start:
        elapsed = time.monotonic() - start
        status = "✓" if success else "✗"
        logger.info(f"{status} {agent_name} finished in {elapsed:.1f}s")

register_callback("agent_run_end", _on_agent_run_end)
""",
    ),
]

# Code Puppy Event-Based Hooks (from hook_engine/models.py)
EVENT_BASED_HOOKS = [
    HookEvent(
        name="PreToolUse",
        category="event",
        description="Before a tool call executes. Can block it.",
        matcher_support=True,
        matcher_examples=["Bash", "Edit|Write", "mcp__.*", ""],
        input_fields={
            "session_id": "unique session identifier",
            "cwd": "working directory",
            "hook_event_name": "PreToolUse",
            "tool_name": "name of the tool",
            "tool_input": "arguments passed to tool",
        },
        output_options=[
            "exit 0 (allow)",
            "exit 2 (block, write reason to stderr)",
            "JSON with permissionDecision: allow|deny|ask",
        ],
        timeout_default=5000,
        code_example="""#!/bin/bash
INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Block dangerous commands
if echo "$COMMAND" | grep -q "drop table"; then
  echo "Blocked: SQL drop not allowed" >&2
  exit 2
fi

exit 0
""",
    ),
    HookEvent(
        name="PostToolUse",
        category="event",
        description="After a tool call succeeds",
        matcher_support=True,
        matcher_examples=["Edit|Write", "Bash", "mcp__github__.*"],
        input_fields={
            "session_id": "unique session identifier",
            "cwd": "working directory",
            "hook_event_name": "PostToolUse",
            "tool_name": "name of the tool",
            "tool_input": "arguments passed to tool",
        },
        output_options=["exit 0 (success)", "stdout content added to context (for SessionStart hooks only)"],
        timeout_default=5000,
        code_example="""#!/bin/bash
INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ "$TOOL" = "Edit" ] || [ "$TOOL" = "Write" ]; then
  echo "File edited: $FILE" >> ~/code-puppy-audit.log
fi

exit 0
""",
    ),
    HookEvent(
        name="SessionStart",
        category="event",
        description="When a session begins or resumes",
        matcher_support=True,
        matcher_examples=["startup", "resume", "clear", "compact"],
        input_fields={
            "session_id": "unique session identifier",
            "source": "startup|resume|clear|compact",
            "cwd": "working directory",
        },
        output_options=[
            "exit 0 + stdout (content added to context)",
            "exit 0 + JSON with additionalContext",
        ],
        timeout_default=5000,
        code_example="""#!/bin/bash
# Re-inject context after compaction
echo "Remember: Always run tests before committing."
echo "Use 'bun' not 'npm' in this project."
exit 0
""",
    ),
    HookEvent(
        name="Stop",
        category="event",
        description="When Claude finishes responding",
        matcher_support=False,
        matcher_examples=[],
        input_fields={
            "session_id": "unique session identifier",
            "stop_hook_active": "bool",
        },
        output_options=[
            "exit 0 (allow stop)",
            "exit 2 (block, continue working)",
            "JSON with decision: block|allow",
        ],
        timeout_default=5000,
        code_example="""#!/bin/bash
INPUT=$(cat)

# Prevent infinite loops
if [ "$(echo "$INPUT" | jq -r '.stop_hook_active')" = "true" ]; then
  exit 0
fi

# Check if tests pass before allowing stop
if ! npm test > /dev/null 2>&1; then
  echo "Tests failed, keep working" >&2
  exit 2
fi

exit 0
""",
    ),
]

# Claude Code Hooks (for reference/parity documentation)
CLAUDE_CODE_REFERENCE_HOOKS = [
    "SessionStart - Session begins/resumes",
    "UserPromptSubmit - User submits a prompt",
    "PreToolUse - Before tool execution (can block)",
    "PermissionRequest - Permission dialog appears",
    "PostToolUse - After tool succeeds",
    "PostToolUseFailure - After tool fails",
    "Notification - Notification sent",
    "SubagentStart - Subagent spawned",
    "SubagentStop - Subagent finishes",
    "Stop - Claude finishes responding",
    "TaskCompleted - Task marked complete",
    "ConfigChange - Config file changed",
    "WorktreeCreate - Worktree created",
    "WorktreeRemove - Worktree removed",
    "PreCompact - Before context compaction",
    "SessionEnd - Session terminates",
]


def get_hook_by_name(name: str) -> Optional[HookEvent]:
    """Find a hook event by name."""
    for hook in LIFECYCLE_CALLBACKS + EVENT_BASED_HOOKS:
        if hook.name.lower() == name.lower():
            return hook
    return None


def get_hooks_by_category(category: str) -> List[HookEvent]:
    """Get all hooks in a category."""
    return [h for h in LIFECYCLE_CALLBACKS + EVENT_BASED_HOOKS if h.category == category]


def list_all_hooks() -> Dict[str, List[HookEvent]]:
    """Get hooks organized by category."""
    return {
        "lifecycle": LIFECYCLE_CALLBACKS,
        "event": EVENT_BASED_HOOKS,
    }
