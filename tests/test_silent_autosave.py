"""Autosave persists history and fires hooks without transcript chatter."""

from unittest.mock import Mock

from code_puppy import config


def test_autosave_success_is_silent(monkeypatch):
    agent = Mock()
    agent.get_message_history.return_value = ["history"]
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent", lambda: agent
    )
    monkeypatch.setattr(config, "get_current_session_name", lambda: "test-session")
    save = Mock()
    record = Mock()
    hook = Mock()
    emit = Mock()
    monkeypatch.setattr(config, "save_session", save)
    monkeypatch.setattr(config, "record_quick_resume_sessions", record)
    monkeypatch.setattr(
        "code_puppy.session_lifecycle.fire_post_autosave_callback", hook
    )
    monkeypatch.setattr("code_puppy.messaging.emit_info", emit)
    assert config.auto_save_session_if_enabled(force=True)
    save.assert_called_once()
    assert save.call_args.kwargs["history"] == ["history"]
    record.assert_called_once_with("test-session")
    hook.assert_called_once_with(save.return_value)
    emit.assert_not_called()
