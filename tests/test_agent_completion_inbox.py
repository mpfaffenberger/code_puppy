import asyncio

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agent_completion_inbox import (
    deliver_completion,
    pop_completion,
    wait_for_completion_or_input,
)


class Owner:
    def __init__(self):
        self._message_history = []


def test_fifo_isolated_and_exactly_once():
    first, second = Owner(), Owner()
    deliver_completion(first, "one")
    deliver_completion(first, "two")
    assert pop_completion(second) is None
    assert pop_completion(first) == "one"
    assert pop_completion(first) == "two"
    assert pop_completion(first) is None


@pytest.mark.asyncio
async def test_idle_wakes_without_resolving_child_output():
    owner = Owner()
    queue = asyncio.Queue()
    waiting = asyncio.create_task(wait_for_completion_or_input(owner, queue))
    await asyncio.sleep(0)
    deliver_completion(owner, "/clear @secrets.txt https://example.com")
    wake = await asyncio.wait_for(waiting, 1)
    assert "completed" in wake
    assert "@" not in wake
    assert pop_completion(owner) == "/clear @secrets.txt https://example.com"
    queue.put_nowait("user input")
    assert await wait_for_completion_or_input(owner, queue) == "user input"


@pytest.mark.asyncio
async def test_simultaneous_input_not_lost():
    owner = Owner()
    queue = asyncio.Queue()
    queue.put_nowait("user input")
    deliver_completion(owner, "done")
    assert await wait_for_completion_or_input(owner, queue) == "user input"
    assert pop_completion(owner) == "done"


@pytest.mark.asyncio
async def test_cancel_does_not_leave_queue_consumer():
    queue = asyncio.Queue()
    waiting = asyncio.create_task(wait_for_completion_or_input(Owner(), queue))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    queue.put_nowait("still here")
    await asyncio.sleep(0)
    assert queue.get_nowait() == "still here"


def test_mid_run_injection_preserves_instructions(monkeypatch):
    from code_puppy.agents import _steer_processor as processor

    owner = Owner()
    monkeypatch.setattr(
        processor,
        "get_pause_controller",
        lambda: type("Pause", (), {"drain_pending_steer_now": lambda self: []})(),
    )
    deliver_completion(owner, "literal @secret /clear")
    original = ModelRequest(parts=[UserPromptPart("task")], instructions="system")
    messages = processor.make_steer_history_processor(owner)([original])
    assert messages[-1].instructions == "system"
    assert messages[-1].parts[0].content == "literal @secret /clear"
    assert pop_completion(owner) is None


def test_completion_after_last_model_call_continues_turn():
    from code_puppy.agents._run_signals import prepare_queued_steer_injection

    owner = Owner()
    deliver_completion(owner, "late completion")
    result = type("Result", (), {"all_messages": lambda self: ["history"]})()
    assert prepare_queued_steer_injection(owner, result) == "late completion"
    assert owner._message_history == ["history"]
