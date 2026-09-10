"""Conversation state carried by real message metadata, never parsed from prose."""

import re
from dataclasses import replace
from typing import Any

from pydantic_ai.messages import ModelRequest

SESSION_KEY = "code_puppy_session_v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def validate_agent_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(
            "agent_id must be 1-128 letters, digits, dots, colons, underscores or hyphens"
        )
    return value


def read_session_state(history: list[Any]) -> dict[str, Any] | None:
    for message in reversed(history):
        if isinstance(message, ModelRequest) and SESSION_KEY in (
            message.metadata or {}
        ):
            state = message.metadata[SESSION_KEY]
            if not isinstance(state, dict):
                raise ValueError("Invalid conversation metadata")
            validate_agent_id(state.get("agent_id"))
            for key in ("prompt_body", "project_rules"):
                if key in state and not isinstance(state[key], str):
                    raise ValueError(f"Invalid conversation {key}")
            prepared = state.get("prepared_prompt")
            if prepared is not None:
                if (
                    not isinstance(prepared, dict)
                    or any(
                        not isinstance(prepared.get(key), str)
                        for key in ("model_name", "instructions", "system_prompt")
                    )
                    or not isinstance(prepared.get("is_claude_code"), bool)
                    or any(
                        key in prepared and not isinstance(prepared[key], str)
                        for key in ("source_prompt", "preparation_scope")
                    )
                ):
                    raise ValueError("Invalid conversation prepared_prompt")
            return {
                **state,
                **({"prepared_prompt": dict(prepared)} if prepared is not None else {}),
            }
    return None


def stamp_session_state(agent: Any, messages: list[Any]) -> list[Any]:
    """Checkpoint state on the newest request after compaction; preserve other metadata."""
    export = getattr(agent, "get_session_state", None)
    if not callable(export):
        return messages
    return stamp_state(export(), messages)


def stamp_state(state: dict[str, Any], messages: list[Any]) -> list[Any]:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, ModelRequest):
            result = list(messages)
            result[index] = replace(
                message, metadata={**(message.metadata or {}), SESSION_KEY: state}
            )
            return result
    return messages
