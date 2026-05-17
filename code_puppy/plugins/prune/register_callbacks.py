"""Plugin that adds /prune for surgical history pruning.

/prune opens a multi-select TUI of conversation history. Unlike /pop
(which slices a contiguous tail), /prune lets the user cherry-pick
arbitrary messages — and even individual tool calls inside messages —
and rip them out.

The system prompt is always preserved.

Usage:
    /prune              Open interactive multi-select TUI
    /prune preview      Open TUI but report changes without applying
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
            "Multi-select pruner — cherry-pick messages and/or tool calls to remove",
        )
    ]


# ── tool-fragment pruning (shared logic with pop_command) ──────────────────
# After surgical edits we may still leave behind orphaned tool calls or
# returns. This pass cleans the tail in the same conservative manner as
# pop_command's pruner. The duplication is deliberate — sibling plugins
# don't depend on each other.


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
    drop_tool_call_ids: Set[str],
) -> Set[str]:
    """Compute the full set of tool_call_ids whose returns must also go.

    Includes:
      - all ToolCallPart ids living inside messages we're dropping wholesale
      - the explicitly-flagged individual tool call ids
    """
    removed: Set[str] = set(drop_tool_call_ids)
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

    Whole-message removal only. Individual ToolCallPart / ToolReturnPart
    surgery used to be supported, but editing a ``ModelResponse``'s parts
    in place breaks Anthropic's invariant that ``thinking`` /
    ``redacted_thinking`` blocks in the latest assistant message must
    remain byte-identical to what the model returned. Full-entry-or-
    nothing avoids that whole class of bug.
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

    # Defensive: never drop the system prompt (index 0).
    drop_indices = {i for i in drop_indices if i != 0 and 0 <= i < len(history)}

    if not drop_indices:
        emit_info("/prune: nothing selected – history unchanged")
        return

    # First pass: figure out which tool_call_ids belonged to dropped
    # messages so we can cascade-drop their orphaned returns elsewhere.
    orphan_call_ids = _collect_removed_tool_call_ids(history, drop_indices, set())

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
    tokens = command.split()
    sub = tokens[1].lower() if len(tokens) >= 2 else ""
    if sub == "debug":
        _emit_debug_report()
        return True
    preview_only = sub == "preview"
    _launch_menu(preview_only=preview_only)
    return True


def _emit_debug_report() -> None:
    """Print a diagnostic dump of the same numbers the menu would use.

    Helps figure out why context indicators look wrong without firing up
    the TUI. Read-only — never mutates history.
    """
    from code_puppy.agents.agent_manager import get_current_agent

    from code_puppy.plugins.prune.prune_model import (
        annotate_context_window,
        build_message_entries,
    )

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/prune debug: could not get current agent – {exc}")
        return

    raw_history: List[Any] = list(agent.get_message_history())
    entries = build_message_entries(raw_history, agent)

    # Probe each agent helper independently with explicit error reporting.
    try:
        ctx_raw = agent._get_model_context_length()
        ctx_repr = f"{ctx_raw!r} (type={type(ctx_raw).__name__})"
    except Exception as exc:
        ctx_repr = f"<exception: {exc!r}>"

    try:
        overhead_raw = agent._estimate_context_overhead()
        overhead_repr = f"{overhead_raw!r} (type={type(overhead_raw).__name__})"
    except Exception as exc:
        overhead_repr = f"<exception: {exc!r}>"

    try:
        model_name = agent.get_model_name()
    except Exception as exc:
        model_name = f"<exception: {exc!r}>"

    budget = annotate_context_window(entries, raw_history, agent)

    greens = sum(1 for e in entries if e.in_context is True)
    reds = sum(1 for e in entries if e.in_context is False)
    nones = sum(1 for e in entries if e.in_context is None)
    token_sum = sum(e.tokens or 0 for e in entries)
    none_tokens = sum(1 for e in entries if e.tokens is None)

    avail = (
        (budget.context_length or 0) - (budget.overhead_tokens or 0)
        if budget.context_length is not None
        else None
    )

    lines = [
        ":mag: /prune debug",
        f"  model:               {model_name}",
        f"  raw history length:  {len(raw_history)} message(s)",
        f"  entries built:       {len(entries)}",
        f"  agent.ctx_length:    {ctx_repr}",
        f"  agent.overhead:      {overhead_repr}",
        f"  budget.context_len:  {budget.context_length}",
        f"  budget.overhead:     {budget.overhead_tokens}",
        f"  budget.used_tokens:  {budget.used_tokens}",
        f"  budget.total_used:   {budget.total_used}",
        f"  budget.pct_used:     {budget.percent_used}",
        f"  budget.available:    {budget.available}",
        f"  available_budget:    {avail}",
        f"  sum(entry.tokens):   {token_sum}",
        f"  entries w/ tokens=None: {none_tokens}",
        f"  in_context green=●:  {greens}",
        f"  in_context red=○:    {reds}",
        f"  in_context none=·:   {nones}",
    ]
    if entries:
        sample = entries[:3] + entries[-3:] if len(entries) > 6 else entries
        lines.append("  sample entries (idx, role, tokens, in_context):")
        for e in sample:
            lines.append(
                f"    #{e.history_index:>3}  {e.role:<12}  "
                f"tokens={e.tokens}  in_context={e.in_context}"
            )
    emit_info("\n".join(lines))


def _launch_menu(*, preview_only: bool) -> None:
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

    entries = build_message_entries(raw_history, agent)
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
        menu = PruneMenu(entries=entries, preview_only=preview_only, budget=budget)
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

    if preview_only:
        msg_count = len(selection.history_indices_to_drop)
        emit_info(
            f"/prune preview: would remove {msg_count} message(s). Run /prune to apply."
        )
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
