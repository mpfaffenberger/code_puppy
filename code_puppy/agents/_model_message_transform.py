"""Plugin transforms for final outbound model messages.

``PluginMessageTransform`` is the capability behind the
``transform_model_messages`` plugin hook: it hands plugins the final
outbound message list -- after compaction, steering, and clamping have
run -- immediately before the model call.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import ModelRequestContext

from code_puppy.callbacks import on_transform_model_messages


@dataclass
class PluginMessageTransform(AbstractCapability[Any]):
    """Run ``transform_model_messages`` plugin callbacks on each model request.

    Overrides :meth:`wrap_model_request` -- the same seam the previous
    ``Hooks(model_request=...)`` adapter registered on -- so its position in
    the ``capabilities=[...]`` list keeps the established ordering: history
    processors and the response clamp run first, then this transform wraps
    the final wire request.

    **Request-only by construction.** The request context is shallow-copied
    and its message list materialized fresh, so plugin *list* mutations
    (append/insert/remove/replace) reach the model for exactly one request
    without leaking into the durable history (``result.all_messages()``
    never shows them). The contained message objects are still shared --
    mutating an existing message in place would leak, exactly as it did
    under the previous ``Hooks`` adapter. Callback failures are
    already isolated inside the ``on_transform_model_messages`` fan-out --
    a crashing plugin never takes down the request.
    """

    agent_name: str | None
    """Logical agent name forwarded to each callback (``None`` when unknown)."""

    async def wrap_model_request(
        self,
        ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        """Copy the context, let plugins mutate the copy, call the model."""
        transformed_context = copy(request_context)
        transformed_context.messages = list(request_context.messages)
        await on_transform_model_messages(self.agent_name, transformed_context.messages)
        return await handler(transformed_context)
