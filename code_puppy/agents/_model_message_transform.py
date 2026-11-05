"""Plugin transforms for final outbound model messages."""

from dataclasses import replace
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import (
    CapabilityOrdering,
    Hooks,
    WrapModelRequestHandler,
)
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.models.wrapper import WrapperModel

from code_puppy.agents._foreign_thinking import strip_foreign_thinking
from code_puppy.callbacks import on_transform_model_messages


class _ContinuationObserver(WrapperModel):
    """Observe a suspended->continued chain *before* pydantic-ai merges it.

    ``continuation_delay`` runs on intermediate suspended responses before
    their usage can merge. This request-local wrapper preserves the real
    model's delay behavior while marking the final response ineligible for
    a receipt. The framework's durable-execution capabilities use the same
    request-model swap seam. Provider details and billing limitations live
    in ``docs/API_CONTEXT_ACCOUNTING.md``.

    It also carries this request's accounting state from the
    ``before_model_request`` leg to the ``after_model_request`` leg: the
    durable history the request was built from, and its prefix fingerprint.
    ``prefix`` is ``None`` when the outbound messages diverged from that
    history, so no anchor is stamped. The model object is the one thing every
    later hook and the core hand on unchanged.
    """

    def __init__(
        self,
        wrapped: Model,
        *,
        durable_messages: list[ModelMessage],
        prefix: str | None,
    ):
        super().__init__(wrapped)
        self.continued = False
        self.durable_messages = durable_messages
        self.prefix = prefix

    def continuation_delay(self, response: ModelResponse) -> float | None:
        self.continued = True
        return super().continuation_delay(response)


def build_model_message_transform(agent_name: str | None, owner: Any = None) -> Hooks:
    """Build the request-only plugin transform for an agent.

    The transform runs in ``before_model_request`` as the innermost
    capability, so it sees what the request really sends: the history after
    compaction and every other ``before_model_request`` rewrite.

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

    async def prepare(
        _ctx: RunContext[Any], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        from code_puppy.context_accounting import fingerprint

        durable_messages = list(request_context.messages)
        # Snapshot *before* anything can touch the messages. strip_foreign_thinking
        # is a no-op pass-through for non-Anthropic models (same list AND same
        # message objects by reference, not a copy) -- so a plugin transform
        # that mutates in place would otherwise mutate ``durable_messages`` too,
        # and a fingerprint taken afterwards would never see the divergence.
        original_fingerprint = fingerprint(durable_messages)

        outbound = strip_foreign_thinking(list(durable_messages), request_context.model)
        await on_transform_model_messages(agent_name, outbound)

        # The anchor must describe what the *durable history* looked like,
        # because that's what next turn's ``context_tokens`` re-fingerprints
        # against. If anything between the snapshot above and the model call
        # -- the built-in foreign-thinking strip, or a plugin's rewrite, in
        # place or not -- changed what's actually sent, the response's usage no
        # longer describes ``durable_messages`` and must not anchor it.
        prefix = original_fingerprint
        if fingerprint(outbound) != prefix:
            prefix = None

        # Wrap *after* the fingerprint check above (which needs the real
        # model for foreign-thinking detection), so the continuation loop
        # inside the core drives this wrapper's `continuation_delay`.
        observer = _ContinuationObserver(
            request_context.model, durable_messages=durable_messages, prefix=prefix
        )
        return replace(request_context, messages=outbound, model=observer)

    async def invalidate_on_failure(
        _ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        # ``on_model_request_error`` only sees failures of the core call;
        # failures of other hooks and cancellation reach only a wrapper.
        try:
            return await handler(request_context)
        except BaseException:
            from code_puppy.context_accounting import invalidate_anchors

            observer = request_context.model
            invalidate_anchors(
                observer.durable_messages
                if isinstance(observer, _ContinuationObserver)
                else request_context.messages
            )
            raise

    async def stamp(
        _ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        from code_puppy.context_accounting import model_names, record_anchor

        observer = request_context.model
        if not isinstance(observer, _ContinuationObserver):
            return response
        # Usage on a continued response is a cumulative sum across segments,
        # not one measured prompt -- decline to anchor it. Billing/usage
        # itself is untouched; only our own receipt is suppressed.
        if observer.prefix is not None and not observer.continued:
            record_anchor(
                observer.durable_messages,
                response,
                context_overhead=getattr(owner, "_context_overhead", 0),
                prefix=observer.prefix,
                request_model=model_names(observer.wrapped),
            )
        return response

    return Hooks(
        before_model_request=prepare,
        model_request=invalidate_on_failure,
        after_model_request=stamp,
        ordering=CapabilityOrdering(position="innermost"),
    )
