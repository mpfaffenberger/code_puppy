"""The enforcement gate — pre/post tool-call hooks.

``pre_tool_call``  : decide whether to BLOCK a tool. Returns a dict shaped
                     ``{"blocked": True, "reason": ..., "error_message": ...}``
                     which ``code_puppy/pydantic_patches.py`` turns into a clean
                     ``ERROR: ...`` tool result (no crash, model can react).
``post_tool_call`` : count the call, unlock on skill actions, track nudges, and
                     record skill usage for the curator.

All state lives in :mod:`budget` (synced to the conversation carrier), so it
survives compaction, resume, and restart. Everything is a no-op while
enforcement is disarmed (opt-in).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from . import budget
from .config import (
    get_max_budget,
    get_onboarding_budget,
    is_enabled,
    is_task_enforcement_enabled,
)
from .hermes_time import now_iso

logger = logging.getLogger(__name__)

_ACTING_TOOLS = frozenset(
    {
        "edit_file",
        "create_file",
        "replace_in_file",
        "delete_snippet",
        "write",
        "edit",
        "str_replace",
        "file_write",
    }
)


def _block(reason: str) -> Dict[str, Any]:
    msg = f"[BLOCKED] {reason}"
    return {"blocked": True, "reason": msg, "error_message": msg}


def _budget_block_message() -> str:
    onboarding = get_onboarding_budget()
    max_budget = get_max_budget()
    return (
        f"SKILL BUDGET ENFORCEMENT — you have used your onboarding budget of "
        f"{onboarding} tool calls.\n\n"
        "You MUST now engage the skills system before continuing:\n"
        '  1. Create a skill: skill_manage(action="create", name=..., '
        "description=..., instructions=...)\n"
        "  2. Or load an existing one: activate_skill(skill_name=...)\n\n"
        f"After a skill action your budget expands to {max_budget} and all "
        "tools unlock."
    )


def _has_active_task() -> bool:
    """Best-effort check for an in-progress task.

    If the task subsystem is missing or raises, we fall back to the configured
    posture (``hermes_governance_task_enforcement_fail_open``): fail OPEN by
    default (return True, allow the tool) so a missing optional subsystem never
    deadlocks the agent — but log it, because a silently-disabled gate is its
    own footgun. Set the key false to fail CLOSED (block when unverifiable).
    """
    try:
        from code_puppy.tools.task_tools import get_task_store  # type: ignore

        store = get_task_store()
        tasks = store.list_tasks() if store else []
        for task in tasks or []:
            status = getattr(task, "status", None) or (
                task.get("status") if isinstance(task, dict) else None
            )
            if status in ("in_progress", "pending"):
                return True
        return False
    except Exception:
        from .config import is_task_fail_open

        fail_open = is_task_fail_open()
        logger.warning(
            "hermes_governance: task system unavailable; task enforcement failing %s",
            "OPEN (tools allowed)" if fail_open else "CLOSED (tools blocked)",
        )
        return fail_open


def pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> Optional[Dict[str, Any]]:
    """Block tools that violate the active governance policy."""
    if not is_enabled():
        return None

    if budget.is_exempt(tool_name):
        return None

    if budget.would_exceed():
        logger.debug("hermes_governance: blocking %s (budget exceeded)", tool_name)
        return _block(_budget_block_message())

    if is_task_enforcement_enabled() and not _has_active_task():
        return _block(
            "TASK ENFORCEMENT — no active task. Create one with task_create "
            "and mark it in_progress before running this tool."
        )

    return None


def _call_succeeded(result: Any) -> bool:
    """Best-effort: did a tool call actually succeed?

    Guards against the *fake unlock* bypass — calling ``activate_skill`` on a
    non-existent skill (or ``skill_manage`` with a validation error) must NOT
    unlock the budget or record phantom skill usage. We treat a call as failed
    when the result carries a truthy ``error`` field, or its string form looks
    like a not-found / error message. Fails *closed* for unlock purposes: if we
    cannot tell, we do NOT grant the unlock (the agent can retry a real action).
    """
    if result is None:
        return False
    # SkillManageOutput and similar carry an ``error`` attribute / key.
    err = getattr(result, "error", None)
    if err is None and isinstance(result, dict):
        err = result.get("error")
    if err:
        return False
    text = str(result).strip().lower()
    if not text:
        return False
    bad_markers = ("not found", "error", "invalid", "too short", "already exists")
    if any(m in text for m in bad_markers):
        return False
    return True


def post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any = None,
    duration_ms: float = 0.0,
    context: Any = None,
) -> None:
    """Count the call, unlock on *successful* skill actions, advance nudges."""
    if not is_enabled():
        return

    if budget.is_unlock_action(tool_name):
        # Only a SUCCESSFUL skill action unlocks the budget and counts as
        # real usage. This closes the fake-unlock bypass (failed activate_skill
        # on a bogus name) and keeps the curator's skill_usage map honest.
        if not _call_succeeded(result):
            logger.debug(
                "hermes_governance: %s did not succeed — no unlock, no skill_use",
                tool_name,
            )
            return
        if budget.unlock():
            logger.debug("hermes_governance: budget unlocked via %s", tool_name)
        budget.reset_nudge_counters()
        # Record which skill was actually used, for curator lifecycle tracking.
        if tool_name.strip().lower() in ("activate_skill", "skill_manage"):
            skill_name = ""
            if isinstance(tool_args, dict):
                skill_name = str(
                    tool_args.get("skill_name") or tool_args.get("name") or ""
                )
            if skill_name:
                budget.record_skill_use(skill_name, now_iso())
        return

    if budget.is_exempt(tool_name):
        return

    budget.increment()
    budget.note_nudge_call(tool_name.strip().lower() in _ACTING_TOOLS)
