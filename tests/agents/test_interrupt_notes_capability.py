"""Contract tests for the InterruptedSubagentNotes capability.

Pins feature parity with the retired eager
``_run_signals.inject_interrupted_subagent_notes``:

* drain + ``emit_info`` timing and text at the old call site;
* model-visible note position (immediately before the turn's user request);
* persistence into ``result.all_messages()`` and ``agent._message_history``
  (injection-time mirror + custody-boundary fallback);
* inertness without an observation, and the nested-run anchor guard.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.agents import _runtime
from code_puppy.agents._interrupt_notes import (
    InterruptNoteObservation,
    InterruptedSubagentNotes,
    build_interrupt_note_observation,
    current_observation,
    install_interrupt_note_observation,
    mirror_uninjected,
)
from code_puppy.callbacks import _callbacks, clear_callbacks
from code_puppy.messaging.pause_controller import reset_pause_controller
from code_puppy.tools.subagent_invocation import (
    drain_interrupted_subagents,
    record_interrupted_subagent,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _isolated_interrupt_queue():
    drain_interrupted_subagents()
    yield
    drain_interrupted_subagents()


@pytest.fixture(autouse=True)
def _reset_pause_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


@pytest.fixture(autouse=True)
def _isolated_callbacks():
    snapshot = {phase: list(cbs) for phase, cbs in _callbacks.items()}
    clear_callbacks()
    yield
    clear_callbacks()
    for phase, cbs in snapshot.items():
        _callbacks[phase].extend(cbs)


@pytest.fixture
def _isolated_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)


class _HistoryAgent:
    """Minimal agent shape for observation building."""

    name = "dummy-agent"

    def __init__(self, history: List[Any] | None = None) -> None:
        self._message_history: List[Any] = list(history or [])
        self._mcp_servers: List[Any] = []
        self._code_generation_agent: Any = None

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused"


def _record(session_id: str = "sess-1", saved: int | None = 2) -> None:
    record_interrupted_subagent(
        agent_name="test-agent", session_id=session_id, saved_count=saved
    )


def _observation_for(
    agent: _HistoryAgent, turn_prompt: Any = None
) -> InterruptNoteObservation:
    observation = build_interrupt_note_observation(agent)
    assert observation is not None
    observation.turn_prompt = turn_prompt
    return observation


def _request_context(messages: List[Any]) -> ModelRequestContext:
    return ModelRequestContext(
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart(content="x")])),
        messages=messages,
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )


def _note_texts(messages: List[Any]) -> List[str]:
    out: List[str] = []
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            content = getattr(part, "content", "")
            if isinstance(content, str) and content.startswith("[system note]"):
                out.append(content)
    return out


# =============================================================================
# Observation building (old call-site semantics)
# =============================================================================


def test_build_returns_none_and_keeps_records_without_history_attr():
    """An agent without ``_message_history`` must not drain the queue."""

    class _NoHistory:
        pass

    _record()
    assert build_interrupt_note_observation(_NoHistory()) is None
    assert len(drain_interrupted_subagents()) == 1


def test_build_returns_none_when_no_records():
    assert build_interrupt_note_observation(_HistoryAgent()) is None


def test_build_drains_records_with_exact_note_and_emit_parity(monkeypatch):
    infos: List[str] = []
    monkeypatch.setattr(
        "code_puppy.agents._interrupt_notes.emit_info",
        lambda msg, *a, **k: infos.append(msg),
    )
    _record("sess-1", saved=2)
    _record("sess-2", saved=None)

    observation = build_interrupt_note_observation(_HistoryAgent())

    assert observation is not None
    assert drain_interrupted_subagents() == []
    texts = [part.content for note in observation.notes for part in note.parts]
    assert texts == [
        "[system note] The sub-agent 'test-agent' you invoked was interrupted "
        "by the user before it finished; 2 message(s) of its work were saved. "
        "Its partial session is saved as 'sess-1'.",
        "[system note] The sub-agent 'test-agent' you invoked was interrupted "
        "by the user before it finished; no completed messages had been "
        "produced yet. Its partial session is saved as 'sess-2'.",
    ]
    assert infos == [
        "Noting interrupted sub-agent 'test-agent' (session sess-1) for the "
        "agent's next turn.",
        "Noting interrupted sub-agent 'test-agent' (session sess-2) for the "
        "agent's next turn.",
    ]
    # Notes never carry instructions -- exactly the shape the eager append made.
    assert all(note.instructions is None for note in observation.notes)


# =============================================================================
# Capability seam behaviour
# =============================================================================


@pytest.mark.asyncio
async def test_capability_is_inert_without_observation():
    context = _request_context([ModelRequest(parts=[UserPromptPart(content="hello")])])
    result = await InterruptedSubagentNotes().before_model_request(None, context)
    assert result is context  # identity: untouched, not a copy


@pytest.mark.asyncio
async def test_capability_is_inert_after_injection():
    agent = _HistoryAgent()
    _record()
    observation = _observation_for(agent, turn_prompt="hello")
    observation.injected = True
    context = _request_context([ModelRequest(parts=[UserPromptPart(content="hello")])])
    with install_interrupt_note_observation(observation):
        result = await InterruptedSubagentNotes().before_model_request(None, context)
    assert result is context


@pytest.mark.asyncio
async def test_empty_prompt_turn_appends_notes_at_end():
    """No user request to anchor on -> notes go last, like the eager append."""
    agent = _HistoryAgent()
    _record()
    observation = _observation_for(agent, turn_prompt="")
    tail = ModelResponse(parts=[TextPart(content="old-answer")])
    context = _request_context([tail])

    with install_interrupt_note_observation(observation):
        result = await InterruptedSubagentNotes().before_model_request(None, context)

    assert result.messages == [tail, *observation.notes]
    assert observation.injected is True
    assert agent._message_history == list(observation.notes)  # mirror fired


@pytest.mark.asyncio
async def test_nonmatching_turn_request_defers_injection():
    """A nested run's request must not steal the outer turn's notes."""
    agent = _HistoryAgent()
    _record()
    observation = _observation_for(agent, turn_prompt="outer prompt")
    context = _request_context(
        [ModelRequest(parts=[UserPromptPart(content="nested prompt")])]
    )

    with install_interrupt_note_observation(observation):
        result = await InterruptedSubagentNotes().before_model_request(None, context)

    assert result is context
    assert observation.injected is False
    assert agent._message_history == []


def test_install_shadows_including_none_installs():
    agent = _HistoryAgent()
    _record("outer")
    outer = _observation_for(agent)
    _record("inner")
    inner = _observation_for(agent)

    assert current_observation() is None
    with install_interrupt_note_observation(None):
        assert current_observation() is None
    with install_interrupt_note_observation(outer):
        assert current_observation() is outer
        with install_interrupt_note_observation(inner):
            assert current_observation() is inner
        assert current_observation() is outer
        # A nested run installs None -- it must SHADOW the outer observation,
        # not fall through to it (nested-run isolation).
        with install_interrupt_note_observation(None):
            assert current_observation() is None
        assert current_observation() is outer
    assert current_observation() is None


def test_mirror_uninjected_is_idempotent_and_respects_injection():
    agent = _HistoryAgent(history=["seed"])
    _record()
    observation = _observation_for(agent)

    mirror_uninjected(observation)
    mirror_uninjected(observation)  # second call must not double-append
    assert agent._message_history == ["seed", *observation.notes]

    # Already-injected notes must not be mirrored again.
    agent2 = _HistoryAgent()
    _record("sess-9")
    observation2 = _observation_for(agent2)
    observation2.injected = True
    mirror_uninjected(observation2)
    assert agent2._message_history == []

    mirror_uninjected(None)  # None-safe


# =============================================================================
# End-to-end through a real pydantic-ai Agent
# =============================================================================


def _make_scripted_model(seen_calls: List[List[str]], steps: int = 1) -> FunctionModel:
    """FunctionModel that records per-call message part contents."""

    def model_fn(messages: List[Any], info: AgentInfo) -> ModelResponse:
        seen_calls.append(
            [
                str(getattr(part, "content", ""))
                for message in messages
                for part in message.parts
            ]
        )
        if len(seen_calls) < steps:
            return ModelResponse(parts=[ToolCallPart(tool_name="noop", args={})])
        return ModelResponse(parts=[TextPart(content="done")])

    return FunctionModel(model_fn)


@pytest.mark.asyncio
async def test_injection_lands_before_turn_request_and_persists():
    agent = _HistoryAgent()
    _record("sess-1", saved=2)
    observation = _observation_for(agent, turn_prompt="hello")

    seen_calls: List[List[str]] = []
    pydantic_agent = Agent(
        _make_scripted_model(seen_calls),
        capabilities=[InterruptedSubagentNotes()],
    )
    history = [
        ModelRequest(parts=[UserPromptPart(content="old-turn")]),
        ModelResponse(parts=[TextPart(content="old-answer")]),
    ]

    with install_interrupt_note_observation(observation):
        result = await pydantic_agent.run("hello", message_history=history)

    note_text = observation.notes[0].parts[0].content
    # Model-visible order matches the eager append: history, note, prompt.
    assert seen_calls == [["old-turn", "old-answer", note_text, "hello"]]
    # The note persists into recorded history, before the turn's request.
    recorded = _note_texts(result.all_messages())
    assert recorded == [note_text]
    all_contents = [
        getattr(part, "content", None)
        for message in result.all_messages()
        for part in message.parts
    ]
    assert all_contents.index(note_text) < all_contents.index("hello")
    # Injection-time mirror: retry re-entry seeds see the note.
    assert _note_texts(agent._message_history) == [note_text]


@pytest.mark.asyncio
async def test_single_injection_across_multi_step_run():
    agent = _HistoryAgent()
    _record("sess-1", saved=1)
    observation = _observation_for(agent, turn_prompt="hello")

    seen_calls: List[List[str]] = []
    pydantic_agent = Agent(
        _make_scripted_model(seen_calls, steps=2),
        capabilities=[InterruptedSubagentNotes()],
    )

    @pydantic_agent.tool_plain
    def noop() -> str:
        return "ok"

    with install_interrupt_note_observation(observation):
        result = await pydantic_agent.run("hello")

    note_text = observation.notes[0].parts[0].content
    # The note appears exactly once per model call (persisted, not re-spliced)
    assert [call.count(note_text) for call in seen_calls] == [1, 1]
    assert _note_texts(result.all_messages()) == [note_text]
    assert _note_texts(agent._message_history) == [note_text]


# =============================================================================
# Production-shaped: through run_with_mcp
# =============================================================================


@pytest.mark.asyncio
async def test_run_with_mcp_delivers_notes_through_capability(_isolated_runtime):
    """Full call-site wiring: drain at run start, ContextVar into the task,
    anchor on the built prompt payload, injection + mirror."""
    seen_calls: List[List[str]] = []
    pydantic_agent = Agent(
        _make_scripted_model(seen_calls),
        capabilities=[InterruptedSubagentNotes()],
    )
    agent = _HistoryAgent(
        history=[
            ModelRequest(parts=[UserPromptPart(content="old-turn")]),
            ModelResponse(parts=[TextPart(content="old-answer")]),
        ]
    )
    agent._code_generation_agent = pydantic_agent
    _record("sess-42", saved=3)

    result = await _runtime.run_with_mcp(agent, "fresh prompt")

    assert result is not None
    notes = _note_texts(result.all_messages())
    assert notes == [
        "[system note] The sub-agent 'test-agent' you invoked was interrupted "
        "by the user before it finished; 3 message(s) of its work were saved. "
        "Its partial session is saved as 'sess-42'."
    ]
    # Model saw the note between prior history and this turn's prompt.
    assert seen_calls == [["old-turn", "old-answer", notes[0], "fresh prompt"]]
    # Mirror persisted it for retry re-entries / crash custody.
    assert _note_texts(agent._message_history) == notes
    # Records were drained at run start.
    assert drain_interrupted_subagents() == []


class _CancelledPydanticAgent:
    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_run_with_mcp_custody_fallback_on_cancel_before_request(
    _isolated_runtime,
):
    """A run cancelled before any model request still persists the notes,
    exactly like the old eager history append."""
    agent = _HistoryAgent(
        history=[ModelRequest(parts=[UserPromptPart(content="old-turn")])]
    )
    agent._code_generation_agent = _CancelledPydanticAgent()
    _record("sess-7", saved=None)

    result = await _runtime.run_with_mcp(agent, "doomed prompt")

    assert result is None  # cancellation is absorbed by the runtime
    notes = _note_texts(agent._message_history)
    assert notes == [
        "[system note] The sub-agent 'test-agent' you invoked was interrupted "
        "by the user before it finished; no completed messages had been "
        "produced yet. Its partial session is saved as 'sess-7'."
    ]
    assert drain_interrupted_subagents() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer_prompt", "nested_prompt"),
    [
        ("", "nested prompt"),  # empty outer anchor: append branch bait
        ("continue", "continue"),  # identical prompts: anchor-match bait
    ],
)
async def test_nested_run_cannot_steal_outer_notes(
    _isolated_runtime, outer_prompt, nested_prompt
):
    """A nested run started while the outer observation is ambient must not
    consume the outer turn's one-shot injection state -- even when the outer
    anchor is empty or the prompts are identical (reviewer finding, PR #840).
    """
    agent = _HistoryAgent()
    _record("sess-outer", saved=1)
    outer_observation = _observation_for(agent, turn_prompt=outer_prompt)

    seen_calls: List[List[str]] = []
    nested_pydantic_agent = Agent(
        _make_scripted_model(seen_calls),
        capabilities=[InterruptedSubagentNotes()],
    )
    nested_agent = _HistoryAgent()
    nested_agent._code_generation_agent = nested_pydantic_agent

    # Simulate the outer run's task context: observation ambient, run depth 1.
    with install_interrupt_note_observation(outer_observation):
        _runtime._active_run_depth += 1
        try:
            await _runtime.run_with_mcp(nested_agent, nested_prompt)
        finally:
            _runtime._active_run_depth -= 1

    note_text = outer_observation.notes[0].parts[0].content
    # The nested model never saw the outer turn's notes...
    assert all(note_text not in call for call in seen_calls)
    # ...and the outer turn's delivery state is untouched.
    assert outer_observation.injected is False
    assert _note_texts(agent._message_history) == []
    assert _note_texts(nested_agent._message_history) == []


@pytest.mark.asyncio
async def test_multimodal_turn_prompt_anchors_the_splice():
    """A [prompt, *attachments] payload rides one UserPromptPart whose content
    is the original list (pydantic-ai 2.31.0); the anchor must match it."""
    from pydantic_ai.messages import BinaryContent

    agent = _HistoryAgent()
    _record()
    payload = ["look at this", BinaryContent(data=b"\x89PNG", media_type="image/png")]
    observation = _observation_for(agent, turn_prompt=payload)
    turn_request = ModelRequest(parts=[UserPromptPart(content=payload)])
    tail = ModelResponse(parts=[TextPart(content="old-answer")])
    context = _request_context([tail, turn_request])

    with install_interrupt_note_observation(observation):
        result = await InterruptedSubagentNotes().before_model_request(None, context)

    assert result.messages == [tail, *observation.notes, turn_request]
    assert observation.injected is True


@pytest.mark.asyncio
async def test_nested_run_does_not_drain_records(_isolated_runtime):
    """Nested runs must leave the record queue for the outer run."""
    seen_calls: List[List[str]] = []
    pydantic_agent = Agent(_make_scripted_model(seen_calls))
    agent = _HistoryAgent(
        history=[ModelRequest(parts=[UserPromptPart(content="old-turn")])]
    )
    agent._code_generation_agent = pydantic_agent
    _record("sess-nested")

    _runtime._active_run_depth += 1  # simulate an outer run in flight
    try:
        await _runtime.run_with_mcp(agent, "inner prompt")
    finally:
        _runtime._active_run_depth -= 1

    assert _note_texts(agent._message_history) == []
    assert len(drain_interrupted_subagents()) == 1


# =============================================================================
# Wiring pins
# =============================================================================


def test_builder_orders_notes_before_compaction():
    """The capability must precede the compaction ProcessHistory so
    compaction sees the notes exactly as it saw the old eager append."""
    import inspect

    from code_puppy.agents import _builder

    source = inspect.getsource(_builder)
    notes_pos = source.index("InterruptedSubagentNotes(),")
    compaction_pos = source.index("ProcessHistory(history_processor)")
    assert notes_pos < compaction_pos


def test_subagent_site_has_no_interrupt_notes_capability():
    """Sub-agents must never inject the main conversation's notes."""
    import inspect

    from code_puppy.tools import subagent_invocation

    source = inspect.getsource(subagent_invocation)
    assert "InterruptedSubagentNotes" not in source
