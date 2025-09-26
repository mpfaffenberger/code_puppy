from __future__ import annotations

from contextlib import ExitStack
from typing import Iterable, List
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from code_puppy.message_history_processor import (
    filter_huge_messages,
    message_history_processor,
    prune_interrupted_tool_calls,
    summarize_messages,
)
from code_puppy.state_management import hash_message


@pytest.fixture(autouse=True)
def silence_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("emit_info", "emit_warning", "emit_error"):
        monkeypatch.setattr(
            "code_puppy.message_history_processor." + name,
            lambda *args, **kwargs: None,
        )


def make_request(text: str) -> ModelRequest:
    return ModelRequest(parts=[TextPart(text)])


def make_response(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def test_prune_interrupted_tool_calls_keeps_delta_pairs() -> None:
    call_id = "call-1"
    delta_id = "delta-1"

    tool_call = ModelResponse(
        parts=[ToolCallPart(tool_name="runner", args={"cmd": "ls"}, tool_call_id=call_id)]
    )
    orphan = ModelResponse(
        parts=[ToolCallPart(tool_name="lost", args={}, tool_call_id="orphan")]
    )
    delta_sequence = ModelResponse(
        parts=[
            ToolCallPartDelta(tool_call_id=delta_id, tool_name_delta="runner"),
            ToolReturnPart(tool_name="runner", tool_call_id=delta_id, content="delta ok"),
        ]
    )
    tool_return = ModelResponse(
        parts=[ToolReturnPart(tool_name="runner", tool_call_id=call_id, content="done")]
    )

    pruned = prune_interrupted_tool_calls(
        [tool_call, orphan, delta_sequence, tool_return]
    )

    assert orphan not in pruned  # orphan should be dropped
    assert tool_call in pruned
    assert tool_return in pruned
    assert delta_sequence in pruned  # delta pair survives intact


def test_filter_huge_messages_preserves_system_and_discards_giant_payload() -> None:
    system = make_request("S" * 210_000)
    huge_user = make_request("U" * 210_000)
    normal_user = make_request("hi")

    filtered = filter_huge_messages([system, huge_user, normal_user])

    assert filtered[0] is system  # system prompt always retained
    assert normal_user in filtered
    assert huge_user not in filtered


def test_summarize_messages_wraps_non_list_output(monkeypatch: pytest.MonkeyPatch) -> None:
    system = make_request("system instructions")
    old = make_request("old message" * 40)
    recent = make_request("recent message")

    monkeypatch.setattr(
        "code_puppy.message_history_processor.get_protected_token_count",
        lambda: 10,
    )
    monkeypatch.setattr(
        "code_puppy.message_history_processor.run_summarization_sync",
        lambda *_args, **_kwargs: "• summary line",
    )

    compacted, summarized_source = summarize_messages(
        [system, old, recent], with_protection=True
    )

    assert compacted[0] is system
    assert compacted[-1] is recent
    assert compacted[1].parts[0].content == "• summary line"
    assert summarized_source == [old]


def test_summarize_messages_without_work_returns_original() -> None:
    system = make_request("system")
    compacted, summarized_source = summarize_messages([system], with_protection=True)

    assert compacted == [system]
    assert summarized_source == []


def test_message_history_processor_cleans_without_compaction(monkeypatch: pytest.MonkeyPatch) -> None:
    system = make_request("system")
    call_id = "tool-1"
    tool_call = ModelResponse(
        parts=[ToolCallPart(tool_name="shell", args={}, tool_call_id=call_id)]
    )
    tool_returns = ModelResponse(
        parts=[
            ToolReturnPart(tool_name="shell", tool_call_id=call_id, content="1"),
            ToolReturnPart(tool_name="shell", tool_call_id=call_id, content="duplicate"),
        ]
    )
    orphan = ModelResponse(
        parts=[ToolCallPart(tool_name="lost", args={}, tool_call_id="orphan")]
    )
    recent = make_request("recent")
    history = [system, tool_call, tool_returns, orphan, recent]

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_model_context_length",
                return_value=10_000,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_compaction_threshold",
                return_value=10.0,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_compaction_strategy",
                return_value="summarization",
            )
        )
        stack.enter_context(
            patch("code_puppy.tui_state.is_tui_mode", return_value=False)
        )
        stack.enter_context(
            patch("code_puppy.tui_state.get_tui_app_instance", return_value=None)
        )
        mock_set_history = stack.enter_context(
            patch("code_puppy.message_history_processor.set_message_history")
        )
        mock_add_hash = stack.enter_context(
            patch("code_puppy.message_history_processor.add_compacted_message_hash")
        )

        result = message_history_processor(history)

    assert mock_set_history.call_args[0][0] == result
    assert orphan not in result
    assert not mock_add_hash.call_args_list


def test_message_history_processor_integration_with_loaded_context(monkeypatch: pytest.MonkeyPatch) -> None:
    system = make_request("system instructions")
    old_user = make_request("old user message" * 3)
    old_assistant = make_response("assistant response" * 2)

    call_id = "tool-call"
    tool_call = ModelResponse(
        parts=[ToolCallPart(tool_name="shell", args={"cmd": "ls"}, tool_call_id=call_id)]
    )
    duplicated_return = ModelResponse(
        parts=[
            ToolReturnPart(tool_name="shell", tool_call_id=call_id, content="stdout"),
            ToolReturnPart(tool_name="shell", tool_call_id=call_id, content="duplicate"),
        ]
    )
    orphan_call = ModelResponse(
        parts=[ToolCallPart(tool_name="lost", args={}, tool_call_id="orphan")]
    )
    delta_pair = ModelResponse(
        parts=[
            ToolCallPartDelta(tool_call_id="delta", tool_name_delta="shell"),
            ToolReturnPart(tool_name="shell", tool_call_id="delta", content="delta ok"),
        ]
    )
    huge_payload = make_request("x" * 200_100)
    recent_user = make_request("recent user ping")

    history = [
        system,
        old_user,
        old_assistant,
        tool_call,
        duplicated_return,
        orphan_call,
        delta_pair,
        huge_payload,
        recent_user,
    ]

    captured_summary_input: List[ModelMessage] = []

    def fake_summarizer(_instructions: str, message_history: Iterable[ModelMessage]):
        captured_summary_input[:] = list(message_history)
        return [ModelRequest(parts=[TextPart("• summarized context")])]

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_model_context_length",
                return_value=100,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_compaction_threshold",
                return_value=0.05,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_compaction_strategy",
                return_value="summarization",
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.get_protected_token_count",
                return_value=25,
            )
        )
        stack.enter_context(
            patch("code_puppy.tui_state.is_tui_mode", return_value=False)
        )
        stack.enter_context(
            patch("code_puppy.tui_state.get_tui_app_instance", return_value=None)
        )
        stack.enter_context(
            patch(
                "code_puppy.message_history_processor.run_summarization_sync",
                side_effect=fake_summarizer,
            )
        )
        mock_set_history = stack.enter_context(
            patch("code_puppy.message_history_processor.set_message_history")
        )
        mock_add_hash: MagicMock = stack.enter_context(
            patch("code_puppy.message_history_processor.add_compacted_message_hash")
        )

        result = message_history_processor(history)

    # system prompt preserved and summary inserted
    assert result[0] is system
    assert result[1].parts[0].content == "• summarized context"
    assert recent_user in result
    assert delta_pair in result

    # orphan call removed, huge payload filtered prior to compaction
    assert orphan_call not in result
    assert huge_payload not in result

    # Summaries target only the expected older messages
    summarized_ids = {id(msg) for msg in captured_summary_input}
    tool_pair_present = id(tool_call) in summarized_ids or id(duplicated_return) in summarized_ids
    assert tool_pair_present
    assert id(old_user) in summarized_ids
    assert id(old_assistant) in summarized_ids
    assert id(delta_pair) not in summarized_ids
    assert id(recent_user) not in summarized_ids

    expected_hashes = [hash_message(msg) for msg in captured_summary_input]
    recorded_hashes = [call.args[0] for call in mock_add_hash.call_args_list]
    assert recorded_hashes == expected_hashes
    assert mock_set_history.call_args[0][0] == result
