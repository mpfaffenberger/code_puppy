"""Tool registration for ask_user_question."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Annotated, Any, Dict, List

from pydantic import BeforeValidator, Field, WithJsonSchema
from pydantic_ai import RunContext

from .constants import (
    MAX_DESCRIPTION_LENGTH,
    MAX_HEADER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_OPTIONS_PER_QUESTION,
    MAX_QUESTION_LENGTH,
    MAX_QUESTIONS_PER_CALL,
    MIN_OPTIONS_PER_QUESTION,
)
from .handler import ask_user_question_async as _ask_user_question_impl
from .models import AskUserQuestionOutput

if TYPE_CHECKING:
    from pydantic_ai import Agent


# Inline JSON schemas to avoid $defs/$ref that many LLM providers misinterpret.
# This matches the approach used by replace_in_file for complex nested types.
# Include maxLength constraints so LLMs know the limits upfront.
_OPTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "maxLength": MAX_LABEL_LENGTH,
            "description": f"Short option name (1-5 words, max {MAX_LABEL_LENGTH} chars)",
        },
        "description": {
            "type": "string",
            "maxLength": MAX_DESCRIPTION_LENGTH,
            "description": f"Optional explanation (max {MAX_DESCRIPTION_LENGTH} chars)",
        },
    },
    "required": ["label"],
}

_QUESTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "maxLength": MAX_QUESTION_LENGTH,
            "description": f"The full question text (max {MAX_QUESTION_LENGTH} chars)",
        },
        "header": {
            "type": "string",
            "maxLength": MAX_HEADER_LENGTH,
            "description": f"Short label for compact display (max {MAX_HEADER_LENGTH} chars, no spaces)",
        },
        "multi_select": {
            "type": "boolean",
            "description": "If true, user can select multiple options (default: false)",
        },
        "input_mode": {
            "type": "string",
            "enum": ["select", "text", "select_or_text"],
            "description": "Use 'text' for free-form user input, 'select' for options, or 'select_or_text' for both.",
        },
        "input_placeholder": {
            "type": "string",
            "maxLength": MAX_DESCRIPTION_LENGTH,
            "description": "Placeholder shown for free-form text input.",
        },
        "options": {
            "type": "array",
            "items": _OPTION_SCHEMA,
            "minItems": 0,
            "maxItems": MAX_OPTIONS_PER_QUESTION,
            "description": f"Array of 0-{MAX_OPTIONS_PER_QUESTION} selectable options. Use at least {MIN_OPTIONS_PER_QUESTION} unless input_mode is 'text'.",
        },
    },
    "required": ["question", "header"],
}

_QUESTIONS_ARRAY_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": _QUESTION_SCHEMA,
    "minItems": 1,
    "maxItems": MAX_QUESTIONS_PER_CALL,
    "description": (
        f"Array of 1-{MAX_QUESTIONS_PER_CALL} question objects. Each question needs: "
        f"'question' (max {MAX_QUESTION_LENGTH} chars), "
        f"'header' (max {MAX_HEADER_LENGTH} chars, no spaces), "
        f"'options' (array of 0-{MAX_OPTIONS_PER_QUESTION} options with 'label'). "
        "Optional: 'multi_select' (boolean), 'input_mode' ('select', 'text', or 'select_or_text'), "
        "and 'input_placeholder'."
    ),
}


# Backward-compat: the registered tool schema keeps `options` as required
# with legacy minItems, while `_QUESTIONS_ARRAY_SCHEMA` remains browser-friendly
# (options optional for input_mode="text").
_TOOL_QUESTION_SCHEMA: Dict[str, Any] = copy.deepcopy(_QUESTION_SCHEMA)
_TOOL_QUESTION_SCHEMA["required"] = ["question", "header", "options"]
_TOOL_QUESTION_SCHEMA["properties"]["options"]["minItems"] = MIN_OPTIONS_PER_QUESTION

_TOOL_QUESTIONS_ARRAY_SCHEMA: Dict[str, Any] = copy.deepcopy(_QUESTIONS_ARRAY_SCHEMA)
_TOOL_QUESTIONS_ARRAY_SCHEMA["items"] = _TOOL_QUESTION_SCHEMA


def _coerce_questions_json_string(v: Any) -> Any:
    """Coerce a JSON-stringified array to a native list before pydantic validates it.

    LLMs frequently pass the questions array as a JSON string (e.g. ``"[{...}]"``)
    instead of a native list. pydantic-ai validates tool call arguments against
    the function signature before calling the handler — so the coercion must
    happen here, at the registration layer, before pydantic sees the value.

    If JSON parsing fails, the original value is returned unchanged and pydantic
    produces a clear type error.
    """
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return v
    return v


# Type alias with explicit JSON schema override so LLMs see the full structure.
# The BeforeValidator handles JSON-string coercion before validation.
# The WithJsonSchema tells pydantic to emit our inline schema instead of inferring.
QuestionsListWithSchema = Annotated[
    List[Dict[str, Any]],
    BeforeValidator(_coerce_questions_json_string),
    WithJsonSchema(_TOOL_QUESTIONS_ARRAY_SCHEMA),
    Field(
        description=(
            f"Array of 1-{MAX_QUESTIONS_PER_CALL} question objects. Each question needs: "
            f"'question' (max {MAX_QUESTION_LENGTH} chars), "
            f"'header' (max {MAX_HEADER_LENGTH} chars), "
            f"'options' (0-{MAX_OPTIONS_PER_QUESTION} options with 'label'; "
            "at least 2 unless input_mode='text')."
        )
    ),
]


def _resolve_tool_result(result: Any) -> Any:
    """Resolve a possibly-awaitable tool result for sync registration paths."""
    if not inspect.isawaitable(result):
        return result

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread, safe to run directly.
        return asyncio.run(result)

    # Running event loop in this thread: resolve on a dedicated thread+loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(result)).result()


def register_ask_user_question(agent: Agent) -> None:
    """Register the ask_user_question tool with the given agent."""

    @agent.tool
    def ask_user_question(
        context: RunContext,  # noqa: ARG001 - Required by framework
        questions: QuestionsListWithSchema,
    ) -> AskUserQuestionOutput:
        """Ask the user multiple related questions in the active UI."""
        # Keep the external tool schema simple for provider compatibility.
        # The handler performs the real nested validation and normalization.
        # Fire a Claude Code-style notification so plugins can react when the
        # agent is awaiting user input.
        try:
            from code_puppy.callbacks import on_notification

            _coro = on_notification(
                "Agent is waiting for user input",
                level="prompt",
                context={"questions": questions},
            )
            try:
                asyncio.get_running_loop()
                asyncio.ensure_future(_coro)
            except RuntimeError:
                asyncio.run(_coro)
        except Exception:
            pass
        return _resolve_tool_result(_ask_user_question_impl(questions))
