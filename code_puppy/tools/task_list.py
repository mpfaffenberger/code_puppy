"""A lightweight, self-maintained task list (todo) for the agent.

The agent calls ``update_task_list`` to record and revise an ordered plan for
non-trivial work. The full list is passed on every call (replace semantics),
so there is exactly one authoritative checklist; the agent marks items
``in_progress`` / ``completed`` as it goes. Purely organizational — no side
effects, no filesystem writes.
"""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_info

Status = Literal["pending", "in_progress", "completed"]

_STATUS_GLYPH: Dict[str, str] = {
    "pending": "[ ]",
    "in_progress": "[→]",
    "completed": "[x]",
}

# Per-agent authoritative list, keyed by agent identity so concurrent agents
# don't clobber each other. In-memory only.
_TASK_LISTS: Dict[str, List[dict]] = {}


class TaskItem(BaseModel):
    content: str = Field(description="Short imperative description of one step.")
    status: Status = Field(
        default="pending",
        description="'pending', 'in_progress' (at most one), or 'completed'.",
    )


class TaskListOutput(BaseModel):
    success: bool
    rendered: str


def _agent_key() -> str:
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        return get_current_agent().get_identity()
    except Exception:
        return "default"


def render_task_list(tasks: List[dict]) -> str:
    if not tasks:
        return "(task list cleared)"
    lines = []
    for i, task in enumerate(tasks, 1):
        glyph = _STATUS_GLYPH.get(task.get("status", "pending"), "[ ]")
        lines.append(f"{glyph} {i}. {task.get('content', '')}")
    return "\n".join(lines)


def get_task_list(agent_key: str | None = None) -> List[dict]:
    """Return the current stored task list (used by status/UI consumers)."""
    return list(_TASK_LISTS.get(agent_key or _agent_key(), []))


def _apply_update(tasks: List[TaskItem]) -> TaskListOutput:
    items = [task.model_dump() for task in tasks]
    _TASK_LISTS[_agent_key()] = items
    rendered = render_task_list(items)
    emit_info("📋 Task list\n" + rendered, message_group="task_list")
    return TaskListOutput(success=True, rendered=rendered)


def register_update_task_list(agent):
    """Register the update_task_list tool."""

    @agent.tool
    def update_task_list(context: RunContext, tasks: List[TaskItem]) -> TaskListOutput:
        """Record or revise your ordered task list for the current work.

        Pass the FULL list every call — this replaces the previous list. Mark
        each item's status: 'pending', 'in_progress' (keep exactly one in
        progress at a time), or 'completed'. Use it to plan and track
        multi-step work so you don't lose the thread; skip it for trivial
        one-step asks. This is organizational only and continues
        autonomously — never wait on the user after updating it.
        """
        del context
        return _apply_update(tasks)
