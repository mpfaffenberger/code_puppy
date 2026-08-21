"""Unit tests for the SteerInjection capability (code_puppy.agents._steering).

Locks the contracts the old ``make_steer_history_processor`` closure carried,
now expressed as a pydantic-ai capability:

- empty queue is a strict no-op
- each steer becomes a discrete ModelRequest appended AFTER existing messages
- the in-effect instructions are carried onto injected requests
- injected messages are mirrored into the host's durable history
- the drain seam only touches the queue the capability owns
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents._steering import SteerInjection, build_steer_injection


def _request_context(messages):
    """Duck-typed ModelRequestContext: the capability only touches .messages."""
    return SimpleNamespace(messages=messages)


def _steer(capability, messages):
    """Fire before_model_request and return the outbound message list."""
    import asyncio

    ctx = _request_context(messages)
    return asyncio.run(capability.before_model_request(Mock(), ctx)).messages


def test_is_a_capability():
    assert issubclass(SteerInjection, AbstractCapability)
    assert SteerInjection.get_serialization_name() is None


def test_empty_queue_is_a_noop():
    mirror = Mock()
    capability = SteerInjection(drain=lambda: [], mirror=mirror)
    original = [ModelRequest(parts=[UserPromptPart(content="hi")])]

    result = _steer(capability, original)

    assert result is original  # untouched, not even copied
    mirror.assert_not_called()


def test_steers_append_after_existing_messages():
    capability = SteerInjection(drain=lambda: ["go left", "no wait, right"])
    existing = [ModelRequest(parts=[UserPromptPart(content="original ask")])]

    result = _steer(capability, existing)

    assert len(result) == 3
    assert result[0] is existing[0]
    assert result[1].parts[0].content == "go left"
    assert result[2].parts[0].content == "no wait, right"
    for injected in result[1:]:
        assert isinstance(injected, ModelRequest)
        assert isinstance(injected.parts[0], UserPromptPart)


def test_instructions_carried_from_most_recent_request():
    """pydantic-ai resolves the system prompt from the MOST RECENT
    ModelRequest; a None-instructions injection silently drops it."""
    capability = SteerInjection(drain=lambda: ["steer me"])
    existing = [
        ModelRequest(
            parts=[UserPromptPart(content="old")], instructions="be a good dog"
        ),
        ModelRequest(parts=[UserPromptPart(content="newer, no instructions")]),
    ]

    result = _steer(capability, existing)

    assert result[-1].instructions == "be a good dog"


def test_no_instructions_anywhere_stays_none():
    capability = SteerInjection(drain=lambda: ["steer me"])

    result = _steer(capability, [ModelRequest(parts=[UserPromptPart(content="x")])])

    assert result[-1].instructions is None


def test_mirror_receives_only_injected_messages():
    seen = []
    capability = SteerInjection(drain=lambda: ["a", "b"], mirror=seen.extend)
    existing = [ModelRequest(parts=[UserPromptPart(content="original")])]

    result = _steer(capability, existing)

    assert len(seen) == 2
    assert seen == result[1:]


def test_build_steer_injection_mirrors_into_agent_history():
    agent = Mock()
    agent._message_history = [ModelRequest(parts=[UserPromptPart(content="turn 1")])]
    capability = build_steer_injection(agent)
    capability.drain = lambda: ["persist me"]

    _steer(capability, [])

    assert len(agent._message_history) == 2
    assert agent._message_history[1].parts[0].content == "persist me"


def test_build_steer_injection_tolerates_agents_without_history():
    agent = SimpleNamespace()  # no _message_history attribute
    capability = build_steer_injection(agent)
    capability.drain = lambda: ["no crash please"]

    result = _steer(capability, [])

    assert len(result) == 1  # injection still happens; mirroring is skipped


def test_default_drain_uses_now_queue_only():
    """The capability drains ONLY now-mode steers; queue-mode belongs to the
    runtime's between-turns loop (draining both would double-inject)."""
    from code_puppy.messaging.pause_controller import get_pause_controller

    controller = get_pause_controller()
    # Clean slate: drain whatever previous tests left behind.
    controller.drain_pending_steer_now()
    controller.drain_pending_steer_queued()

    controller.request_steer("now steer", mode="now")
    controller.request_steer("queued steer", mode="queue")
    try:
        capability = SteerInjection()

        result = _steer(capability, [])

        assert len(result) == 1
        assert result[0].parts[0].content == "now steer"
        assert controller.peek_pending_steer_queued() == ["queued steer"]
    finally:
        controller.drain_pending_steer_now()
        controller.drain_pending_steer_queued()


@pytest.mark.asyncio
async def test_before_model_request_is_native_async():
    """The hook must be awaitable directly on the pydantic-ai seam."""
    capability = SteerInjection(drain=lambda: [])
    ctx = _request_context([])

    result = await capability.before_model_request(Mock(), ctx)

    assert result is ctx
