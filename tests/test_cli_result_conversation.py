"""Tests for ``--result-conversation``: headless conversation export (#366)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.cli_runner import execute_single_prompt, main
from code_puppy.session_storage import (
    ENCODING_MESSAGES,
    decode_envelope,
    export_conversation,
    read_envelope_file,
)


def _conversation() -> list[ModelRequest | ModelResponse]:
    return [
        ModelRequest(parts=[UserPromptPart(content="refactor utils.py")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="read_file",
                    args={"file_path": "utils.py"},
                    tool_call_id="call-1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="read_file", content="def f(): ...", tool_call_id="call-1"
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content="done")]),
    ]


def test_export_conversation_round_trips_as_session_envelope(tmp_path):
    target = tmp_path / "nested" / "run-001.json"
    history = _conversation()

    export_conversation(target, history)

    envelope = read_envelope_file(target)
    assert envelope["encoding"] == ENCODING_MESSAGES
    assert decode_envelope(envelope) == history
    assert list(target.parent.glob("*.tmp")) == []


@pytest.mark.anyio
async def test_execute_single_prompt_exports_full_conversation(tmp_path):
    target = tmp_path / "run.json"
    history = _conversation()
    result = MagicMock(output="done")
    result.all_messages.return_value = history

    with (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="refactor utils.py"),
        ),
        patch("code_puppy.cli_runner.get_current_agent", return_value=MagicMock()),
        patch(
            "code_puppy.cli_runner.run_prompt_with_attachments",
            new=AsyncMock(return_value=(result, MagicMock())),
        ),
        patch("code_puppy.messaging.get_message_bus"),
        patch("code_puppy.session_lifecycle.persist_named_session"),
        patch("code_puppy.config.record_quick_resume_sessions"),
    ):
        await execute_single_prompt(
            "refactor utils.py", MagicMock(), conversation_file=target
        )

    messages = json.loads(target.read_text())["messages"]
    assert [message["kind"] for message in messages] == [
        "request",
        "response",
        "request",
        "response",
    ]
    assert messages[1]["parts"][0]["tool_name"] == "read_file"


@pytest.mark.anyio
async def test_result_conversation_without_prompt_is_a_usage_error(tmp_path):
    argv = ["code-puppy", "--result-conversation", str(tmp_path / "run.json")]

    with patch("sys.argv", argv), pytest.raises(SystemExit) as exit_info:
        await main()

    assert exit_info.value.code == 2
