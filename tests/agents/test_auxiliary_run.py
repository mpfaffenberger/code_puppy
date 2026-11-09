"""Regression tests for direct auxiliary model lifecycle isolation."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from code_puppy import callbacks
from code_puppy.agents import _auxiliary_run, _runtime, run_stats
from code_puppy.agents.run_stats import AgentRunStats


@pytest.fixture(autouse=True)
def reset_stats():
    AgentRunStats.reset_conversation_stats()
    AgentRunStats.reset_cycle_state()
    yield
    AgentRunStats.reset_conversation_stats()
    AgentRunStats.reset_cycle_state()


async def test_auxiliary_lifecycle_preserves_live_main_run_stats(monkeypatch):
    AgentRunStats.mark_request_start(model_name="main-model")
    AgentRunStats.record_output_tokens(400)
    end_events = []
    observed_scopes = []

    async def submit(prompt, _session_id):
        observed_scopes.append(callbacks.is_auxiliary_agent_run())
        return prompt

    async def start(**kwargs):
        observed_scopes.append(callbacks.is_auxiliary_agent_run())
        await run_stats._on_agent_run_start(**kwargs)

    async def end(**kwargs):
        observed_scopes.append(callbacks.is_auxiliary_agent_run())
        end_events.append(kwargs)
        await run_stats._on_agent_run_end(**kwargs)

    monkeypatch.setattr(_runtime, "apply_attachment_free_user_prompt_submit", submit)
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", start)
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", end)

    async def call(prompt):
        assert prompt == "question"
        return "answer"

    result = await _auxiliary_run.run_auxiliary_model_call(
        agent_name="btw",
        model_name="side-model",
        session_id="btw-session",
        prompt="question",
        call=call,
        response_text=lambda value: value,
    )

    assert result == "answer"
    assert observed_scopes == [True, True, True]
    assert AgentRunStats._output_tokens == 400
    assert AgentRunStats._current_model_name == "main-model"
    assert end_events[0]["metadata"] == {
        "status": "completed",
        "auxiliary_model_call": True,
    }


@pytest.mark.parametrize(
    ("failure", "status", "reported_error"),
    [
        (RuntimeError("boom"), "failed", "same"),
        (asyncio.CancelledError(), "cancelled", None),
        (KeyboardInterrupt(), "cancelled", None),
    ],
)
async def test_auxiliary_lifecycle_reports_failure_and_reraises(
    monkeypatch, failure, status, reported_error
):
    monkeypatch.setattr(
        _runtime,
        "apply_attachment_free_user_prompt_submit",
        AsyncMock(side_effect=lambda prompt, _session_id: prompt),
    )
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", AsyncMock())
    finished = AsyncMock()
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", finished)

    async def fail(_prompt):
        raise failure

    with pytest.raises(type(failure)):
        await _auxiliary_run.run_auxiliary_model_call(
            agent_name="btw",
            model_name="side-model",
            session_id="btw-session",
            prompt="question",
            call=fail,
            response_text=lambda value: value,
        )

    assert finished.await_args.kwargs["success"] is False
    expected_error = failure if reported_error == "same" else reported_error
    assert finished.await_args.kwargs["error"] is expected_error
    assert finished.await_args.kwargs["metadata"]["status"] == status


def test_auxiliary_context_is_nested_and_restored():
    assert callbacks.is_auxiliary_agent_run() is False
    with callbacks.auxiliary_agent_run_context():
        assert callbacks.is_auxiliary_agent_run() is True
        with callbacks.auxiliary_agent_run_context():
            assert callbacks.is_auxiliary_agent_run() is True
        assert callbacks.is_auxiliary_agent_run() is True
    assert callbacks.is_auxiliary_agent_run() is False


async def test_cancel_during_start_is_balanced_and_reraised(monkeypatch):
    events = []
    cancellation = asyncio.CancelledError("stop during start")

    async def submit(prompt, _session_id):
        return prompt

    async def cancel_start(**_kwargs):
        events.append("start")
        raise cancellation

    async def finish(**kwargs):
        events.append(("end", kwargs))

    monkeypatch.setattr(_runtime, "apply_attachment_free_user_prompt_submit", submit)
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", cancel_start)
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", finish)

    with pytest.raises(asyncio.CancelledError) as raised:
        await _auxiliary_run.run_auxiliary_model_call(
            agent_name="side",
            model_name="model",
            session_id="session",
            prompt="question",
            call=AsyncMock(return_value="unused"),
            response_text=str,
        )

    assert raised.value is cancellation
    assert events[0] == "start"
    terminal = events[1][1]
    assert terminal["error"] is None
    assert terminal["metadata"]["status"] == "cancelled"


async def test_prompt_submit_cancel_precedes_lifecycle(monkeypatch):
    cancellation = asyncio.CancelledError("stop during submit")
    started = AsyncMock()
    finished = AsyncMock()
    monkeypatch.setattr(
        _runtime,
        "apply_attachment_free_user_prompt_submit",
        AsyncMock(side_effect=cancellation),
    )
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", started)
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", finished)

    with pytest.raises(asyncio.CancelledError) as raised:
        await _auxiliary_run.run_auxiliary_model_call(
            agent_name="side",
            model_name="model",
            session_id="session",
            prompt="question",
            call=AsyncMock(return_value="unused"),
            response_text=str,
        )

    assert raised.value is cancellation
    started.assert_not_awaited()
    finished.assert_not_awaited()


@pytest.mark.parametrize("adapter", ["result_error", "response_text"])
async def test_terminal_adapter_failure_is_balanced_and_reraised(monkeypatch, adapter):
    failure = ValueError(f"{adapter} failed")
    finished = AsyncMock()
    monkeypatch.setattr(
        _runtime,
        "apply_attachment_free_user_prompt_submit",
        AsyncMock(side_effect=lambda prompt, _session_id: prompt),
    )
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", AsyncMock())
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", finished)

    def fail(_result):
        raise failure

    kwargs = {
        "result_error": fail if adapter == "result_error" else None,
        "response_text": fail if adapter == "response_text" else str,
    }
    with pytest.raises(ValueError) as raised:
        await _auxiliary_run.run_auxiliary_model_call(
            agent_name="side",
            model_name="model",
            session_id="session",
            prompt="question",
            call=AsyncMock(return_value="answer"),
            **kwargs,
        )

    assert raised.value is failure
    assert finished.await_count == 1
    assert finished.await_args.kwargs["error"] is failure
    assert finished.await_args.kwargs["metadata"]["status"] == "failed"


async def test_result_error_reports_failed_terminal_and_returns_result(monkeypatch):
    finished = AsyncMock()
    monkeypatch.setattr(
        _runtime,
        "apply_attachment_free_user_prompt_submit",
        AsyncMock(side_effect=lambda prompt, _session_id: prompt),
    )
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_start", AsyncMock())
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", finished)

    result = await _auxiliary_run.run_auxiliary_model_call(
        agent_name="fork",
        model_name="side-model",
        session_id="final-session",
        prompt="question",
        call=AsyncMock(return_value={"response": "partial", "error": "boom"}),
        response_text=lambda value: value["response"],
        result_error=lambda value: value["error"],
    )

    assert result == {"response": "partial", "error": "boom"}
    assert finished.await_count == 1
    terminal = finished.await_args.kwargs
    assert terminal["success"] is False
    assert str(terminal["error"]) == "boom"
    assert terminal["response_text"] == "partial"
    assert terminal["metadata"]["status"] == "failed"


async def test_real_start_dispatcher_failure_is_nonfatal_and_balanced(monkeypatch):
    events = []

    async def broken_start(*_args, **_kwargs):
        events.append("broken-start")
        raise RuntimeError("observer failed")

    async def capture_end(*args, **_kwargs):
        events.append(("end", args[3]))

    callbacks.register_callback("agent_run_start", broken_start)
    callbacks.register_callback("agent_run_end", capture_end)
    monkeypatch.setattr(
        _runtime,
        "apply_attachment_free_user_prompt_submit",
        AsyncMock(side_effect=lambda prompt, _session_id: prompt),
    )
    monkeypatch.setattr(
        _auxiliary_run, "on_agent_run_start", callbacks.on_agent_run_start
    )
    monkeypatch.setattr(_auxiliary_run, "on_agent_run_end", callbacks.on_agent_run_end)

    result = await _auxiliary_run.run_auxiliary_model_call(
        agent_name="side",
        model_name="model",
        session_id="session",
        prompt="question",
        call=AsyncMock(return_value="answer"),
        response_text=str,
    )

    assert result == "answer"
    assert events == ["broken-start", ("end", True)]
