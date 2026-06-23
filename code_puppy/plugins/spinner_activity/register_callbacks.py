"""Surface a live, tool-aware activity label on the spinner.

While a tool runs, the spinner shows what's happening ("Running: npm test",
"Reading src/app.py") instead of a static "thinking…", so a long action reads
as live progress. Wired through the central pre/post tool-call hooks so every
tool benefits from one place.
"""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.messaging.spinner import resume_all_spinners
from code_puppy.messaging.spinner.spinner_base import SpinnerBase


def _short(value: Any, limit: int = 56) -> str:
    text = " ".join(str(value).split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _activity_label(tool_name: str, tool_args: dict | None) -> str:
    name = (tool_name or "").lower()
    args = tool_args or {}

    def arg(*keys: str) -> str:
        for key in keys:
            value = args.get(key)
            if value:
                return _short(value)
        return ""

    if name in ("agent_run_shell_command", "run_shell_command"):
        cmd = arg("command")
        return f"Running: {cmd}" if cmd else "Running shell command"
    if name == "read_file":
        target = arg("file_path", "path")
        return f"Reading {target}" if target else "Reading file"
    if name == "grep":
        pattern = arg("search_string", "pattern", "query")
        return f"Searching {pattern}" if pattern else "Searching"
    if name in ("create_file", "replace_in_file", "delete_snippet", "delete_file"):
        target = arg("file_path", "path")
        return f"Editing {target}" if target else "Editing file"
    if name == "list_files":
        target = arg("directory", "path") or "."
        return f"Listing {target}"
    if name in ("invoke_agent", "invoke_agent_with_model"):
        agent = arg("agent_name", "agent")
        return f"Delegating to {agent}" if agent else "Delegating to subagent"
    if name == "update_task_list":
        return "Updating task list"
    if name in ("activate_skill", "list_or_search_skills"):
        return "Using a skill"
    return f"Running {tool_name or 'tool'}"


async def _on_pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> None:
    try:
        SpinnerBase.set_activity(_activity_label(tool_name, tool_args))
        # The stream handler keeps the spinner paused when transitioning into a
        # tool call, so a long tool would otherwise run with no indicator at
        # all. Resume it here (guarded against user-input prompts) so the
        # activity label animates while the tool executes.
        resume_all_spinners()
    except Exception:
        pass


async def _on_post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    try:
        SpinnerBase.clear_activity()
    except Exception:
        pass


register_callback("pre_tool_call", _on_pre_tool_call)
register_callback("post_tool_call", _on_post_tool_call)
