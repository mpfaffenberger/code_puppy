"""Unit tests for the steering history processor.

The processor drains ``PauseController``'s steer queue on every
``history_processors`` invocation and appends each pending steer as a
``UserPromptPart`` message. Because pydantic-ai calls history processors
before EVERY model invocation (including between tool calls within a
single ``agent.run()``), this is what makes mid-turn steering Just Work.
"""

from __future__ import annotations

from typing import List
from unittest.mock import Mock

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from code_puppy.agents._steer_processor import make_steer_history_processor
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture(autouse=True)
def _reset_pause_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


def _make_agent_with_history(history: List[ModelMessage] | None = None) -> Mock:
    agent = Mock()
    agent._message_history = list(history or [])
    return agent


# =============================================================================
# Identity behaviour when nothing's queued
# =============================================================================


def test_no_pending_steers_returns_messages_unchanged():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    messages: List[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="original")])
    ]

    result = proc(messages)

    assert result == messages
    # Must NOT mutate _message_history when nothing is queued.
    assert agent._message_history == []


# =============================================================================
# Single steer injection
# =============================================================================


def test_single_steer_appended_as_user_message():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer("change strategy please")

    original: List[ModelMessage] = []
    result = proc(original)

    assert len(result) == 1
    appended = result[0]
    assert isinstance(appended, ModelRequest)
    assert len(appended.parts) == 1
    part = appended.parts[0]
    assert isinstance(part, UserPromptPart)
    assert part.content == "change strategy please"


def test_steer_appended_after_existing_messages():
    """Order matters: existing history first, then steers."""
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    existing = ModelRequest(parts=[UserPromptPart(content="hello")])
    get_pause_controller().request_steer("pivot")

    result = proc([existing])

    assert len(result) == 2
    assert result[0] is existing
    assert isinstance(result[1], ModelRequest)
    assert result[1].parts[0].content == "pivot"


# =============================================================================
# Multiple steers — each becomes a discrete turn
# =============================================================================


def test_multiple_steers_appended_as_separate_user_messages():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    pc = get_pause_controller()
    pc.request_steer("first")
    pc.request_steer("second")
    pc.request_steer("third")

    result = proc([])

    assert len(result) == 3
    contents = [r.parts[0].content for r in result]
    assert contents == ["first", "second", "third"]
    # Each is its own ModelRequest (NOT concatenated into one).
    assert all(isinstance(m, ModelRequest) for m in result)


# =============================================================================
# Queue lifecycle
# =============================================================================


def test_processor_drains_the_queue():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    pc = get_pause_controller()
    pc.request_steer("eat me")

    proc([])

    # Queue must be empty post-call so the next history-processor invocation
    # doesn't double-inject.
    assert pc.drain_pending_steer() == []


def test_second_call_with_empty_queue_is_a_noop():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    pc = get_pause_controller()
    pc.request_steer("only this once")

    first = proc([])
    second = proc(first)

    assert len(first) == 1
    assert second == first  # nothing new appended


# =============================================================================
# agent._message_history mirroring
# =============================================================================


def test_processor_mirrors_into_agent_message_history():
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer("persist me")

    proc([])

    assert len(agent._message_history) == 1
    assert isinstance(agent._message_history[0], ModelRequest)
    assert agent._message_history[0].parts[0].content == "persist me"


def test_processor_appends_to_existing_message_history():
    existing_msg = ModelRequest(parts=[UserPromptPart(content="prior")])
    agent = _make_agent_with_history([existing_msg])
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer("new")

    proc([])

    assert len(agent._message_history) == 2
    assert agent._message_history[0] is existing_msg
    assert agent._message_history[1].parts[0].content == "new"


def test_processor_with_no_agent_message_history_attribute():
    """Defensive: agent without ``_message_history`` must NOT crash."""

    class _BareAgent:
        pass

    agent = _BareAgent()
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer("hi")

    # Must not raise.
    result = proc([])
    assert len(result) == 1


# =============================================================================
# Diagnostics
# =============================================================================


def test_processor_emits_preview_info_message(monkeypatch):
    infos: List[str] = []
    monkeypatch.setattr(
        "code_puppy.agents._steer_processor.emit_info",
        lambda msg, *_a, **_k: infos.append(msg),
    )

    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer("rewrite in rust")

    proc([])

    assert any("Injecting steer mid-turn" in m for m in infos)
    assert any("rewrite in rust" in m for m in infos)


def test_processor_truncates_long_previews(monkeypatch):
    """Steer previews longer than 80 chars get an ellipsis."""
    infos: List[str] = []
    monkeypatch.setattr(
        "code_puppy.agents._steer_processor.emit_info",
        lambda msg, *_a, **_k: infos.append(msg),
    )

    long_steer = "x" * 200
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    get_pause_controller().request_steer(long_steer)

    proc([])

    msg = next(m for m in infos if "Injecting steer" in m)
    assert "..." in msg
    # The original steer message is preserved in the actual ModelRequest.
    # (The preview is only for the emit_info diagnostic.)


# =============================================================================
# Mode isolation — processor MUST NOT drain queue-mode steers
# =============================================================================


def test_processor_drains_only_now_mode_steers():
    """The history processor owns ``now``-mode steers exclusively.
    ``queue``-mode steers belong to ``_runtime._do_run``'s between-turns
    loop — if the processor drains them too, they'd never reach the
    runtime and would either be lost or double-injected.
    """
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    pc = get_pause_controller()
    pc.request_steer("inject mid-turn", mode="now")
    pc.request_steer("inject after turn", mode="queue")

    result = proc([])

    # Only the now-mode steer should have been injected.
    assert len(result) == 1
    assert result[0].parts[0].content == "inject mid-turn"

    # The queue-mode steer MUST still be in its queue.
    assert pc.has_pending_steer_queued() is True
    assert pc.drain_pending_steer_queued() == ["inject after turn"]


def test_processor_with_only_queue_mode_steers_is_noop():
    """When only queue-mode steers exist, the processor is a no-op."""
    agent = _make_agent_with_history()
    proc = make_steer_history_processor(agent)
    pc = get_pause_controller()
    pc.request_steer("for the runtime, not me", mode="queue")

    result = proc([])

    assert result == []
    # Queue-mode steer is untouched.
    assert pc.drain_pending_steer_queued() == ["for the runtime, not me"]
