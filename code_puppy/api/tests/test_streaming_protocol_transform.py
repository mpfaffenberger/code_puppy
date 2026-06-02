"""Tests for streaming-only assistant response protocol adaptation."""

from code_puppy.api.ws.response_frames import (
    build_assistant_text_stream_frames,
    build_error_response_frames,
)


def _dump_frames(**kwargs):
    return [
        frame.model_dump(exclude_none=True)
        for frame in build_assistant_text_stream_frames(**kwargs)
    ]


def test_complete_response_is_adapted_to_streaming_frames():
    frames = _dump_frames(
        response_text="hello from a non-streaming model",
        session_id="WS_session_test",
        agent_name="code-puppy",
        model_name="non-stream-model",
        tokens={"total_tokens": 7},
        message_id="msg-fixed",
        timestamp=123.456,
    )

    assert [frame["type"] for frame in frames] == [
        "assistant_message_start",
        "assistant_message_delta",
        "assistant_message_end",
        "stream_end",
    ]

    start, delta, end, stream_end = frames
    assert start == {
        "type": "assistant_message_start",
        "message_id": "msg-fixed",
        "part_type": "text",
        "part_index": 0,
        "timestamp": 123.456,
        "session_id": "WS_session_test",
        "agent_name": "code-puppy",
        "model_name": "non-stream-model",
    }
    assert delta["message_id"] == "msg-fixed"
    assert delta["content"] == "hello from a non-streaming model"
    assert delta["part_index"] == 0
    assert delta["session_id"] == "WS_session_test"

    assert end["message_id"] == "msg-fixed"
    assert end["part_type"] == "text"
    assert end["full_content"] == "hello from a non-streaming model"
    assert end["timestamp"] == 123.456

    assert stream_end == {
        "type": "stream_end",
        "success": True,
        "session_id": "WS_session_test",
        "total_length": len("hello from a non-streaming model"),
        "agent_name": "code-puppy",
        "model_name": "non-stream-model",
        "tokens": {"total_tokens": 7},
    }


def test_complete_response_transform_does_not_emit_legacy_response_frame():
    frames = _dump_frames(
        response_text="render me through streaming",
        session_id="WS_session_test",
        message_id="msg-fixed",
        timestamp=1.0,
    )

    assert "response" not in {frame["type"] for frame in frames}
    assert any(
        frame["type"] == "assistant_message_delta"
        and frame["content"] == "render me through streaming"
        for frame in frames
    )


def test_complete_response_transform_preserves_part_type_for_thinking_parts():
    frames = _dump_frames(
        response_text="reasoning trace",
        session_id="WS_session_test",
        part_type="thinking",
        part_index=1,
        message_id="thinking-fixed",
        timestamp=2.0,
    )

    assert frames[0]["part_type"] == "thinking"
    assert frames[1]["part_index"] == 1
    assert frames[2]["part_type"] == "thinking"
    assert frames[2]["part_index"] == 1
    assert frames[3]["type"] == "stream_end"


def test_error_after_partial_stream_emits_stream_end_then_error():
    frames = build_error_response_frames(
        RuntimeError("backend unavailable"),
        collected_text=["partial output"],
        session_id="WS_session_test",
    )

    assert frames[0]["type"] == "stream_end"
    assert frames[0]["success"] is False
    assert frames[1]["type"] == "error"
    assert frames[1]["session_id"] == "WS_session_test"


def test_response_frames_import_does_not_eagerly_load_chat_handler():
    import importlib
    import sys

    sys.modules.pop("code_puppy.api.ws", None)
    sys.modules.pop("code_puppy.api.ws.chat_handler", None)
    sys.modules.pop("code_puppy.api.ws.response_frames", None)

    module = importlib.import_module("code_puppy.api.ws.response_frames")

    assert module is not None
    assert "code_puppy.api.ws.chat_handler" not in sys.modules
