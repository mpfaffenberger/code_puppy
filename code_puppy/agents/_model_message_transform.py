"""Plugin transforms for final outbound model messages."""

from copy import copy
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Hooks, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.models.wrapper import WrapperModel

from code_puppy.agents._foreign_thinking import strip_foreign_thinking
from code_puppy.callbacks import on_transform_model_messages

# Per-request prefix fingerprint, handed from the ``wrap_model_request`` leg
# to the ``after_model_request`` leg via this attribute on the (mutable,
# per-request) ``ModelRequestContext``. ``None`` means "this request's
# outbound messages diverged from the durable history it was built from, so
# don't stamp an anchor" -- see ``build_model_message_transform``.
_PREFIX_ATTR = "_context_accounting_prefix"


class _ContinuationObserver(WrapperModel):
    """Observe a suspended->continued chain *before* pydantic-ai merges it.

    ``continuation_delay`` runs on intermediate suspended responses before
    their usage can merge. This request-local wrapper preserves the real
    model's delay behavior while marking the final response ineligible for
    a receipt. The framework's durable-execution capabilities use the same
    request-model swap seam. Provider details and billing limitations live
    in ``docs/API_CONTEXT_ACCOUNTING.md``.
    """

    def __init__(self, wrapped):
        super().__init__(wrapped)
        self.continued = False

    def continuation_delay(self, response: ModelResponse) -> float | None:
        self.continued = True
        return super().continuation_delay(response)


def build_model_message_transform(agent_name: str | None, owner: Any = None) -> Hooks:
    """Build the request-only plugin transform for an agent.

    ``owner`` is the Code Puppy agent (or agent-shaped object) whose
    ``_context_overhead`` compaction just computed for this same request --
    see ``CodePuppyCompactionStore.context_overhead``. Passing it lets the
    stamped receipt record the *exact* overhead the compaction trigger used,
    so the next request's ``context_tokens`` call reconstructs the same
    total instead of silently drifting by whatever overhead changed between
    the two reads. ``None`` (sub-agents/tests that don't wire one) just
    stamps ``overhead=0``, which only costs an extra estimate on that one
    anchor -- never a wrong total, because ``context_tokens`` always folds
    the caller's *current* overhead back in.
    """

    async def transform(
        _ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        from code_puppy.context_accounting import fingerprint, invalidate_anchors

        durable_messages = request_context.messages
        # Snapshot *before* anything can touch the messages. strip_foreign_thinking
        # is a no-op pass-through for non-Anthropic models (same list AND same
        # message objects by reference, not a copy) -- so a plugin transform
        # that mutates in place would otherwise mutate ``durable_messages`` too,
        # and a fingerprint taken afterwards would never see the divergence.
        original_fingerprint = fingerprint(durable_messages)

        transformed_context = copy(request_context)
        transformed_context.messages = strip_foreign_thinking(
            list(durable_messages), request_context.model
        )
        await on_transform_model_messages(agent_name, transformed_context.messages)

        # The anchor must describe what the *durable history* looked like,
        # because that's what next turn's ``context_tokens`` re-fingerprints
        # against. If anything between the snapshot above and the handler
        # call -- the built-in foreign-thinking strip, or a plugin's rewrite,
        # in place or not -- changed what's actually sent, the response's
        # usage no longer describes ``durable_messages`` and must not anchor it.
        prefix = original_fingerprint
        if fingerprint(transformed_context.messages) != prefix:
            prefix = None

        # Wrap *after* the fingerprint check above (which needs the real
        # model for foreign-thinking detection) and *before* the handler
        # call, so the continuation loop inside `handler` actually drives
        # this wrapper's `continuation_delay` -- see `_ContinuationObserver`.
        observer = _ContinuationObserver(transformed_context.model)
        transformed_context.model = observer

        try:
            response = await handler(transformed_context)
        except BaseException:
            invalidate_anchors(durable_messages)
            raise

        if observer.continued:
            # Usage on `response` is a cumulative sum across segments, not
            # one measured prompt -- decline to anchor it. Billing/usage
            # itself is untouched; only our own receipt is suppressed.
            prefix = None
        setattr(request_context, _PREFIX_ATTR, prefix)
        return response

    async def stamp(
        _ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        from code_puppy.context_accounting import model_names, record_anchor

        prefix = getattr(request_context, _PREFIX_ATTR, None)
        if prefix is not None:
            record_anchor(
                request_context.messages,
                response,
                context_overhead=getattr(owner, "_context_overhead", 0),
                prefix=prefix,
                request_model=model_names(request_context.model),
            )
        return response

    return Hooks(model_request=transform, after_model_request=stamp)
