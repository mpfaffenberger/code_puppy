"""Round-robin request routing as a pydantic-ai capability.

Promotes the per-request model rotation that ``RoundRobinModel`` performs
inside its ``request``/``request_stream`` methods onto pydantic-ai 2.31.0's
``wrap_model_request`` capability seam. The seam is the natural home for the
feature: rotation is a per-model-request routing decision, and the seam hands
every request (streamed and non-streamed alike) a mutable
``ModelRequestContext`` whose ``model`` field the terminal handler honours —
upstream's own durable-execution capabilities swap ``request_context.model``
at exactly this seam.

Custody split (explicit-when-ours, fallback-for-guests):

* **Capability-owned requests** — when the request's model is the exact
  ``RoundRobinModel`` instance this capability was built around, the
  capability advances the rotation, mirrors the eager leaf-side
  ``prepare_request`` merge, and routes the request straight to the selected
  leaf model. ``RoundRobinModel.request``/``request_stream`` never run.
* **Guest requests** — anything else passes through untouched: an explicit
  ``run(model=...)``/``override(model=...)`` model, or the round-robin model
  re-wrapped by an arbitrary ``WrapperModel``. In the wrapped case the outer
  model's own ``request`` still reaches ``RoundRobinModel.request``, which
  rotates eagerly exactly as before — the ``Model`` subclass stays intact as
  the guest fallback, and both paths share one rotation state
  (``RoundRobinModel.next_model``), so every pydantic-ai model request
  advances the rotation exactly once no matter which path serves it. (Guest
  custody additionally rotates per *continuation segment* within one wrapped
  request — the pre-conversion behaviour; see the continuation divergence
  below.) Note instrumentation is NOT a guest: pydantic-ai 2.31.0 installs
  it as a capability and unwraps explicit ``InstrumentedModel``s before the
  run, so instrumented requests still carry the bare round-robin model and
  take the owned path.

Bounded divergences on the capability-owned path (documented, pinned by
tests where observable):

* ``_ensure_model_supports_streaming`` now checks the routed **leaf** for
  streamed requests rather than the wrapper — strictly more precise, and
  vacuous for real provider leaves (they all stream).
* **Continuation segments stay pinned to the leaf that opened the chain.**
  ``model_request``/``model_request_stream`` resolve suspended → complete
  continuations (Anthropic ``pause_turn``, OpenAI background polls) by
  re-invoking ``req_ctx.model`` inside ONE wrapped request. Eagerly the
  terminal model was the round-robin wrapper, so every segment rotated —
  which could stitch one merged response from two different models, and
  would re-poll a *different* provider for a suspended job id. Owned
  requests advance the rotation once and serve the whole chain from the
  selected leaf: a deliberate divergence, strictly saner than the eager
  behaviour (which survives unchanged on the guest path). Pinned both ways
  by the continuation tests.
* Span-attribute fix-up on streamed requests moves from stream-open to
  handler-return, which parks until the stream is fully drained — a
  mid-stream cancel/teardown therefore records nothing where the eager path
  had already recorded at open. This is reachable in shipped configurations:
  ``observability.py`` calls ``logfire.instrument_pydantic_ai()``, and 2.31.0
  instrumentation is capability-based (explicit ``InstrumentedModel``s are
  unwrapped before the run), so instrumented requests take the owned path.
  Scope of the loss: only the leaf-attribute refinement on the chat span —
  the span itself, its round-robin ``gen_ai.request.model``, and the eager
  fallback for completed streams are unaffected. Non-streamed timing is
  unchanged (after the response). Pinned by the teardown tests.
* ``ModelRequestContext.model_id`` is only meaningful while the context still
  carries the run's resolved model; swapping the model invalidates it for
  durable-execution capabilities (upstream-documented semantics of any
  model-swapping hook, including upstream's own).
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model, ModelRequestContext

from code_puppy.round_robin_model import RoundRobinModel

__all__ = ["RoundRobinRequests", "build_round_robin_requests"]


@dataclass
class RoundRobinRequests(AbstractCapability[Any]):
    """Route each model request to the next leaf of a ``RoundRobinModel``.

    One instance per built agent, wrapping that agent's resolved
    ``RoundRobinModel``. Stateless beyond the model reference — rotation
    state lives on the model itself so capability-owned and guest requests
    share one sequence.
    """

    model: RoundRobinModel

    @classmethod
    def get_serialization_name(cls) -> str | None:
        # Holds a live Model instance (provider HTTP clients) — not
        # spec-constructible.
        return None

    async def wrap_model_request(
        self,
        ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        if request_context.model is not self.model:
            # Guest custody: an explicit run/override model, or our model
            # re-wrapped (e.g. InstrumentedModel). The outer model's own
            # request path performs the eager rotation when applicable.
            return await handler(request_context)

        leaf = self.model.next_model()
        # Mirror the eager path byte-for-byte: RoundRobinModel.request calls
        # ``leaf.prepare_request`` before handing off, merging the leaf's own
        # default settings under the run's settings and letting the leaf
        # customize the request parameters. The leaf re-prepares internally
        # on ``request()`` exactly as it did when called by RoundRobinModel.
        merged_settings, prepared_params = leaf.prepare_request(
            request_context.model_settings,
            request_context.model_request_parameters,
        )
        routed_context = copy(request_context)
        routed_context.model = leaf
        routed_context.model_settings = merged_settings
        routed_context.model_request_parameters = prepared_params

        response = await handler(routed_context)
        self.model.record_span_attributes(leaf)
        return response


def build_round_robin_requests(model: Model) -> list[RoundRobinRequests]:
    """Conditionally splice a ``RoundRobinRequests`` into a capabilities list.

    Returns ``[RoundRobinRequests(model)]`` when ``model`` is a
    ``RoundRobinModel``, else ``[]`` — the same conditional-splice shape as
    ``build_tool_output_limits`` so non-round-robin agents carry no inert
    capability.
    """
    if isinstance(model, RoundRobinModel):
        return [RoundRobinRequests(model)]
    return []
