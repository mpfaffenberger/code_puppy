"""API anchors must never survive changes to the prompt they measured."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RequestUsage, RunUsage

from code_puppy.agents import _compaction
from code_puppy.agents._history import estimate_tokens_for_message
from code_puppy.agents._model_message_transform import build_model_message_transform


def request(text="hello"):
    return ModelRequest(parts=[UserPromptPart(text)])


def anchor_history(input_tokens=180000, output_tokens=100):
    from code_puppy.context_accounting import record_anchor

    prefix = [request("old prompt")]
    response = ModelResponse(
        parts=[TextPart("answer")],
        model_name="actual-model",
        usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )
    record_anchor(prefix, response, context_overhead=50)
    return [*prefix, response, request("next")]


def count(messages, model="actual-model", overhead=50):
    from code_puppy.context_accounting import context_tokens

    return context_tokens(messages, model, overhead)


def classic(messages, overhead=50):
    return (
        sum(estimate_tokens_for_message(m, "actual-model") for m in messages) + overhead
    )


def _owner(**extra):
    """A minimal agent-shaped owner for the ``HistoryCompaction`` capability."""
    base = dict(
        _message_history=[],
        _compacted_message_hashes=set(),
        _get_model_context_length=lambda: 200000,
        _estimate_context_overhead=lambda: 0,
        name="test",
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_valid_anchor_only_estimates_delta():
    history = anchor_history()
    with patch(
        "code_puppy.context_accounting.estimate_tokens_for_message", return_value=7
    ) as estimate:
        assert count(history) == 180107
    assert estimate.call_count == 1
    assert estimate.call_args.args[0] is history[-1]


@pytest.mark.parametrize(
    "change", ["truncate", "prune", "arguments", "response", "switch"]
)
def test_rewrites_and_model_switch_fall_back(change):
    history = anchor_history()
    model, overhead = "actual-model", 50
    if change == "truncate":
        history = history[1:]
    elif change == "prune":
        history[0].parts.append(UserPromptPart("changed"))
    elif change == "arguments":
        history.insert(
            0,
            ModelResponse(parts=[ToolCallPart("tool", {"argument": "changed"}, "id")]),
        )
    elif change == "response":
        history[1].parts[0].content = "clamped"
    else:
        model = "new-model"
    assert count(history, model, overhead) == classic(history, overhead)


@pytest.mark.parametrize("usage", [None, 0])
def test_missing_zero_or_legacy_usage_falls_back(usage):
    history = anchor_history()
    history[1].usage.input_tokens = usage or 0
    assert count(history) == classic(history)
    history[1].usage.input_tokens = 180000
    history[1].metadata = None
    assert count(history) == classic(history)


def test_first_request_and_session_round_trip():
    assert count([request()]) == classic([request()])
    history = anchor_history()
    loaded = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(history)
    )
    assert count(loaded) == count(history)
    loaded[0].parts[0].content = "rewritten on resume"
    assert count(loaded) == classic(loaded)


def test_thinking_uses_estimate_not_generated_hidden_tokens():
    from code_puppy.context_accounting import record_anchor

    prefix = [request()]
    response = ModelResponse(
        parts=[ThinkingPart("visible", signature="signed"), TextPart("answer")],
        model_name="actual-model",
        usage=RequestUsage(input_tokens=1000, output_tokens=50000),
    )
    record_anchor(prefix, response, context_overhead=50)
    history = [*prefix, response]
    assert count(history) == 1000 + estimate_tokens_for_message(
        response, "actual-model"
    )


async def test_no_repeated_compaction_with_verbatim_stale_tail():
    history = anchor_history()
    owner = _owner(get_model_name=lambda: "actual-model")
    ctx = RunContext(
        deps=None,
        model=TestModel(model_name="actual-model"),
        usage=RunUsage(),
        prompt="",
        messages=history,
    )
    strategy = SimpleNamespace(compact=AsyncMock(return_value=history[1:]))
    with (
        patch.object(_compaction, "build_compaction_strategy", return_value=strategy),
        patch.object(_compaction, "get_compaction_threshold", return_value=0.85),
    ):
        compacted, _ = await _compaction.compact(owner, history, 200000, 50, ctx)
        assert strategy.compact.await_count == 1
        assert compacted[0] is history[1]  # retained API usage, not a sanitized fake
        again, dropped = await _compaction.compact(owner, compacted, 200000, 50, ctx)
        assert again == compacted and dropped == []
        assert strategy.compact.await_count == 1


@pytest.mark.parametrize("streaming", [False, True])
async def test_completed_real_agent_records_usage_at_request_boundary(streaming):
    def model(messages, info):
        return ModelResponse(
            parts=[TextPart("ok")],
            usage=RequestUsage(input_tokens=1234, output_tokens=9),
        )

    async def stream(messages, info):
        yield "ok"

    model = FunctionModel(model, stream_function=stream, model_name="actual-model")
    agent = Agent(model, capabilities=[build_model_message_transform("test")])
    if streaming:

        async def consume(ctx, events):
            async for event in events:
                pass

        history = (
            await agent.run("hello", event_stream_handler=consume)
        ).all_messages()
    else:
        history = (await agent.run("hello")).all_messages()
    assert history[-1].usage.input_tokens > 0
    assert count(history, overhead=0) >= history[-1].usage.input_tokens
    assert history[-1].metadata and "context_anchor" in history[-1].metadata


@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_or_cancelled_request_invalidates_previous_anchor(cancelled):
    history = anchor_history()
    hooks = build_model_message_transform("test")
    from pydantic_ai.models import ModelRequestContext, ModelRequestParameters

    context = ModelRequestContext(
        model=TestModel(),
        messages=history,
        model_settings={},
        model_request_parameters=ModelRequestParameters(),
    )

    async def failing(context):
        if cancelled:
            raise asyncio.CancelledError()
        raise RuntimeError("failed")

    with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
        await hooks.wrap_model_request(None, request_context=context, handler=failing)
    assert count(history) == classic(history)


def test_status_bar_and_compaction_share_total(monkeypatch):
    from code_puppy import token_usage
    from code_puppy.agents import agent_manager

    history = anchor_history()
    owner = SimpleNamespace(
        get_message_history=lambda: history,
        get_model_name=lambda: "alias",
        cur_model=TestModel(model_name="actual-model"),
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
    )
    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: owner)
    monkeypatch.setattr(
        token_usage,
        "compute_overhead_breakdown",
        lambda agent: token_usage.OverheadBreakdown(10, 20, 20, 0),
    )
    usage = token_usage.get_current_usage()
    assert usage.total_tokens == count(history)
    assert usage.total_tokens > 170000


def test_incomplete_response_never_anchors():
    history = anchor_history()
    history[1].state = "interrupted"
    assert count(history) == classic(history)


async def test_second_model_step_compaction_sees_completed_usage():
    """By the 2nd model step, the 1st response's usage has already anchored.

    ``after_model_request`` stamps the anchor before the graph loops back
    for the tool-call follow-up request, so the durable history the second
    ``before_model_request`` measures already carries a trustworthy receipt.
    """
    owner = _owner()

    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[ToolCallPart("ping", {}, "id")],
                usage=RequestUsage(input_tokens=12345, output_tokens=10),
            )
        return ModelResponse(
            parts=[TextPart("done")],
            usage=RequestUsage(input_tokens=12400, output_tokens=5),
        )

    agent = Agent(
        FunctionModel(model, model_name="actual-model"),
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )

    @agent.tool_plain
    def ping() -> str:
        return "pong"

    await agent.run("hello")
    tool_call_response = next(
        m
        for m in owner._message_history
        if isinstance(m, ModelResponse)
        and any(isinstance(p, ToolCallPart) for p in m.parts)
    )
    assert tool_call_response.usage.input_tokens == 12345
    assert tool_call_response.metadata["context_anchor"]
    assert count(owner._message_history, overhead=0) > 12345


def test_installed_retired_plugin_cannot_patch_estimators(monkeypatch, caplog):
    from code_puppy import plugins
    from unittest.mock import Mock

    entry = SimpleNamespace(name="token_ratio_learner", load=Mock())
    monkeypatch.setattr(plugins, "entry_points", lambda **kwargs: [entry])
    with caplog.at_level("DEBUG", logger="code_puppy.plugins"):
        assert plugins._load_installed_plugins() == []
    entry.load.assert_not_called()
    assert "Skipping retired plugin token_ratio_learner" in caplog.text


def test_argument_and_signature_changes_in_measured_prefix_invalidate():
    from code_puppy.context_accounting import record_anchor

    prefix = [
        request(),
        ModelResponse(
            parts=[
                ToolCallPart("tool", {"large": "a"}, "id"),
                ThinkingPart("thought", signature="sig"),
            ]
        ),
    ]
    response = ModelResponse(
        parts=[TextPart("ok")],
        model_name="actual-model",
        usage=RequestUsage(input_tokens=12345, output_tokens=5),
    )
    record_anchor(prefix, response, context_overhead=50)
    history = [*prefix, response]
    assert count(history) == 12350
    prefix[1].parts[0].args = {"large": "b"}
    assert count(history) == classic(history)
    prefix[1].parts[0].args = {"large": "a"}
    prefix[1].parts[1].signature = "rewritten"
    assert count(history) == classic(history)


async def test_request_only_transform_cannot_claim_persisted_prompt():
    from code_puppy import callbacks

    def transform(name, messages):
        messages.append(request("request-only"))

    callbacks.register_callback("transform_model_messages", transform)
    agent = Agent(
        TestModel(model_name="actual-model"),
        capabilities=[build_model_message_transform("test")],
    )
    history = (await agent.run("hello")).all_messages()
    assert not (history[-1].metadata or {}).get("context_anchor")
    assert count(history, overhead=0) == classic(history, overhead=0)


def test_real_session_storage_revalidates_receipt(tmp_path):
    from code_puppy.session_storage import save_session, load_session

    history = anchor_history()
    save_session(
        history=history,
        session_name="anchor",
        base_dir=tmp_path,
        timestamp="now",
        token_estimator=lambda message: 1,
    )
    loaded = load_session("anchor", tmp_path)
    assert count(loaded) == count(history)
    loaded.pop(0)
    assert count(loaded) == classic(loaded)


@pytest.mark.parametrize("input_tokens,compacts", [(169000, False), (171000, True)])
async def test_real_prompt_threshold_brackets_170k(input_tokens, compacts):
    history = anchor_history(input_tokens=input_tokens)
    ctx = RunContext(
        deps=None,
        model=TestModel(model_name="actual-model"),
        usage=RunUsage(),
        prompt="",
        messages=history,
    )
    strategy = SimpleNamespace(compact=AsyncMock(return_value=[request("summary")]))
    with (
        patch.object(_compaction, "build_compaction_strategy", return_value=strategy),
        patch.object(_compaction, "get_compaction_threshold", return_value=0.85),
    ):
        await _compaction.compact(None, history, 200000, 50, ctx)
    assert bool(strategy.compact.await_count) == compacts


def test_anthropic_normalized_cache_usage_not_double_counted():
    usage = RequestUsage.extract(
        {
            "model": "claude-sonnet-4-5",
            "usage": {
                "input_tokens": 10000,
                "output_tokens": 100,
                "cache_creation_input_tokens": 20000,
                "cache_read_input_tokens": 200000,
            },
        },
        provider="anthropic",
        provider_url="https://api.anthropic.com",
        provider_fallback="anthropic",
    )
    assert usage.input_tokens == 230000
    history = anchor_history(input_tokens=usage.input_tokens)
    assert count(history) == 230100 + estimate_tokens_for_message(
        history[-1], "actual-model"
    )
