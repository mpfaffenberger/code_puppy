"""Helpers for rewinding complete conversation turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class RewindResult:
    """Result of removing complete turns from message history."""

    history: list[Any]
    requested_turns: int
    rewound_turns: int
    removed_messages: int


def rewind_history(history: Sequence[Any], turns: int) -> RewindResult:
    """Remove the last ``turns`` user-started conversation turns.

    Pydantic AI stores a conversation as a flat list of model messages. A user
    turn starts at a ``ModelRequest`` containing at least one ``UserPromptPart``;
    every following message belongs to that turn until the next user prompt.
    Removing from the turn boundary through the tail removes tool calls, tool
    returns, text responses, attachment parts, and any other components that
    would otherwise be sent back to the model.
    """
    if turns < 1:
        raise ValueError("turns must be a positive integer")

    original = list(history)
    if not original:
        return RewindResult(original, turns, 0, 0)

    boundary = len(original)
    rewound = 0
    for index in range(len(original) - 1, -1, -1):
        if _is_user_turn_start(original[index]):
            boundary = index
            rewound += 1
            if rewound == turns:
                break

    if rewound == 0:
        return RewindResult(original, turns, 0, 0)

    new_history = original[:boundary]
    return RewindResult(
        history=new_history,
        requested_turns=turns,
        rewound_turns=rewound,
        removed_messages=len(original) - len(new_history),
    )


def _is_user_turn_start(message: Any) -> bool:
    """Return True when a message starts a user conversation turn."""
    try:
        from pydantic_ai.messages import ModelRequest, UserPromptPart
    except Exception:  # pragma: no cover - import guard for exotic installs
        return False

    if not isinstance(message, ModelRequest):
        return False

    parts = getattr(message, "parts", None) or []
    return any(isinstance(part, UserPromptPart) for part in parts)


__all__ = ["RewindResult", "rewind_history"]
