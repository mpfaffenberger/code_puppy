"""Plugin that adds /rewind for removing complete conversation turns."""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.plugins.rewind.history import rewind_history


def emit_error(message: Any) -> None:
    from code_puppy.messaging import emit_error as _emit_error

    _emit_error(message)


def emit_success(message: Any) -> None:
    from code_puppy.messaging import emit_success as _emit_success

    _emit_success(message)


def emit_warning(message: Any) -> None:
    from code_puppy.messaging import emit_warning as _emit_warning

    _emit_warning(message)


def _custom_help() -> list[tuple[str, str]]:
    return [
        (
            "rewind [turns]",
            "Remove the most recent completed conversation turn(s) from history",
        )
    ]


def _parse_rewind_count(command: str) -> int | None:
    tokens = command.split()
    if len(tokens) == 1:
        return 1

    if len(tokens) > 2:
        emit_error("/rewind: usage: /rewind [turns]")
        return None

    try:
        count = int(tokens[1])
    except ValueError:
        emit_error(
            f"/rewind: '{tokens[1]}' is not a valid integer – usage: /rewind [turns]"
        )
        return None

    if count < 1:
        emit_error("/rewind: turns must be a positive integer")
        return None

    return count


def _handle_rewind_command(command: str) -> bool:
    from code_puppy.agents.agent_manager import get_current_agent

    count = _parse_rewind_count(command)
    if count is None:
        return True

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/rewind: could not get current agent – {exc}")
        return True

    history = list(agent.get_message_history())
    result = rewind_history(history, count)

    if result.rewound_turns == 0:
        emit_warning("/rewind: no completed conversation turns to remove")
        return True

    try:
        agent.set_message_history(result.history)
    except Exception as exc:
        emit_error(f"/rewind: failed to update message history – {exc}")
        return True

    turn_word = "turn" if result.rewound_turns == 1 else "turns"
    message_word = "message" if result.removed_messages == 1 else "messages"
    summary = f"⏪ Rewound {result.rewound_turns} {turn_word}"
    if result.rewound_turns < result.requested_turns:
        summary += f" (requested {result.requested_turns}; only {result.rewound_turns} available)"
    summary += f". Removed {result.removed_messages} history {message_word}."
    emit_success(summary)
    return True


def _handle_custom_command(command: str, name: str) -> bool | None:
    if name != "rewind":
        return None

    return _handle_rewind_command(command)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)


__all__ = [
    "_custom_help",
    "_handle_custom_command",
    "_handle_rewind_command",
    "_parse_rewind_count",
]
