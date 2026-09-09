"""Contract tests for the ``PromptPreparation`` capability.

The capability replaces ``_runtime._should_prepend_system_prompt``'s baked-in
first-turn prompt fold (claude-code OAuth etc.) with a request-time swap plus
a persist-time mirror; see ``code_puppy/agents/_prompt_preparation.py`` for
the migration story. These tests pin:

* hook-call parity of :func:`build_prompt_observation` with the old code
  (same arguments, same call count, NOT fired for non-qualifying turns),
* the send-side swap semantics (first message only, attachments payloads,
  no mutation of the input messages),
* the persist-side mirror (in-place, idempotent),
* end-to-end wire parity against the old baked-in behaviour through a real
  ``Agent.run()``, including retry-style re-runs from checkpointed history,
* ContextVar scoping (no observation == inert; nested installs shadow).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.agents._prompt_preparation import (
    PromptObservation,
    PromptPreparation,
    build_prompt_observation,
    current_prompt_observation,
    observe_prompt_preparation,
)

RAW = "please fetch the bone"
PREPARED = "SYSTEM PROMPT\n\nplease fetch the bone"


@dataclass
class FakeAgent:
    """Just enough surface for ``build_prompt_observation``."""

    _message_history: List[Any] = field(default_factory=list)
    system_prompt: str = "SYSTEM PROMPT"
    model_name: str = "claude-code-sonnet"

    def get_full_system_prompt(self) -> str:
        return self.system_prompt

    def get_model_name(self) -> str:
        return self.model_name


def _capture_model(seen: List[List[Any]]) -> FunctionModel:
    def model_fn(messages: List[Any], info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        return ModelResponse(parts=[TextPart("ok")])

    return FunctionModel(model_fn)


def _content_shape(messages: List[Any]) -> List[Any]:
    """Timestamp-free projection of what the model saw."""
    shape: List[Any] = []
    for message in messages:
        for part in message.parts:
            shape.append((type(part).__name__, getattr(part, "content", None)))
    return shape


# ---- build_prompt_observation: hook-call parity -----------------------------


def test_non_qualifying_turn_does_not_fire_hooks(monkeypatch):
    """Non-empty history == the old early return: hooks must NOT fire."""

    def boom(**_kwargs):  # pragma: no cover - would fail the test
        raise AssertionError("prepare_prompt_for_model must not be called")

    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", boom)
    agent = FakeAgent(_message_history=[object()])
    observation, prompt = build_prompt_observation(agent, RAW)
    assert not observation.active
    assert prompt == RAW


def test_first_turn_fires_hooks_with_old_arguments(monkeypatch):
    calls: List[dict] = []

    def fake_prepare(*, model_name, system_prompt, user_prompt, prepend_system_to_user):
        calls.append(
            {
                "model_name": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "prepend_system_to_user": prepend_system_to_user,
            }
        )

        @dataclass
        class Prepared:
            user_prompt: str

        return Prepared(user_prompt=f"{system_prompt}\n\n{user_prompt}")

    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", fake_prepare)
    monkeypatch.setattr("code_puppy.agents._builder.load_puppy_rules", lambda: "RULES")

    agent = FakeAgent()
    observation, prompt = build_prompt_observation(agent, RAW)

    # Exactly one call, byte-identical to the old _should_prepend_system_prompt.
    assert calls == [
        {
            "model_name": "claude-code-sonnet",
            "system_prompt": "SYSTEM PROMPT\nRULES",
            "user_prompt": RAW,
            "prepend_system_to_user": True,
        }
    ]
    assert prompt == RAW  # raw prompt rides to run(); the capability swaps
    assert observation.active
    assert observation.raw == RAW
    assert observation.prepared == f"SYSTEM PROMPT\nRULES\n\n{RAW}"


def test_identity_preparation_is_inert(monkeypatch):
    """No plugin claimed the model -> prepared == raw -> nothing to do."""

    def fake_prepare(**kwargs):
        @dataclass
        class Prepared:
            user_prompt: str

        return Prepared(user_prompt=kwargs["user_prompt"])

    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", fake_prepare)
    monkeypatch.setattr("code_puppy.agents._builder.load_puppy_rules", lambda: None)

    observation, prompt = build_prompt_observation(FakeAgent(), RAW)
    assert not observation.active
    assert prompt == RAW


def test_empty_prompt_bakes_eagerly(monkeypatch):
    """Payload building drops empty prompts, so the fold can't ride the swap."""

    def fake_prepare(**kwargs):
        @dataclass
        class Prepared:
            user_prompt: str

        return Prepared(user_prompt=f"{kwargs['system_prompt']}\n\n")

    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", fake_prepare)
    monkeypatch.setattr("code_puppy.agents._builder.load_puppy_rules", lambda: None)

    observation, prompt = build_prompt_observation(FakeAgent(), "")
    assert not observation.active
    assert prompt == "SYSTEM PROMPT\n\n"  # old behaviour: baked into the prompt


# ---- send side: apply_to_request --------------------------------------------


def _observation() -> PromptObservation:
    return PromptObservation(raw=RAW, prepared=PREPARED, active=True)


def test_swap_replaces_first_user_message_without_mutating_input():
    original = ModelRequest(parts=[UserPromptPart(content=RAW)])
    messages: List[Any] = [original, ModelResponse(parts=[TextPart("hi")])]

    swapped = _observation().apply_to_request(messages)

    assert swapped[0].parts[0].content == PREPARED
    assert swapped[1] is messages[1]
    assert original.parts[0].content == RAW  # fresh copies, no aliasing


def test_swap_handles_attachment_payloads():
    attachment = BinaryContent(data=b"\x89PNG", media_type="image/png")
    messages = [ModelRequest(parts=[UserPromptPart(content=[RAW, attachment])])]

    swapped = _observation().apply_to_request(messages)

    content = swapped[0].parts[0].content
    assert content[0] == PREPARED
    assert content[1] is attachment


def test_swap_leaves_non_matching_content_alone():
    observation = _observation()
    for messages in (
        [],
        [ModelResponse(parts=[TextPart("model first")])],
        [ModelRequest(parts=[UserPromptPart(content="different text")])],
        [
            ModelRequest(
                parts=[ToolReturnPart(tool_name="t", content="x", tool_call_id="1")]
            )
        ],
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=[BinaryContent(data=b"z", media_type="image/png")]
                    )
                ]
            )
        ],
    ):
        assert observation.apply_to_request(messages) == messages


def test_swap_is_positional_not_content_scanning():
    """A later message repeating the raw text must NOT be folded."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content="turn one")]),
        ModelResponse(parts=[TextPart("ok")]),
        ModelRequest(parts=[UserPromptPart(content=RAW)]),
    ]
    assert _observation().apply_to_request(messages) == messages


def test_inactive_observation_is_a_no_op():
    messages = [ModelRequest(parts=[UserPromptPart(content=RAW)])]
    assert PromptObservation.inactive().apply_to_request(messages) is messages
    # Identity swaps deactivate themselves in __post_init__.
    assert not PromptObservation(raw=RAW, prepared=RAW, active=True).active


# ---- persist side: mirror ---------------------------------------------------


def test_mirror_rewrites_in_place_and_is_idempotent():
    part = UserPromptPart(content=RAW)
    history: List[Any] = [
        ModelRequest(parts=[part]),
        ModelResponse(parts=[TextPart("ok")]),
    ]
    observation = _observation()

    observation.mirror(history)
    assert part.content == PREPARED  # the SAME object every alias sees

    observation.mirror(history)  # idempotent: content no longer matches raw
    assert part.content == PREPARED


def test_mirror_tolerates_empty_and_foreign_history():
    observation = _observation()
    observation.mirror(None)
    observation.mirror([])
    response_first: List[Any] = [ModelResponse(parts=[TextPart("hi")])]
    observation.mirror(response_first)
    assert response_first[0].parts[0].content == "hi"


# ---- capability seams -------------------------------------------------------


def test_capability_without_observation_is_inert():
    async def scenario():
        assert current_prompt_observation() is None
        seen: List[List[Any]] = []
        agent = Agent(
            model=_capture_model(seen),
            instructions="sys",
            output_type=str,
            capabilities=[PromptPreparation()],
        )
        result = await agent.run(RAW)
        assert seen[0][0].parts[0].content == RAW
        assert result.all_messages()[0].parts[0].content == RAW

    asyncio.run(scenario())


def test_wire_and_history_parity_with_baked_prompt():
    """Capability + raw prompt must be byte-identical to the old baked prepend."""

    async def scenario():
        baked_seen: List[List[Any]] = []
        baked_agent = Agent(
            model=_capture_model(baked_seen),
            instructions="sys",
            output_type=str,
        )
        baked_result = await baked_agent.run(PREPARED)  # the old code path

        cap_seen: List[List[Any]] = []
        cap_agent = Agent(
            model=_capture_model(cap_seen),
            instructions="sys",
            output_type=str,
            capabilities=[PromptPreparation()],
        )
        with observe_prompt_preparation(_observation()):
            task = asyncio.get_running_loop().create_task(cap_agent.run(RAW))
        cap_result = await task

        # Model-visible bytes: identical.
        assert _content_shape(cap_seen[0]) == _content_shape(baked_seen[0])
        # Bytes at rest: identical (after_run mirrored the recorded history).
        assert _content_shape(cap_result.all_messages()) == _content_shape(
            baked_result.all_messages()
        )

    asyncio.run(scenario())


def test_checkpoint_resume_rerun_still_folds():
    """A streaming-retry re-entry resumes from checkpointed history whose
    first message is still raw; the swap must keep applying so the model
    sees the folded prompt exactly as it did when the fold was baked in."""

    async def scenario():
        seen: List[List[Any]] = []
        agent = Agent(
            model=_capture_model(seen),
            instructions="sys",
            output_type=str,
            capabilities=[PromptPreparation()],
        )
        checkpointed: List[Any] = [
            ModelRequest(parts=[UserPromptPart(content=RAW)]),
            ModelResponse(parts=[TextPart("partial step")]),
        ]
        with observe_prompt_preparation(_observation()):
            task = asyncio.get_running_loop().create_task(
                agent.run("continue", message_history=checkpointed)
            )
        result = await task
        # Send side: the model saw the folded prompt.
        assert seen[0][0].parts[0].content == PREPARED
        # Persist side: the run's RECORDED history was mirrored by after_run.
        assert result.all_messages()[0].parts[0].content == PREPARED
        # pydantic-ai copies supplied history, so the caller's checkpoint list
        # itself stays raw after the run — repairing it is exactly the job of
        # the core custody-boundary mirror, pinned separately below.
        assert checkpointed[0].parts[0].content == RAW

    asyncio.run(scenario())


def test_main_custody_boundary_mirror_then_prune():
    """Production-shaped replica of ``_run_agent_task_body``'s finally block:
    mirror the (possibly raw) turn state in place, THEN prune interrupted
    tool calls — covering crash/cancel exits where after_run never fired."""
    from code_puppy.agents import _history

    part = UserPromptPart(content=RAW)
    message_history: List[Any] = [
        ModelRequest(parts=[part]),
        ModelResponse(parts=[TextPart("partial step")]),
    ]
    observation = _observation()

    observation.mirror(message_history)
    message_history = _history.prune_interrupted_tool_calls(message_history)

    assert message_history[0].parts[0].content == PREPARED
    assert part.content == PREPARED  # in place: every alias sees it


def test_subagent_partial_save_custody_boundary():
    """Production-shaped replica of the sub-agent except-block mirror: the
    checkpointed ``agent_config`` history is repaired before partial save."""

    class FakeConfig:
        def __init__(self, history: List[Any]) -> None:
            self._history = history

        def get_message_history(self) -> List[Any]:
            return self._history

    part = UserPromptPart(content=RAW)
    config = FakeConfig([ModelRequest(parts=[part])])
    observation = _observation()

    # Exactly what the except block does before _save_partial_session.
    observation.mirror(config.get_message_history() or [])

    assert config.get_message_history()[0].parts[0].content == PREPARED


def test_process_history_after_prompt_preparation_sees_folded_message():
    """Pins the capability-list ordering contract both construction sites use:
    PromptPreparation FIRST means compaction observes the folded prompt."""

    async def scenario():
        observed: List[List[Any]] = []

        def recorder(messages: List[Any]) -> List[Any]:
            observed.append(list(messages))
            return messages

        seen: List[List[Any]] = []
        agent = Agent(
            model=_capture_model(seen),
            instructions="sys",
            output_type=str,
            capabilities=[PromptPreparation(), ProcessHistory(recorder)],
        )
        with observe_prompt_preparation(_observation()):
            task = asyncio.get_running_loop().create_task(agent.run(RAW))
        await task
        assert observed[0][0].parts[0].content == PREPARED

    asyncio.run(scenario())


def test_nested_observation_shadowing():
    """Sub-agent installs must shadow the outer turn's observation for their
    own tasks only — mirroring how sub-agent invocation nests inside a run."""

    async def scenario():
        outer = _observation()
        inner = PromptObservation(
            raw="inner raw", prepared="inner prepared", active=True
        )

        async def inner_task() -> Optional[PromptObservation]:
            return current_prompt_observation()

        with observe_prompt_preparation(outer):
            with observe_prompt_preparation(inner):
                shadowed = asyncio.get_running_loop().create_task(inner_task())
            restored = asyncio.get_running_loop().create_task(inner_task())
            assert await shadowed is inner
            assert await restored is outer
        assert current_prompt_observation() is None

    asyncio.run(scenario())


def test_not_spec_serializable():
    assert PromptPreparation.get_serialization_name() is None
