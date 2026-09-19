"""Steering injection changes model history, not the visible transcript."""

from types import SimpleNamespace
from unittest.mock import Mock

from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents import _steer_processor
from code_puppy.steer_metadata import STEER_METADATA


def test_steering_is_injected_silently(monkeypatch):
    controller = Mock()
    controller.drain_pending_steer_now.return_value = ["use accent colors"]
    monkeypatch.setattr(_steer_processor, "get_pause_controller", lambda: controller)
    monkeypatch.setattr(
        "code_puppy.agent_completion_inbox.pop_completion", lambda agent: None
    )
    content = ["use accent colors", "resolved attachment"]
    monkeypatch.setattr(
        _steer_processor, "resolve_steer_content", lambda text: (content, text)
    )
    emit = Mock()
    monkeypatch.setattr("code_puppy.messaging.message_queue.emit_message", emit)
    original = ModelRequest(parts=[UserPromptPart(content="hello")], instructions="rules")
    agent = SimpleNamespace(_message_history=[original])
    result = _steer_processor.make_steer_history_processor(agent)([original])
    assert len(result) == 2
    assert result[-1].parts[0].content == content
    assert result[-1].instructions == "rules"
    assert result[-1].metadata == STEER_METADATA
    assert agent._message_history == result
    emit.assert_not_called()


def test_queued_steering_is_silent_and_preserves_leftovers(monkeypatch):
    from code_puppy.agents import _run_signals

    controller = Mock()
    controller.drain_pending_steer_queued.return_value = ["first", "second"]
    monkeypatch.setattr(
        "code_puppy.messaging.pause_controller.get_pause_controller", lambda: controller
    )
    monkeypatch.setattr(
        "code_puppy.agent_completion_inbox.pop_completion", lambda agent: None
    )
    content = ["first", "attachment"]
    monkeypatch.setattr(
        _run_signals, "resolve_steer_content", lambda text: (content, text)
    )
    emit = Mock()
    monkeypatch.setattr(_run_signals, "emit_info", emit)
    agent = SimpleNamespace(_message_history=[])
    result = Mock()
    result.all_messages.return_value = ["completed history"]
    assert _run_signals.prepare_queued_steer_injection(agent, result) == content
    assert agent._message_history == ["completed history"]
    controller.request_steer.assert_called_once_with("second", mode="queue")
    emit.assert_not_called()
