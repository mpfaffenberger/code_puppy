"""Surface a live, tool-aware activity label on the spinner.

While a tool runs, the spinner shows what's happening ("Running: npm test",
"Reading src/app.py") instead of a static "thinking…", so a long action reads
as live progress. Wired through the central pre/post tool-call hooks so every
tool benefits from one place.

When ``compact_steps`` is enabled (Option B — default on), each completed tool
additionally prints a stacked ``✓ label`` row *above* the spinner's pinned
footer via ``ConsoleSpinner.print_above``. That row persists in scrollback,
matching the Claude-Code / Codex visual the user asked for. The ledger stays
the source of truth for ``/steps`` replay.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from code_puppy.callbacks import register_callback
from code_puppy.config import get_compact_steps
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


def _strip_leading_running(label: str) -> str:
    """Drop the ``Running: `` prefix when storing into the ledger so the
    completed row reads as ``✓ npm test`` rather than ``✓ Running: npm test``.
    """
    text = (label or "").strip()
    if text.lower().startswith("running:"):
        text = text.split(":", 1)[1].strip()
    return text or label


async def _on_pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> None:
    try:
        label = _activity_label(tool_name, tool_args)
        SpinnerBase.set_activity(label)
        if get_compact_steps():
            try:
                from code_puppy.messaging.step_ledger import get_ledger

                SpinnerBase.set_ledger_active(True)
                get_ledger().begin_active(label)
            except Exception:
                pass
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
        if get_compact_steps():
            try:
                from code_puppy.messaging.spinner import get_active_spinner
                from code_puppy.messaging.step_ledger import get_ledger

                ledger = get_ledger()
                # Complete the active row (if any) so the ledger history
                # stays accurate for ``/steps`` replay.
                final_label = (
                    _strip_leading_running(ledger.active.label)
                    if ledger.has_active() and ledger.active
                    else None
                )
                if ledger.has_active():
                    ledger.complete_active(final_label)
                # Commit a stacked ``✓ label`` row above the footer so the
                # step persists in scrollback (the screenshot's UX).
                if final_label:
                    row = Text()
                    row.append("  ✓ ", style="bold green")
                    row.append(final_label, style="dim")
                    spinner = get_active_spinner()
                    if spinner is not None:
                        spinner.print_above(row)
            except Exception:
                pass
    except Exception:
        pass


register_callback("pre_tool_call", _on_pre_tool_call)
register_callback("post_tool_call", _on_post_tool_call)
