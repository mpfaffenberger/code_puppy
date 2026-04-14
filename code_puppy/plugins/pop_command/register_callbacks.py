"""Plugin that adds /pop for trimming recent conversation history."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from code_puppy.callbacks import register_callback


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


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "pop",
            "Delete the N most-recent messages and prune broken tool-call fragments",
        )
    ]


def _has_only_tool_returns(message: Any) -> bool:
    """Return True when a request message contains only tool-return parts."""
    try:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        if not isinstance(message, ModelRequest):
            return False

        parts = getattr(message, "parts", []) or []
        return bool(parts) and all(isinstance(part, ToolReturnPart) for part in parts)
    except Exception:
        return False


def _has_unresolved_tool_calls(message: Any) -> bool:
    """Return True when a response message still contains unresolved tool calls."""
    try:
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        if not isinstance(message, ModelResponse):
            return False

        parts = getattr(message, "parts", []) or []
        return any(isinstance(part, ToolCallPart) for part in parts)
    except Exception:
        return False


def _prune_dangling_tool_fragments(history: List[Any]) -> tuple[List[Any], int]:
    """Strip incomplete tool-call sequences from the tail of history."""
    pruned = 0

    while history:
        tail = history[-1]
        if _has_only_tool_returns(tail):
            history.pop()
            pruned += 1
            continue

        if _has_unresolved_tool_calls(tail):
            history.pop()
            pruned += 1
            continue

        break

    return history, pruned


def _parse_pop_count(command: str) -> Optional[int]:
    tokens = command.split()
    if len(tokens) < 2:
        return 1

    try:
        count = int(tokens[1])
    except ValueError:
        emit_error(f"/pop: '{tokens[1]}' is not a valid integer – usage: /pop [N]")
        return None

    if count < 1:
        emit_error("/pop: N must be a positive integer")
        return None

    return count


def _handle_pop_command(command: str) -> bool:
    from code_puppy.agents.agent_manager import get_current_agent

    count = _parse_pop_count(command)
    if count is None:
        return True

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/pop: could not get current agent – {exc}")
        return True

    history: List[Any] = list(agent.get_message_history())
    if not history:
        emit_warning("/pop: conversation history is empty – nothing to remove")
        return True

    poppable = len(history) - 1
    if poppable <= 0:
        emit_warning("/pop: only the system prompt is in history – nothing to remove")
        return True

    if count > poppable:
        emit_warning(
            f"/pop: requested {count} but only {poppable} message(s) can be removed "
            f"(the system prompt is always preserved). Removing {poppable}."
        )
        count = poppable

    before_count = len(history)
    history = history[: before_count - count]
    history, extra_pruned = _prune_dangling_tool_fragments(history)
    after_count = len(history)
    total_removed = before_count - after_count

    try:
        agent.set_message_history(history)
    except Exception as exc:
        emit_error(f"/pop: failed to update message history – {exc}")
        return True

    summary_parts = [f":scissors: Popped {count} message(s)"]
    if extra_pruned:
        summary_parts.append(
            f"and pruned {extra_pruned} extra incomplete tool-call fragment(s)"
        )

    remaining = max(after_count - 1, 0)
    emit_success(
        " ".join(summary_parts)
        + ".\n"
        + f":scroll: History: {before_count - 1} → {remaining} message(s) "
        + f"(excluding system prompt, removed {total_removed} total)"
    )

    if after_count <= 1:
        emit_info(":bulb: History is now empty (system prompt only). Starting fresh!")

    return True


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "pop":
        return None

    return _handle_pop_command(command)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)


__all__ = [
    "_custom_help",
    "_handle_custom_command",
    "_handle_pop_command",
    "_parse_pop_count",
    "_prune_dangling_tool_fragments",
    "_has_only_tool_returns",
    "_has_unresolved_tool_calls",
]
