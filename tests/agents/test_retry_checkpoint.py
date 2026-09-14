"""No-progress retries must spend their budget, not manufacture user turns."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from code_puppy.agents.retry_checkpoint import RetryCheckpoint, resumable_call
from code_puppy.agents._runtime import streaming_retry


async def test_repeated_failures_exhaust_budget_without_duplicate_prompts():
    agent = SimpleNamespace(_message_history=[])
    prompts = []

    async def run(prompt, message_history):
        prompts.append(prompt)
        if prompt is not None:
            message_history.append(ModelRequest(parts=[UserPromptPart(prompt)]))
        raise ConnectionError("broken stream")

    checkpoint = RetryCheckpoint(agent)
    call = resumable_call(agent, SimpleNamespace(run=run), "continue")
    with (
        patch("code_puppy.agents._runtime.should_retry_streaming", return_value=True),
        patch("code_puppy.agents._runtime.asyncio.sleep", new_callable=AsyncMock),
        patch("code_puppy.error_logging.log_error"),
        patch("code_puppy.agents._runtime.emit_warning") as warning,
        patch("code_puppy.agents._runtime.emit_error"),
    ):
        wrapped = streaming_retry(
            max_attempts=5,
            delays=[1, 2, 3],
            progress_fn=checkpoint.progress,
            max_total_attempts=200,
        )(call)
        with pytest.raises(ConnectionError):
            await wrapped()
    assert prompts == ["continue", None, None, None, None]
    assert len(agent._message_history) == 1
    assert checkpoint.progress() == 0
    assert "streak 4/5" in warning.call_args.args[0]


async def test_failure_before_checkpoint_resends_prompt():
    agent = SimpleNamespace(_message_history=[])
    run = AsyncMock(side_effect=ConnectionError)
    call = resumable_call(agent, SimpleNamespace(run=run), "continue")
    for _ in range(2):
        with pytest.raises(ConnectionError):
            await call()
    assert [c.args[0] for c in run.call_args_list] == ["continue", "continue"]


def test_progress_ignores_requests_and_survives_compaction():
    agent = SimpleNamespace(_message_history=[])
    checkpoint = RetryCheckpoint(agent)
    agent._message_history.append(ModelRequest(parts=[UserPromptPart("continue")]))
    assert checkpoint.progress() == 0
    response = ModelResponse(parts=[TextPart("completed step")])
    agent._message_history.append(response)
    assert checkpoint.progress() == 1
    agent._message_history.clear()
    assert checkpoint.progress() == 1
    agent._message_history.append(response)
    assert checkpoint.progress() == 1
    agent._message_history.append(ModelResponse(parts=[TextPart("next step")]))
    assert checkpoint.progress() == 2


async def test_new_logical_turn_can_repeat_same_prompt():
    agent = SimpleNamespace(_message_history=[])

    async def run(prompt, **kwargs):
        agent._message_history.append(ModelRequest(parts=[UserPromptPart(prompt)]))

    for _ in range(2):
        await resumable_call(agent, SimpleNamespace(run=run), "continue")()
    assert len(agent._message_history) == 2
