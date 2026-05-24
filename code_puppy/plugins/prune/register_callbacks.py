"""Plugin that adds /prune for surgical history pruning.

/prune opens a multi-select TUI of conversation history. Unlike /pop
(which slices a contiguous tail), /prune lets the user cherry-pick
arbitrary whole messages and rip them out. Selection granularity is
at the message level only — individual tool calls within a message
cannot be removed in isolation; they always travel with their parent
message (and their matching tool returns elsewhere in history are
cascaded out via the orphan-cleanup pass).

The system prompt is always preserved.

Usage:
    /prune              Open interactive multi-select TUI
"""

from __future__ import annotations

from typing import Any, List, Optional, Set, Tuple

from code_puppy.callbacks import register_callback


# ── messaging wrappers ──────────────────────────────────────────────────────


def emit_error(message: Any) -> None:
    from code_puppy.messaging import emit_error as _emit_error

    _emit_error(message)


def emit_info(message: Any) -> None:
    from code_puppy.messaging import emit_info as _emit_info

    _emit_info(message)


def emit_success(message: Any) -> None:
    from code_puppy.messaging import emit_success as _emit_success

    _emit_success(message)


def emit_warning(message: Any) -> None:
    from code_puppy.messaging import emit_warning as _emit_warning

    _emit_warning(message)


# ── /help integration ───────────────────────────────────────────────────────


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "prune",
            "Multi-select pruner — cherry-pick whole messages to remove",
        )
    ]


# ── tool-fragment pruning ──────────────────────────────────────────────────
# After dropping selected messages, the tail of history may still hold
# orphaned ToolCallPart or ToolReturnPart fragments. Providers (notably
# Anthropic) require every ToolCallPart to have a matching
# ToolReturnPart and vice versa, so we walk the tail and strip any
# fragment whose ``tool_call_id`` has no live partner in the remaining
# history.


def _collect_tool_ids(history: List[Any]) -> Tuple[Set[str], Set[str]]:
    call_ids: Set[str] = set()
    return_ids: Set[str] = set()
    try:
        from pydantic_ai.messages import ToolCallPart, ToolReturnPart
    except Exception:
        return call_ids, return_ids

    for message in history:
        for part in getattr(message, "parts", []) or []:
            if isinstance(part, ToolCallPart):
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    call_ids.add(tcid)
            elif isinstance(part, ToolReturnPart):
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    return_ids.add(tcid)
    return call_ids, return_ids


def _has_orphaned_returns(message: Any, call_ids: Set[str]) -> bool:
    try:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        if not isinstance(message, ModelRequest):
            return False
        parts = getattr(message, "parts", []) or []
        if not parts:
            return False
        if not all(isinstance(p, ToolReturnPart) for p in parts):
            return False
        return any(
            not getattr(p, "tool_call_id", None) or p.tool_call_id not in call_ids
            for p in parts
        )
    except Exception:
        return False


def _has_orphaned_calls(message: Any, return_ids: Set[str]) -> bool:
    try:
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        if not isinstance(message, ModelResponse):
            return False
        for part in getattr(message, "parts", []) or []:
            if isinstance(part, ToolCallPart):
                tcid = getattr(part, "tool_call_id", None)
                if not tcid or tcid not in return_ids:
                    return True
        return False
    except Exception:
        return False


def _prune_dangling_tool_fragments(history: List[Any]) -> Tuple[List[Any], int]:
    """Strip genuinely orphaned tool-call sequences from the tail."""
    pruned = 0
    while history:
        call_ids, return_ids = _collect_tool_ids(history)
        tail = history[-1]
        if _has_orphaned_returns(tail, call_ids):
            history.pop()
            pruned += 1
            continue
        if _has_orphaned_calls(tail, return_ids):
            history.pop()
            pruned += 1
            continue
        break
    return history, pruned


# ── core mutation ──────────────────────────────────────────────────────────


def _collect_removed_tool_call_ids(
    history: List[Any],
    drop_indices: Set[int],
) -> Set[str]:
    """Compute the full set of tool_call_ids whose returns must also go.

    Collects every ToolCallPart id living inside the messages we're
    dropping wholesale, so the matching ToolReturnPart fragments
    elsewhere in history can be cascaded out as orphans.
    """
    removed: Set[str] = set()
    try:
        from pydantic_ai.messages import ModelResponse, ToolCallPart
    except Exception:
        return removed

    for hist_idx in drop_indices:
        if hist_idx < 0 or hist_idx >= len(history):
            continue
        msg = history[hist_idx]
        if not isinstance(msg, ModelResponse):
            continue
        for part in getattr(msg, "parts", []) or []:
            if isinstance(part, ToolCallPart):
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    removed.add(tcid)
    return removed


def _message_carries_system_prompt(message: Any) -> bool:
    """True if ``message`` is a ModelRequest containing a SystemPromptPart.

    Matches both a standalone system message and pydantic-ai's bundled
    ``SystemPromptPart + UserPromptPart`` request.
    """
    try:
        from pydantic_ai.messages import ModelRequest, SystemPromptPart
    except Exception:
        return False
    if not isinstance(message, ModelRequest):
        return False
    for part in getattr(message, "parts", []) or []:
        if isinstance(part, SystemPromptPart):
            return True
    return False


def _message_has_orphan_tool_return(message: Any, orphan_call_ids: Set[str]) -> bool:
    """True if ``message`` is a ModelRequest carrying a ToolReturnPart
    whose ``tool_call_id`` is in ``orphan_call_ids``.

    Used to cascade-drop messages that would otherwise leave the model
    looking at a tool result with no matching tool call (which providers
    like Anthropic reject outright).
    """
    if not orphan_call_ids:
        return False
    try:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        try:
            from pydantic_ai.messages import RetryPromptPart  # type: ignore
        except Exception:  # pragma: no cover — older pydantic-ai
            RetryPromptPart = None  # type: ignore[assignment]
    except Exception:
        return False
    if not isinstance(message, ModelRequest):
        return False
    reply_kinds: tuple = (ToolReturnPart,)
    if RetryPromptPart is not None:
        reply_kinds = (ToolReturnPart, RetryPromptPart)
    for part in getattr(message, "parts", []) or []:
        if isinstance(part, reply_kinds):
            tcid = getattr(part, "tool_call_id", None)
            if tcid and tcid in orphan_call_ids:
                return True
    return False


def _perform_prune(drop_indices: Set[int]) -> None:
    """Apply the prune selection to current agent history.

    Operates on whole messages only: each index in ``drop_indices`` is
    removed from history, any ToolReturnPart messages whose matching
    ToolCallPart was dropped are cascade-removed, and orphaned
    tool-call/return fragments at the tail are cleaned up.
    """
    from code_puppy.agents.agent_manager import get_current_agent

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/prune: could not get current agent – {exc}")
        return

    history: List[Any] = list(agent.get_message_history())
    if not history:
        emit_warning("/prune: conversation history is empty – nothing to remove")
        return

    # Defensive filter: ignore out-of-range indices and silently skip
    # any message that carries a SystemPromptPart so the agent's
    # identity can never be dropped.
    drop_indices = {
        i
        for i in drop_indices
        if 0 <= i < len(history) and not _message_carries_system_prompt(history[i])
    }

    if not drop_indices:
        emit_info("/prune: nothing selected – history unchanged")
        return

    # First pass: figure out which tool_call_ids belonged to dropped
    # messages so we can cascade-drop their orphaned returns elsewhere.
    orphan_call_ids = _collect_removed_tool_call_ids(history, drop_indices)

    before_count = len(history)

    new_history: List[Any] = []
    msgs_dropped = 0
    cascade_dropped = 0

    for hist_idx, msg in enumerate(history):
        if hist_idx in drop_indices:
            msgs_dropped += 1
            continue
        if _message_has_orphan_tool_return(msg, orphan_call_ids):
            cascade_dropped += 1
            continue
        new_history.append(msg)

    new_history, extra_pruned = _prune_dangling_tool_fragments(new_history)
    after_count = len(new_history)

    try:
        agent.set_message_history(new_history)
    except Exception as exc:
        emit_error(f"/prune: failed to update message history – {exc}")
        return

    summary_lines = [
        ":scissors: Prune complete.",
        f"  · {msgs_dropped} message(s) removed by selection",
    ]
    if cascade_dropped:
        summary_lines.append(
            f"  · {cascade_dropped} message(s) cascade-dropped (orphaned tool returns)"
        )
    if extra_pruned:
        summary_lines.append(
            f"  · {extra_pruned} dangling tool fragment(s) cleaned from tail"
        )
    summary_lines.append(
        f":scroll: History: {before_count - 1} → {max(after_count - 1, 0)} message(s) "
        f"(excluding system prompt)"
    )

    emit_success("\n".join(summary_lines))

    if after_count <= 1:
        emit_info(":bulb: History is now empty (system prompt only). Starting fresh!")


# ── /prune dispatch ────────────────────────────────────────────────────────


def _handle_prune_command(command: str) -> bool:
    del command  # /prune takes no arguments anymore
    _launch_menu()
    return True


def _launch_menu() -> None:
    from code_puppy.agents.agent_manager import get_current_agent

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/prune: could not get current agent – {exc}")
        return

    raw_history: List[Any] = list(agent.get_message_history())

    # Sibling modules within the same package.
    from code_puppy.plugins.prune.prune_menu import PruneMenu
    from code_puppy.plugins.prune.prune_model import (
        ContextBudget,
        annotate_context_window,
        build_message_entries,
    )

    entries = build_message_entries(raw_history)
    # Bail out when there's nothing the user can actually toggle.
    # Locked rows (system bundle or history[0]) are non-prunable, so an
    # all-locked list is the same as an empty conversation.
    if not entries or all(e.is_locked for e in entries):
        emit_info("/prune: no prunable messages")
        return

    # Annotate token counts and in-context flags. Failures are silent —
    # the menu just won't show the indicators.
    try:
        budget = annotate_context_window(entries, raw_history, agent)
    except Exception:
        budget = ContextBudget()

    try:
        menu = PruneMenu(entries=entries, budget=budget)
    except ValueError as exc:
        emit_info(f"/prune: {exc}")
        return

    selection = menu.run()

    if selection is None:
        emit_info("/prune: cancelled")
        return

    if selection.is_empty:
        emit_info("/prune: nothing selected – history unchanged")
        return

    _perform_prune(selection.history_indices_to_drop)


# ── custom_command plumbing ────────────────────────────────────────────────


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "prune":
        return None
    return _handle_prune_command(command)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)


__all__ = [
    "_collect_removed_tool_call_ids",
    "_custom_help",
    "_handle_custom_command",
    "_handle_prune_command",
    "_message_has_orphan_tool_return",
    "_perform_prune",
    "_prune_dangling_tool_fragments",
]
