"""Plugin transforms for final outbound model messages."""

from copy import copy
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Hooks, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import ModelRequestContext

from code_puppy.callbacks import on_transform_model_messages


def build_model_message_transform(agent_name: str | None) -> Hooks:
    """Build the request-only plugin transform for an agent."""

    async def transform(
        _ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        transformed_context = copy(request_context)
        transformed_context.messages = list(request_context.messages)
        await on_transform_model_messages(agent_name, transformed_context.messages)
        return await handler(transformed_context)

    return Hooks(model_request=transform)
