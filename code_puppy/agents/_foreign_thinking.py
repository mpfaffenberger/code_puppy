"""Keep other providers' reasoning out of Anthropic requests.

pydantic-ai replays a ``ThinkingPart`` from any other provider (or one with no
signature) to Anthropic as ``<thinking>`` text inside a prior assistant turn.
Anthropic reads that as an attempt to extract or duplicate model reasoning and
refuses the request (``refusal_category: reasoning_extraction``), which breaks
switching to a Claude model mid-session, e.g. a cross-model final review.

Only the outbound request is filtered; stored history keeps every part, so a
switch back to the original provider still sees its own reasoning. Restricted
to Anthropic because other adapters (including Code Puppy's Gemini model,
which labels parts with the model name) rely on their own thinking replay.
"""

from __future__ import annotations

import dataclasses

from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.wrapper import WrapperModel


def _is_anthropic(model: Model) -> bool:
    while isinstance(model, WrapperModel):
        model = model.wrapped
    return isinstance(model, AnthropicModel)


def strip_foreign_thinking(
    messages: list[ModelMessage], model: Model
) -> list[ModelMessage]:
    """Return ``messages`` without reasoning Anthropic cannot natively replay.

    Called by: _model_message_transform :: build_model_message_transform().
    """
    if not _is_anthropic(model):
        return messages

    def foreign(part: object) -> bool:
        return isinstance(part, ThinkingPart) and not (
            part.provider_name == model.system and part.signature
        )

    cleaned: list[ModelMessage] = []
    for message in messages:
        if isinstance(message, ModelResponse) and any(map(foreign, message.parts)):
            parts = [part for part in message.parts if not foreign(part)]
            if not parts:
                continue
            message = dataclasses.replace(message, parts=parts)
        cleaned.append(message)
    return cleaned
