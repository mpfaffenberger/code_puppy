"""Seam-contract tests for the ``RoundRobinRequests`` capability.

Direct ``wrap_model_request`` drives: leaf routing, copy isolation, guest
pass-through, the eager ``prepare_request`` merge, span-attr fix-up custody,
error propagation, spec-constructibility opt-out, and the conditional splice
helper. End-to-end ``Agent`` runs and construction-site wiring live in
``test_round_robin_capability_runs.py``.
"""

from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents._round_robin import (
    RoundRobinRequests,
    build_round_robin_requests,
)
from code_puppy.round_robin_model import RoundRobinModel
from tests.agents.round_robin_capability_harness import (
    make_leaf,
    passthrough_handler,
    request_context,
)


async def test_routes_requests_to_alternating_leaves():
    hits: dict[str, int] = {}
    leaf_a, leaf_b = make_leaf("a", hits), make_leaf("b", hits)
    rr = RoundRobinModel(leaf_a, leaf_b)
    capability = RoundRobinRequests(rr)

    routed: list = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        routed.append(req_ctx.model)
        return ModelResponse(parts=[TextPart("ok")])

    for _ in range(4):
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=request_context(rr),
            handler=handler,
        )

    assert routed == [leaf_a, leaf_b, leaf_a, leaf_b]


async def test_original_context_is_not_mutated():
    rr = RoundRobinModel(make_leaf("a", {}), make_leaf("b", {}))
    capability = RoundRobinRequests(rr)
    original = request_context(rr)
    original_messages = original.messages

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=original, handler=handler
    )

    assert original.model is rr
    assert original.messages is original_messages
    assert received[0] is not original
    assert received[0].messages is original_messages  # shallow copy, #830 shape


async def test_guest_context_passes_through_untouched():
    """A context carrying any other model must pass through identically —
    that request's rotation (if any) belongs to the outer model's own
    ``request`` path."""
    rr = RoundRobinModel(make_leaf("a", {}), make_leaf("b", {}))
    capability = RoundRobinRequests(rr)
    other = make_leaf("other", {})
    ctx = request_context(other)

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=ctx, handler=handler
    )

    assert received[0] is ctx  # identical object — no copy, no swap
    # Rotation untouched: the next owned request still starts at leaf "a".
    assert rr.next_model().model_name == "a"


async def test_prepare_request_merge_mirrors_eager_path():
    """The routed context must carry exactly what ``RoundRobinModel.request``
    would have handed the leaf: ``leaf.prepare_request(settings, params)``."""
    hits: dict[str, int] = {}
    leaf = FunctionModel(
        lambda m, i: ModelResponse(parts=[TextPart("ok")]),
        model_name="leaf",
        settings={"temperature": 0.5},
    )
    rr = RoundRobinModel(leaf, make_leaf("b", hits))
    capability = RoundRobinRequests(rr)

    ctx = request_context(rr)
    ctx.model_settings = {"max_tokens": 10}
    expected_settings, expected_params = leaf.prepare_request(
        ctx.model_settings, ctx.model_request_parameters
    )

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=ctx, handler=handler
    )

    assert received[0].model_settings == expected_settings
    assert received[0].model_settings["temperature"] == 0.5
    assert received[0].model_settings["max_tokens"] == 10
    assert received[0].model_request_parameters == expected_params


async def test_span_attributes_recorded_for_routed_leaf_only():
    hits: dict[str, int] = {}
    leaf_a, leaf_b = make_leaf("a", hits), make_leaf("b", hits)
    rr = RoundRobinModel(leaf_a, leaf_b)
    capability = RoundRobinRequests(rr)
    recorded: list = []

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=request_context(rr),
            handler=passthrough_handler,
        )
        # Guest pass-through must not record anything.
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=request_context(make_leaf("other", {})),
            handler=passthrough_handler,
        )

    assert recorded == [leaf_a]


async def test_handler_error_propagates_after_rotation_without_span_record():
    """Eager parity: rotation advances before the request; a failed request
    neither rolls the rotation back nor records span attributes."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    capability = RoundRobinRequests(rr)
    recorded: list = []

    async def broken_handler(req_ctx: ModelRequestContext) -> ModelResponse:
        raise RuntimeError("provider exploded")

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        try:
            await capability.wrap_model_request(
                SimpleNamespace(),
                request_context=request_context(rr),
                handler=broken_handler,
            )
        except RuntimeError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError("handler error must propagate")

    assert recorded == []
    # Rotation already advanced past leaf "a" — next owned request gets "b".
    assert rr.next_model().model_name == "b"


def test_not_spec_constructible():
    # Live Model reference (provider HTTP clients) — #833 precedent.
    assert RoundRobinRequests.get_serialization_name() is None


def test_build_round_robin_requests_conditional_splice():
    rr = RoundRobinModel(make_leaf("a", {}))
    caps = build_round_robin_requests(rr)
    assert len(caps) == 1 and caps[0].model is rr
    assert build_round_robin_requests(make_leaf("plain", {})) == []
