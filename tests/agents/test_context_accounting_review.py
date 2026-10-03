"""Review regressions for dynamic overhead and production receipt wiring."""

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from code_puppy import token_usage
from code_puppy.agents import _compaction
from code_puppy.agents._model_message_transform import build_model_message_transform
from code_puppy.context_accounting import context_tokens, record_anchor
from code_puppy.round_robin_model import RoundRobinModel


def history():
    prefix = [ModelRequest(parts=[UserPromptPart("hello")])]
    response = ModelResponse(
        parts=[TextPart("reply")],
        model_name="model",
        usage=RequestUsage(input_tokens=160000, output_tokens=10),
    )
    record_anchor(prefix, response, context_overhead=50)
    return [*prefix, response]


def _owner(**extra):
    base = dict(
        _message_history=[],
        _compacted_message_hashes=set(),
        _get_model_context_length=lambda: 200000,
        _estimate_context_overhead=lambda: 0,
        name="test",
    )
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("overhead", [51, 1000, 25])
def test_dynamic_overhead_adjusts_anchor_instead_of_discarding(overhead):
    assert context_tokens(history(), "model", overhead) == 160010 + overhead - 50


def test_shared_entry_point_imports_in_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "import code_puppy.context_accounting"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_nonzero_processor_overhead_is_recorded_and_reused():
    overhead = Mock(return_value=123)
    owner = _owner(_estimate_context_overhead=overhead)
    model = FunctionModel(
        lambda messages, info: ModelResponse(
            parts=[TextPart("ok")],
            usage=RequestUsage(input_tokens=160000, output_tokens=10),
        ),
        model_name="model",
    )
    agent = Agent(
        model,
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )
    messages = (await agent.run("hello")).all_messages()
    assert messages[-1].metadata["context_anchor"]["overhead"] == 123
    assert context_tokens(messages, "model", 124) == 160011
    assert overhead.call_count == 1

    overhead.return_value = 124
    result2 = await agent.run("next turn", message_history=messages)
    assert overhead.call_count == 2
    # The follow-up turn's own stamped overhead reflects the new value. Its
    # response isn't merged into ``owner._message_history`` until a *third*
    # request's before_model_request would run -- which never happens here
    # -- so check the run result's own message list instead.
    final_response = result2.all_messages()[-1]
    assert final_response.metadata["context_anchor"]["overhead"] == 124


async def test_round_robin_response_is_valid_for_current_model():
    from code_puppy.context_accounting import active_model_name

    model = FunctionModel(
        lambda messages, info: ModelResponse(
            parts=[TextPart("ok")],
            usage=RequestUsage(input_tokens=150000, output_tokens=10),
        ),
        model_name="model",
    )
    rotating = RoundRobinModel(model, TestModel(model_name="other"))
    owner = SimpleNamespace(cur_model=rotating, get_model_name=lambda: "config-alias")
    messages = history()
    assert context_tokens(messages, active_model_name(owner), 50) == 160010


def test_model_switch_status_uses_shared_counter():
    from code_puppy.model_switching import _refresh_context_status

    owner = SimpleNamespace(
        cur_model=TestModel(model_name="model"),
        get_model_name=lambda: "alias",
        get_message_history=history,
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
        estimate_tokens_for_message=lambda msg: 1,
    )
    with (
        patch(
            "code_puppy.messaging.spinner.format_context_info",
            side_effect=lambda total, *args: str(total),
        ),
        patch("code_puppy.messaging.spinner.update_spinner_context") as update,
    ):
        _refresh_context_status(owner)
    update.assert_called_once_with("160010")


def test_breakdown_preserves_bucket_sum_and_shared_total(monkeypatch):
    from code_puppy.agents import agent_manager

    owner = SimpleNamespace(
        cur_model=TestModel(model_name="model"),
        get_model_name=lambda: "alias",
        get_message_history=history,
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
    )
    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: owner)
    monkeypatch.setattr(
        token_usage,
        "compute_overhead_breakdown",
        lambda agent: token_usage.OverheadBreakdown(10, 20, 30, 40),
    )
    usage = token_usage.get_current_usage()
    assert usage.overhead_tokens == 100
    assert usage.total_tokens == 160010


async def test_real_round_robin_agent_retains_anchor_between_steps():
    from pydantic_ai.messages import ToolCallPart

    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        parts = [ToolCallPart("ping", {}, "id")] if calls == 1 else [TextPart("done")]
        return ModelResponse(
            parts=parts, usage=RequestUsage(input_tokens=150000, output_tokens=10)
        )

    rotating = RoundRobinModel(
        FunctionModel(respond, model_name="a"), FunctionModel(respond, model_name="b")
    )
    owner = _owner(_estimate_context_overhead=lambda: 123)
    agent = Agent(
        rotating,
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
    assert tool_call_response.metadata["context_anchor"]
    # The final "done" response is from whichever candidate ran second and
    # isn't merged into ``owner._message_history`` within this same run (the
    # merge happens at the *next* request's before_model_request, same as
    # the tool-call step above) -- so validate against the candidate
    # identity set a compaction trigger would actually see mid-run.
    from code_puppy.context_accounting import model_names

    # Confirms the anchor is actually used (API usage dominates the total)
    # rather than a silent fallback to a tens-of-tokens chars/2.5 estimate.
    # Not pinned to an exact figure: passing overhead=0 here while the
    # stamped receipt recorded overhead=123 nets a small negative delta.
    assert context_tokens(owner._message_history, model_names(rotating), 0) > 100000


async def test_in_place_transform_does_not_get_identity_shortcut():
    from code_puppy import callbacks

    def rewrite(name, messages):
        messages[-1].parts[-1].content = "rewritten in place"

    callbacks.register_callback("transform_model_messages", rewrite)
    agent = Agent(
        FunctionModel(
            lambda messages, info: ModelResponse(
                parts=[TextPart("ok")],
                usage=RequestUsage(input_tokens=1000, output_tokens=10),
            ),
            model_name="model",
        ),
        capabilities=[build_model_message_transform("test")],
    )
    messages = (await agent.run("hello")).all_messages()
    assert not (messages[-1].metadata or {}).get("context_anchor")
