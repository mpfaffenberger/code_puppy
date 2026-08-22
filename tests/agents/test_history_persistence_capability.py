"""Contract tests for the ``HistoryPersistence`` capability.

The feature under test: success-path main-conversation history custody —
persisting ``result.all_messages()`` into the owning agent's durable
``_message_history`` — promoted from seven eager call sites onto pydantic-ai's
``after_run`` seam. See ``code_puppy/agents/_history_persistence.py`` for the
migration story.
"""

import inspect
from contextlib import contextmanager
from unittest.mock import patch

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy.agents._history_persistence import (
    HistoryPersistence,
    persist_result_history,
)


class _FakeAgent:
    """BaseAgent-shaped double: history list + the plain public setter."""

    def __init__(self):
        self._message_history = []
        self.setter_calls = 0

    def set_message_history(self, history):
        self.setter_calls += 1
        self._message_history = history


class _BareAgent:
    """Agent double WITHOUT the public setter (runtime-site spelling)."""

    def __init__(self):
        self._message_history = []


class _FakeResult:
    """AgentRunResult-shaped double."""

    def __init__(self, messages):
        self._messages = messages

    def all_messages(self):
        return self._messages


# ---------- direct seam contract ---------------------------------------------


async def test_after_run_persists_all_messages_via_setter():
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    messages = ["m1", "m2", "m3"]
    result = _FakeResult(messages)

    returned = await cap.after_run(None, result=result)

    assert returned is result  # result passes through unchanged
    assert agent._message_history == messages
    # Fresh list copy — mutating the persisted history must not reach back
    # into the result's internal message list.
    assert agent._message_history is not messages
    assert agent.setter_calls == 1
    assert cap.last_result is result


async def test_after_run_uses_direct_assignment_without_setter():
    agent = _BareAgent()
    cap = HistoryPersistence(agent)
    result = _FakeResult(["a", "b"])

    await cap.after_run(None, result=result)

    assert agent._message_history == ["a", "b"]
    assert cap.last_result is result


async def test_after_run_ignores_result_without_all_messages():
    agent = _FakeAgent()
    agent._message_history = ["keep me"]
    cap = HistoryPersistence(agent)
    bare = object()

    returned = await cap.after_run(None, result=bare)

    assert returned is bare
    assert agent._message_history == ["keep me"]
    assert cap.last_result is None


def test_get_serialization_name_is_none():
    # Live agent reference — must never be spec-constructible.
    assert HistoryPersistence(_FakeAgent()).get_serialization_name() is None


# ---------- unconditional writeback helper ------------------------------------


def test_helper_writes_when_no_capability():
    agent = _FakeAgent()
    result = _FakeResult(["m1"])

    assert persist_result_history(agent, result) is True
    assert agent._message_history == ["m1"]
    assert agent.setter_calls == 1


def test_helper_writes_via_direct_assignment_without_setter():
    agent = _BareAgent()
    result = _FakeResult(["m1"])

    assert persist_result_history(agent, result) is True
    assert agent._message_history == ["m1"]


async def test_helper_clobbers_post_run_history_mutations():
    """Exact-parity pin: the demoted sites always rewrote with the completed
    transcript, clobbering anything that mutated durable history after the
    run (e.g. an ``agent_run_end`` plugin). The helper must NOT skip just
    because the capability already persisted this result once."""
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    result = _FakeResult(["m1", "m2"])
    await cap.after_run(None, result=result)

    # A plugin replaces the history between run-end and the turn-end site.
    agent._message_history = ["mutated by plugin"]

    assert persist_result_history(agent, result) is True
    assert agent._message_history == ["m1", "m2"]  # transcript restored


def test_helper_rejects_none_and_messageless_results():
    agent = _FakeAgent()
    agent._message_history = ["keep me"]

    assert persist_result_history(agent, None) is False
    assert persist_result_history(agent, object()) is False
    assert agent._message_history == ["keep me"]
    assert agent.setter_calls == 0


# ---------- real Agent.run() through the seam --------------------------------


async def test_real_run_persists_identical_result_state():
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    pyd_agent = PydanticAgent(
        model=TestModel(custom_output_text="woof"),
        capabilities=[cap],
    )

    result = await pyd_agent.run("hello")

    # after_run saw the exact result object the caller received...
    assert cap.last_result is result
    # ...and persisted exactly its full transcript.
    assert agent._message_history == list(result.all_messages())


async def test_real_multi_step_run_persists_final_transcript():
    """Tool-calling run: the persisted history must include the tool cycle
    AND the trailing final response no before_model_request hook ever sees."""
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    calls = {"n": 0}

    def model_func(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="fetch", args={}, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    pyd_agent = PydanticAgent(model=FunctionModel(model_func), capabilities=[cap])

    @pyd_agent.tool_plain
    def fetch() -> str:
        return "kibble"

    result = await pyd_agent.run("go")

    assert agent._message_history == list(result.all_messages())
    final = agent._message_history[-1]
    assert isinstance(final, ModelResponse)
    assert final.parts[0].content == "done"


async def test_real_run_composes_with_other_capabilities():
    """The persist must survive CombinedCapability composition."""
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    pyd_agent = PydanticAgent(
        model=TestModel(custom_output_text="woof"),
        # A vanilla no-hook capability on either side forces composition.
        capabilities=[AbstractCapability(), cap, AbstractCapability()],
    )

    result = await pyd_agent.run("hello")

    assert cap.last_result is result
    assert agent._message_history == list(result.all_messages())


async def test_followup_seeding_matches_eager_baseline():
    """A follow-up run seeded from the capability-persisted history must feed
    the model exactly what the old eager writeback would have seeded."""
    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    seen_histories = []

    def model_func(messages, info):
        seen_histories.append(list(messages))
        return ModelResponse(parts=[TextPart(content="ok")])

    pyd_agent = PydanticAgent(model=FunctionModel(model_func), capabilities=[cap])

    result1 = await pyd_agent.run("turn one")
    eager_baseline = list(result1.all_messages())  # the old writeback's value
    assert agent._message_history == eager_baseline

    await pyd_agent.run("turn two", message_history=agent._message_history)

    # The second request's prior-context prefix is byte-identical to what the
    # eager writeback would have seeded.
    follow_up_request = seen_histories[1]
    assert follow_up_request[: len(eager_baseline)] == eager_baseline


# ---------- production wiring ------------------------------------------------


@contextmanager
def _builder_harness():
    from code_puppy.agents import _builder

    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (TestModel(custom_output_text="woof"), "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        yield _builder


def _make_builder_config():
    from tests.test_agent_span_naming import _FakeAgentConfig

    return _FakeAgentConfig()


def _find_history_persistence(built):
    """Walk the built agent's capability tree with the public ``apply``
    visitor and return the (single) HistoryPersistence leaf."""
    leaves = []
    built.root_capability.apply(leaves.append)
    caps = [leaf for leaf in leaves if isinstance(leaf, HistoryPersistence)]
    assert len(caps) == 1
    return caps[0]


def test_builder_wires_capability_bound_to_the_config():
    cfg = _make_builder_config()
    with _builder_harness() as _builder:
        built = _builder.build_pydantic_agent(cfg)

    cap = _find_history_persistence(built)
    assert cap.agent is cfg


async def test_built_agent_run_persists_history_end_to_end():
    cfg = _make_builder_config()
    with _builder_harness() as _builder:
        built = _builder.build_pydantic_agent(cfg)

    result = await built.run("hello")

    assert _find_history_persistence(built).last_result is result
    assert cfg.get_message_history() == list(result.all_messages())


def test_subagent_site_gets_no_history_persistence():
    """Sub-agent history custody belongs to session persistence — the
    capability is main-path only."""
    from code_puppy.tools import subagent_invocation

    source = inspect.getsource(subagent_invocation)
    assert "HistoryPersistence" not in source
    assert "persist_result_history" not in source


def test_no_inline_writebacks_remain():
    """Every previously-eager writeback site must route through the shared
    writeback helper — no hand-rolled all_messages() persists left behind."""
    import code_puppy.cli_runner as cli_runner
    from code_puppy.agents import _run_signals, _runtime

    runtime_src = inspect.getsource(_runtime)
    signals_src = inspect.getsource(_run_signals)
    cli_src = inspect.getsource(cli_runner)

    assert "_message_history = list(result.all_messages())" not in runtime_src
    assert "_message_history = list(result.all_messages())" not in signals_src
    assert "set_message_history(list(result.all_messages()))" not in cli_src
    assert "set_message_history(list(response.all_messages()))" not in cli_src
    for src in (runtime_src, signals_src, cli_src):
        assert "persist_result_history" in src


# ---------- turn-loop interplay ----------------------------------------------


async def test_steer_drain_persists_alongside_the_capability():
    """prepare_queued_steer_injection keeps its unconditional idempotent
    persist — the steer turn is seeded from the completed transcript even if
    something mutated durable history after ``after_run``."""
    from code_puppy.agents._run_signals import prepare_queued_steer_injection
    from code_puppy.messaging.pause_controller import get_pause_controller

    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    result = _FakeResult(["m1", "m2"])
    await cap.after_run(None, result=result)
    agent._message_history = ["mutated after the run"]

    pc = get_pause_controller()
    pc.request_steer("focus", mode="queue")
    try:
        steer = prepare_queued_steer_injection(agent, result)
    finally:
        pc.drain_pending_steer_queued()

    assert steer == "focus"
    assert agent._message_history == ["m1", "m2"]


def test_steer_drain_persists_for_guest_results():
    """Without the capability (guest wrapper), the steer drain still persists
    the result's messages exactly as the old eager side effect did."""
    from code_puppy.agents._run_signals import prepare_queued_steer_injection
    from code_puppy.messaging.pause_controller import get_pause_controller

    agent = _FakeAgent()
    result = _FakeResult(["m1", "m2"])

    pc = get_pause_controller()
    pc.request_steer("focus", mode="queue")
    try:
        steer = prepare_queued_steer_injection(agent, result)
    finally:
        pc.drain_pending_steer_queued()

    assert steer == "focus"
    assert agent._message_history == ["m1", "m2"]


# ---------- documented divergence pins ---------------------------------------


async def test_prune_is_noop_on_a_completed_run_transcript():
    """Bounded divergence pin: with per-run persistence, the task-body
    ``finally`` prune now sees the completed transcript. A successful run
    leaves no dangling tool calls, so the prune must be a no-op."""
    from code_puppy.agents import _history

    agent = _FakeAgent()
    cap = HistoryPersistence(agent)
    calls = {"n": 0}

    def model_func(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="fetch", args={}, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    pyd_agent = PydanticAgent(model=FunctionModel(model_func), capabilities=[cap])

    @pyd_agent.tool_plain
    def fetch() -> str:
        return "kibble"

    await pyd_agent.run("go")

    pruned = _history.prune_interrupted_tool_calls(agent._message_history)
    assert pruned == agent._message_history
