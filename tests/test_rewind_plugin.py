from unittest.mock import MagicMock, patch

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.plugins.rewind.history import rewind_history
from code_puppy.plugins.rewind.register_callbacks import (
    _handle_custom_command,
    _parse_rewind_count,
)


def request(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def response(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def system(text: str = "system") -> ModelRequest:
    return ModelRequest(parts=[SystemPromptPart(content=text)])


def flatten_history_text(history) -> str:
    chunks = []
    for message in history:
        for part in getattr(message, "parts", []) or []:
            chunks.append(str(getattr(part, "content", "")))
            chunks.append(str(getattr(part, "args", "")))
    return "\n".join(chunks)


def test_baseline_history_keeps_prior_user_fact_without_rewind():
    history = [
        system(),
        request("what's 5+5"),
        response("10"),
        request("my name is john"),
        response("Nice to meet you, John."),
        request("what is my name"),
    ]

    assert "my name is john" in flatten_history_text(history)
    assert "John" in flatten_history_text(history)


def test_rewind_one_turn_removes_fact_before_next_question():
    history = [
        system(),
        request("what's 5+5"),
        response("10"),
        request("my name is john"),
        response("Nice to meet you, John."),
    ]

    result = rewind_history(history, 1)
    next_request_history = [*result.history, request("what is my name?")]

    assert result.rewound_turns == 1
    assert "my name is john" not in flatten_history_text(next_request_history)
    assert "Nice to meet you, John." not in flatten_history_text(next_request_history)
    assert "what is my name?" in flatten_history_text(next_request_history)


def test_rewind_removes_full_tool_component_turn_from_next_model_request():
    history = [
        system(),
        request("safe earlier fact"),
        response("kept"),
        request("latest turn with secret attachment: john"),
        ModelResponse(
            parts=[
                TextPart(content="I'll inspect that."),
                ToolCallPart(
                    tool_name="read_file",
                    args={"file_path": "john-secret.txt"},
                    tool_call_id="call-1",
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="read_file",
                    content="oversized context window poison john",
                    tool_call_id="call-1",
                )
            ]
        ),
        response("Tool result says john."),
    ]

    result = rewind_history(history, 1)
    next_request_history = [*result.history, request("continue")]
    text = flatten_history_text(next_request_history)

    assert result.removed_messages == 4
    assert "safe earlier fact" in text
    assert "latest turn with secret attachment" not in text
    assert "john-secret.txt" not in text
    assert "oversized context window poison john" not in text
    assert "Tool result says john" not in text


def test_rewind_recovers_from_oversized_latest_turn():
    poison = "TOO_BIG " * 20_000
    history = [system(), request("small ok"), response("ok"), request(poison)]

    result = rewind_history(history, 1)
    next_request_history = [*result.history, request("now answer normally")]

    assert poison not in flatten_history_text(next_request_history)
    assert "small ok" in flatten_history_text(next_request_history)


def test_rewind_two_turns_and_never_removes_system_message():
    history = [
        system("do not remove me"),
        request("turn one"),
        response("one"),
        request("turn two"),
        response("two"),
    ]

    result = rewind_history(history, 2)

    assert result.rewound_turns == 2
    assert result.history == [history[0]]
    assert "do not remove me" in flatten_history_text(result.history)


def test_rewind_more_turns_than_exist_removes_safely_available_turns():
    history = [system(), request("only turn"), response("only response")]

    result = rewind_history(history, 99)

    assert result.rewound_turns == 1
    assert result.requested_turns == 99
    assert result.history == [history[0]]


def test_rewind_with_no_completed_turns_does_not_crash():
    result = rewind_history([system()], 1)

    assert result.rewound_turns == 0
    assert len(result.history) == 1


def test_parse_rewind_defaults_to_one():
    assert _parse_rewind_count("/rewind") == 1


def test_parse_rewind_rejects_invalid_counts_without_mutation_path():
    with patch("code_puppy.messaging.emit_error") as emit_error:
        assert _parse_rewind_count("/rewind 0") is None
        assert _parse_rewind_count("/rewind -1") is None
        assert _parse_rewind_count("/rewind abc") is None

    assert emit_error.call_count == 3


def test_rewind_command_updates_active_agent_history():
    agent = MagicMock()
    history = [system(), request("name is john"), response("hi john")]
    agent.get_message_history.return_value = history

    with (
        patch(
            "code_puppy.agents.agent_manager.get_current_agent",
            return_value=agent,
        ),
        patch("code_puppy.messaging.emit_success") as emit_success,
    ):
        handled = _handle_custom_command("/rewind 1", "rewind")

    assert handled is True
    agent.set_message_history.assert_called_once_with([history[0]])
    emit_success.assert_called_once()


def test_rewind_command_invalid_count_does_not_mutate_history():
    agent = MagicMock()

    with (
        patch(
            "code_puppy.agents.agent_manager.get_current_agent",
            return_value=agent,
        ),
        patch("code_puppy.messaging.emit_error"),
    ):
        handled = _handle_custom_command("/rewind nope", "rewind")

    assert handled is True
    agent.set_message_history.assert_not_called()
