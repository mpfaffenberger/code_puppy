from code_puppy.api.permission_plugin import (
    get_suppress_emitter_tool_events,
    get_websocket_context,
)
from code_puppy.api.ws.chat_context import (
    begin_agent_run_context,
    cleanup_agent_run_context,
    cleanup_message_context,
    setup_message_context,
)
from code_puppy.plugins.frontend_emitter.session_context import (
    current_emitter_session_id,
)


def test_setup_and_cleanup_message_context():
    calls = []

    setup_message_context(websocket="ws-obj", session_id="session-123")
    assert get_websocket_context() == ("ws-obj", "session-123")

    cleanup_message_context(
        clear_session_working_directory=lambda: calls.append("cleared")
    )
    assert get_websocket_context() is None
    assert calls == ["cleared"]


def test_begin_and_cleanup_agent_run_context_resets_all_contextvars():
    calls = []
    assert current_emitter_session_id.get() is None
    assert get_suppress_emitter_tool_events() is False

    run_context = begin_agent_run_context(session_id="session-abc")

    assert get_suppress_emitter_tool_events() is True
    assert current_emitter_session_id.get() == "session-abc"

    cleanup_agent_run_context(
        run_context,
        clear_session_working_directory=lambda: calls.append("cleared"),
    )

    assert get_suppress_emitter_tool_events() is False
    assert current_emitter_session_id.get() is None
    assert get_websocket_context() is None
    assert calls == ["cleared"]


def test_cleanup_agent_run_context_accepts_none_context():
    calls = []
    cleanup_agent_run_context(
        None,
        clear_session_working_directory=lambda: calls.append("cleared"),
    )
    assert get_suppress_emitter_tool_events() is False
    assert get_websocket_context() is None
    assert calls == ["cleared"]
