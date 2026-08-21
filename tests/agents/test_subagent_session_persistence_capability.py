"""Contract tests for the ``SubagentSessionPersistence`` capability.

The capability moves sub-agent session persistence onto pydantic-ai's
``wrap_run`` seam: success saves the full transcript at the run boundary,
failure/cancellation saves the partial checkpoint via the same
``_save_partial_session`` helper the eager path used, and the invocation
layer reads the custody records (``recorded_save``) instead of saving
eagerly -- falling back to the eager saves only when the boundary never ran.

Covers:
* seam-signature parity with ``AbstractCapability.wrap_run``
* success/failure/cancellation custody through a REAL pydantic-ai ``Agent``
* the eager triage mirrored exactly (``SystemExit``/``GeneratorExit`` never save)
* call-time helper resolution (existing test patches keep intercepting writes)
* ``recorded_save`` triage and latest-attempt-wins retry semantics
* invocation-layer wiring: capability construction, fallback-when-guest,
  and the no-clobber guard for crashes after a successful run
"""

import asyncio
import inspect
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

from code_puppy.agents._subagent_sessions import SubagentSessionPersistence

SAVE_HISTORY = "code_puppy.tools.subagent_invocation._save_session_history"
SAVE_PARTIAL = "code_puppy.tools.subagent_invocation._save_partial_session"


class FakeConfig:
    """Minimal stand-in for the BaseAgent config wrapper."""

    def __init__(self, history=None):
        self._message_history = list(history or [])

    def get_message_history(self):
        return self._message_history


def _capability(**overrides):
    kwargs = dict(
        agent_config=FakeConfig(),
        session_id="tester-session-abc123",
        agent_name="tester",
        baseline_count=0,
        initial_prompt="hi there",
    )
    kwargs.update(overrides)
    return SubagentSessionPersistence(**kwargs)


def _agent_with(cap, model):
    return Agent(
        model=model,
        instructions="be terse",
        output_type=str,
        capabilities=[cap],
    )


# ---------------------------------------------------------------------------
# Seam contract
# ---------------------------------------------------------------------------


def test_wrap_run_signature_matches_base_seam():
    base = inspect.signature(AbstractCapability.wrap_run)
    ours = inspect.signature(SubagentSessionPersistence.wrap_run)
    assert [(p.name, p.kind) for p in ours.parameters.values()] == [
        (p.name, p.kind) for p in base.parameters.values()
    ]
    # ``handler`` must stay keyword-only, matching the seam's calling convention.
    assert ours.parameters["handler"].kind is inspect.Parameter.KEYWORD_ONLY


def test_not_spec_constructible():
    assert SubagentSessionPersistence.get_serialization_name() is None


# ---------------------------------------------------------------------------
# Success custody through a real agent run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_run_saves_full_transcript_at_boundary():
    cap = _capability()
    agent = _agent_with(cap, TestModel())
    saves = []
    with patch(SAVE_HISTORY, side_effect=lambda **kw: saves.append(kw)):
        result = await agent.run("hello")

    assert cap.final_saved is True
    assert cap.recorded_save() == (True, cap.final_saved_count)
    assert len(saves) == 1
    save = saves[0]
    assert save["session_id"] == "tester-session-abc123"
    assert save["agent_name"] == "tester"
    assert save["initial_prompt"] == "hi there"
    # Byte-identical payload to the eager post-run save.
    assert save["message_history"] == list(result.all_messages())
    assert cap.final_saved_count == len(save["message_history"])


@pytest.mark.asyncio
async def test_final_save_resolves_helper_at_call_time():
    """Patching the invocation module attr intercepts the capability's save.

    This is the compatibility contract the existing suites rely on: they
    patch ``subagent_invocation._save_session_history`` and must keep
    seeing every write.
    """
    cap = _capability()
    agent = _agent_with(cap, TestModel())
    mock_save = MagicMock()
    with patch(SAVE_HISTORY, mock_save):
        await agent.run("hello")
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_final_save_failure_propagates_and_leaves_no_record():
    """A failed boundary save fails the run, exactly as the eager save
    failing failed the invocation. No partial record is written for it --
    the invocation layer's fallback then takes over."""
    cap = _capability()
    agent = _agent_with(cap, TestModel())
    with patch(SAVE_HISTORY, side_effect=OSError("disk full")):
        with pytest.raises(BaseException) as excinfo:
            await agent.run("hello")
    assert "disk full" in repr(excinfo.getrepr(style="value"))
    assert cap.final_saved is False
    assert cap.partial_save_attempted is False
    assert cap.recorded_save() == (False, None)


# ---------------------------------------------------------------------------
# Failure / cancellation custody through a real agent run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_inside_run_records_partial_save_and_reraises():
    def explode(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("model on fire")

    cap = _capability(agent_config=FakeConfig(["m1", "m2"]), baseline_count=1)
    agent = _agent_with(cap, FunctionModel(explode))
    partial = MagicMock(return_value=2)
    with patch(SAVE_PARTIAL, partial):
        with pytest.raises(BaseException) as excinfo:
            await agent.run("hello")

    assert "model on fire" in repr(excinfo.getrepr(style="value"))
    assert cap.partial_save_attempted is True
    assert cap.partial_saved_count == 2
    assert cap.recorded_save() == (True, 2)
    partial.assert_called_once_with(
        agent_config=cap.agent_config,
        session_id="tester-session-abc123",
        agent_name="tester",
        baseline_count=1,
        initial_prompt="hi there",
    )


@pytest.mark.asyncio
async def test_cancellation_records_partial_save():
    started = asyncio.Event()

    async def hang(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        started.set()
        await asyncio.sleep(3600)
        return ModelResponse(parts=[TextPart("unreachable")])

    cap = _capability()
    agent = _agent_with(cap, FunctionModel(hang))
    partial = MagicMock(return_value=None)
    with patch(SAVE_PARTIAL, partial):
        task = asyncio.create_task(agent.run("hello"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert cap.partial_save_attempted is True
    assert cap.partial_saved_count is None
    assert cap.recorded_save() == (True, None)
    partial.assert_called_once()


def test_should_record_mirrors_eager_triage():
    should = SubagentSessionPersistence._should_record
    assert should(RuntimeError("boom")) is True
    assert should(KeyboardInterrupt()) is True
    assert should(asyncio.CancelledError()) is True
    # Async teardown wraps cancellation in a group; still an interruption.
    group = BaseExceptionGroup("teardown", [asyncio.CancelledError()])
    assert should(group) is True
    # The eager ``except`` block re-raised these without saving.
    assert should(SystemExit(1)) is False
    assert should(GeneratorExit()) is False


@pytest.mark.asyncio
async def test_wrap_run_skips_save_for_system_exit():
    async def boom():
        raise SystemExit(3)

    cap = _capability()
    partial = MagicMock()
    with patch(SAVE_PARTIAL, partial):
        with pytest.raises(SystemExit):
            await cap.wrap_run(None, handler=boom)
    partial.assert_not_called()
    assert cap.recorded_save() == (False, None)


# ---------------------------------------------------------------------------
# recorded_save triage + retry semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_reinvocation_latest_attempt_wins():
    """``streaming_retry`` re-invokes ``run()`` on the same agent, so one
    capability instance sees several ``wrap_run`` calls. A transient failure
    checkpoints partial progress; the successful retry's full save then
    takes precedence in ``recorded_save``."""
    cap = _capability()

    async def fail():
        raise RuntimeError("transient 503")

    async def succeed():
        result = MagicMock()
        result.all_messages.return_value = ["m1", "m2", "m3"]
        return result

    with patch(SAVE_PARTIAL, return_value=1) as partial, patch(SAVE_HISTORY) as final:
        with pytest.raises(RuntimeError):
            await cap.wrap_run(None, handler=fail)
        assert cap.recorded_save() == (True, 1)

        returned = await cap.wrap_run(None, handler=succeed)

    assert returned.all_messages.return_value == ["m1", "m2", "m3"]
    partial.assert_called_once()
    final.assert_called_once()
    assert cap.final_saved is True
    # Full save outranks the earlier attempt's partial record.
    assert cap.recorded_save() == (True, 3)


def test_recorded_save_three_states():
    cap = _capability()
    assert cap.recorded_save() == (False, None)

    cap.partial_save_attempted = True
    cap.partial_saved_count = None
    assert cap.recorded_save() == (True, None)

    cap.final_saved = True
    cap.final_saved_count = 7
    assert cap.recorded_save() == (True, 7)


# ---------------------------------------------------------------------------
# Invocation-layer wiring
# ---------------------------------------------------------------------------


def _passthrough_retry(*_args, **_kwargs):
    def _decorator(func):
        return func

    return _decorator


def _build_agent_config():
    config = MagicMock()

    @contextmanager
    def temporary_override(_model_name):
        yield

    config.temporary_model_name_override.side_effect = temporary_override
    config.get_model_name.return_value = "test-model"
    config.get_full_system_prompt.return_value = "Test instructions"
    config.get_available_tools.return_value = ["list_files"]
    config.get_message_history.return_value = []
    return config


@contextmanager
def _invocation_harness(capture):
    """Patch the invocation layer's collaborators; capture Agent kwargs.

    The mocked ``Agent`` never executes capabilities itself; individual
    tests decide whether the captured capability runs (production-shaped)
    or stays inert (guest-fallback shape).
    """
    agent_config = _build_agent_config()
    capture["agent_config"] = agent_config

    def fake_agent(*args, **kwargs):
        capture["agent_kwargs"] = kwargs
        return capture["temp_agent"]

    with ExitStack() as stack:
        p = stack.enter_context
        p(patch("code_puppy.tools.subagent_invocation.get_message_bus"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.get_session_context",
                return_value="parent",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.set_session_context"))
        capture["info"] = p(patch("code_puppy.tools.subagent_invocation.emit_info"))
        p(patch("code_puppy.tools.subagent_invocation.emit_error"))
        p(patch("code_puppy.tools.subagent_invocation.emit_success"))
        capture["warning"] = p(
            patch("code_puppy.tools.subagent_invocation.emit_warning")
        )
        capture["save"] = p(patch(SAVE_HISTORY))
        capture["partial"] = p(patch(SAVE_PARTIAL, return_value=None))
        p(
            patch(
                "code_puppy.tools.subagent_invocation._load_session_history",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
                return_value="abc123",
            )
        )
        p(
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=agent_config,
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"test-model": {}},
            )
        )
        p(patch("code_puppy.model_factory.ModelFactory.get_model"))
        p(patch("code_puppy.model_factory.make_model_settings"))
        p(patch("code_puppy.agents._builder.load_puppy_rules", return_value=None))
        p(patch("code_puppy.callbacks.on_load_prompt", return_value=[]))
        prepare = p(patch("code_puppy.model_utils.prepare_prompt_for_model"))
        prepare.return_value = MagicMock(
            instructions="prepared instructions", user_prompt="prepared prompt"
        )
        p(
            patch(
                "code_puppy.agents._builder.autostart_bound_servers_async",
                new=AsyncMock(),
            )
        )
        p(patch("code_puppy.config.get_value", return_value="true"))
        p(patch("code_puppy.config.get_output_level", return_value="medium"))
        p(
            patch(
                "code_puppy.agents._compaction.make_history_processor",
                return_value=lambda messages: messages,
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.Agent", side_effect=fake_agent))
        p(patch("code_puppy.tools.register_tools_for_agent"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_wrap_pydantic_agent",
                side_effect=lambda _cfg, agent, **_kwargs: agent,
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_agent_run_context",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.agents.retry_profiles.make_streaming_retry",
                new=_passthrough_retry,
            )
        )
        yield


def _capability_from(capture):
    caps = capture["agent_kwargs"]["capabilities"]
    ours = [c for c in caps if isinstance(c, SubagentSessionPersistence)]
    assert len(ours) == 1
    return ours[0]


async def _drive_invocation(capture, run_side_effect):
    from code_puppy.tools.subagent_invocation import _invoke_agent_impl

    temp_agent = MagicMock()
    temp_agent.run = AsyncMock(side_effect=run_side_effect)
    capture["temp_agent"] = temp_agent
    with _invocation_harness(capture):
        return await _invoke_agent_impl(
            MagicMock(),
            agent_name="test-agent",
            prompt="Hello",
        )


def _successful_result():
    result = MagicMock()
    result.output = "subagent response"
    result.all_messages.return_value = ["m1", "m2"]
    return result


@pytest.mark.asyncio
async def test_invocation_constructs_capability_with_prepared_prompt():
    capture = {}
    result = _successful_result()

    await _drive_invocation(capture, lambda *a, **kw: result)

    cap = _capability_from(capture)
    assert cap.agent_config is capture["agent_config"]
    assert cap.session_id == "test-agent-session-abc123"
    assert cap.agent_name == "test-agent"
    assert cap.baseline_count == 0
    # New session: the initial prompt is the PREPARED prompt, matching what
    # the eager save wrote after prepare_prompt_for_model rewrote it.
    assert cap.initial_prompt == "prepared prompt"


@pytest.mark.asyncio
async def test_guest_run_falls_back_to_eager_save():
    """The mocked run never executes capabilities -- exactly the shape of a
    plugin wrapper that bypasses them. The eager save must still fire."""
    capture = {}
    result = _successful_result()

    output = await _drive_invocation(capture, lambda *a, **kw: result)

    assert output.error is None
    capture["save"].assert_called_once_with(
        session_id="test-agent-session-abc123",
        message_history=["m1", "m2"],
        agent_name="test-agent",
        initial_prompt="prepared prompt",
    )


@pytest.mark.asyncio
async def test_boundary_save_skips_eager_save():
    """Production shape: the run routes through the capability's wrap_run,
    so the invocation layer must not save a second time."""
    capture = {}
    result = _successful_result()

    async def run_through_capability(*_args, **_kwargs):
        cap = _capability_from(capture)

        async def produce():
            return result

        return await cap.wrap_run(None, handler=produce)

    output = await _drive_invocation(capture, run_through_capability)

    assert output.error is None
    # Exactly one write: the boundary save (through the patched module attr).
    capture["save"].assert_called_once()
    assert _capability_from(capture).final_saved is True


@pytest.mark.asyncio
async def test_failure_inside_run_uses_boundary_record_no_double_save():
    capture = {}

    async def run_through_capability(*_args, **_kwargs):
        cap = _capability_from(capture)

        async def explode():
            raise RuntimeError("boom")

        return await cap.wrap_run(None, handler=explode)

    output = await _drive_invocation(capture, run_through_capability)

    assert output.error is not None
    cap = _capability_from(capture)
    assert cap.partial_save_attempted is True
    # The boundary already saved; the invocation layer must not save again.
    capture["partial"].assert_called_once()


@pytest.mark.asyncio
async def test_crash_after_successful_run_keeps_full_transcript():
    """A crash between the run and the invocation layer's bookkeeping used
    to overwrite the session with the older live checkpoint; the boundary
    save now stands (no partial fallback runs at all)."""
    capture = {}
    result = MagicMock()
    result.output = "subagent response"
    # First call feeds the boundary save; second (invocation layer) crashes.
    result.all_messages = MagicMock(
        side_effect=[["m1", "m2", "m3"], RuntimeError("post-run bookkeeping crash")]
    )

    async def run_through_capability(*_args, **_kwargs):
        cap = _capability_from(capture)

        async def produce():
            return result

        return await cap.wrap_run(None, handler=produce)

    output = await _drive_invocation(capture, run_through_capability)

    assert output.error is not None
    cap = _capability_from(capture)
    assert cap.final_saved is True
    assert cap.recorded_save() == (True, 3)
    capture["save"].assert_called_once()
    capture["partial"].assert_not_called()


@pytest.mark.asyncio
async def test_failure_without_boundary_falls_back_to_eager_partial_save():
    """When the run fails without the capability ever running (a guest
    wrapper bypassing capabilities, or a failure before the run proper),
    the eager partial-save path takes over."""
    capture = {}

    output = await _drive_invocation(capture, RuntimeError("guest run exploded"))

    assert output.error is not None
    cap = _capability_from(capture)
    assert cap.recorded_save() == (False, None)
    capture["partial"].assert_called_once()
    capture["save"].assert_not_called()


def test_main_builder_does_not_carry_subagent_persistence():
    """The capability is sub-agent-only: main-agent sessions are persisted
    by the autosave pipeline, not at the pydantic-ai run boundary."""
    import code_puppy.agents._builder as builder

    source = inspect.getsource(builder)
    assert "SubagentSessionPersistence" not in source
