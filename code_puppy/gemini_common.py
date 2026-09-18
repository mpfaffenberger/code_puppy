"""Shared Gemini wire-format helpers.

Consolidates logic that was previously duplicated and drifted across
`gemini_model.py::GeminiModel` and `gemini_code_assist.py::GeminiCodeAssistModel`.

Wire-format knowledge for the Gemini API should live in exactly one place.
"""

import uuid
from typing import Any

from pydantic_ai import (
    ModelResponsePart,
    ThinkingPart,
    TextPart,
    ToolCallPart,
    RequestUsage,
)
from pydantic_ai.settings import ModelSettings


def generate_tool_call_id() -> str:
    """Generate a unique tool call ID."""
    return str(uuid.uuid4())


def _parse_candidate_parts(
    data: dict[str, Any], candidates: list[dict[str, Any]]
) -> tuple[RequestUsage, list[ModelResponsePart]]:
    """Parse candidate parts from Gemini API response."""
    # Extract usage.
    usage_meta = data.get("usageMetadata", {})
    usage = RequestUsage(
        input_tokens=usage_meta.get("promptTokenCount", 0),
        output_tokens=usage_meta.get("candidatesTokenCount", 0),
    )

    response_parts: list[ModelResponsePart] = []

    if not candidates:
        return usage, response_parts

    candidate = candidates[0]
    content = candidate.get("content", {})
    parts = content.get("parts", [])

    for part in parts:
        if part.get("thought") and part.get("text") is not None:
            # Thinking part.
            signature = part.get("thoughtSignature")
            response_parts.append(
                ThinkingPart(content=part["text"], signature=signature)
            )

        elif "text" in part:
            response_parts.append(TextPart(content=part["text"]))

        elif "functionCall" in part:
            fc = part["functionCall"]

            response_parts.append(
                ToolCallPart(
                    tool_name=fc["name"],
                    args=fc.get("args", {}),
                    tool_call_id=fc.get("id") or generate_tool_call_id(),
                )
            )

    return usage, response_parts


def _build_generation_config(model_settings: ModelSettings | None) -> dict[str, Any]:
    """Build generation config from model settings."""
    config: dict[str, Any] = {}

    if model_settings:
        # ModelSettings is a TypedDict, so use .get() for all access.
        temperature = model_settings.get("temperature")
        if temperature is not None:
            config["temperature"] = temperature

        top_p = model_settings.get("top_p")
        if top_p is not None:
            config["topP"] = top_p

        max_tokens = model_settings.get("max_tokens")
        if max_tokens is not None:
            config["maxOutputTokens"] = max_tokens

        # Handle Gemini 3 Pro thinking settings.
        thinking_enabled = model_settings.get("thinking_enabled")
        thinking_level = model_settings.get("thinking_level")

        # Build `thinkingConfig` if thinking settings are present.
        if thinking_enabled is not False and thinking_level is not None:
            # Gemini 3 Pro uses thinkingLevel with values "low" or "high".
            # `includeThoughts=True` is required to surface the thinking in response.
            config["thinkingConfig"] = {
                "thinkingLevel": thinking_level,
                "includeThoughts": True,
            }

    return config
