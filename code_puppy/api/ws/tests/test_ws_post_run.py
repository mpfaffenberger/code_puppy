from __future__ import annotations

from types import SimpleNamespace

from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.ws_post_run import resolve_post_run_resolution


class _Logger:
    def __init__(self):
        self.debug_messages = []
        self.warning_messages = []

    def debug(self, message, *args):
        self.debug_messages.append(message % args if args else message)

    def warning(self, message, *args):
        self.warning_messages.append(message % args if args else message)


class _AssistantMessage:
    role = "assistant"

    def __init__(self, content: str):
        self.content = content


class _ThinkingPart:
    def __init__(self, content: str):
        self.content = content


class _ModelResponse:
    def __init__(self, parts):
        self.parts = parts


class _Agent:
    def __init__(self, history=None, estimate=7):
        self._history = history or []
        self._estimate = estimate

    def get_message_history(self):
        return list(self._history)

    def estimate_tokens_for_message(self, _msg):
        return self._estimate


def test_resolve_post_run_resolution_cancelled():
    state = WebSocketTurnState()
    state.agent_error = "cancelled"

    resolution = resolve_post_run_resolution(
        result=None,
        turn_state=state,
        agent=None,
        session_id="s1",
        logger=_Logger(),
    )

    assert resolution.cancelled is True
    assert resolution.error_frames is None
    assert resolution.no_result_error is None


def test_resolve_post_run_resolution_builds_error_frames_for_agent_exception():
    state = WebSocketTurnState(collected_text=["partial output"])
    state.agent_error = RuntimeError("boom")

    resolution = resolve_post_run_resolution(
        result=None,
        turn_state=state,
        agent=None,
        session_id="s2",
        logger=_Logger(),
    )

    assert resolution.cancelled is False
    assert resolution.error_frames is not None
    assert resolution.error_frames[0]["type"] == "stream_end"
    assert resolution.error_frames[0]["success"] is False
    assert resolution.error_frames[1]["type"] == "error"


def test_resolve_post_run_resolution_handles_no_result_without_stream():
    state = WebSocketTurnState()

    resolution = resolve_post_run_resolution(
        result=None,
        turn_state=state,
        agent=None,
        session_id="s3",
        logger=_Logger(),
    )

    assert resolution.no_result_error is not None
    assert resolution.no_result_error.type == "error"
    assert resolution.no_result_error.session_id == "s3"
    assert "no result returned" in resolution.no_result_error.error.lower()


def test_resolve_post_run_resolution_prefers_streamed_text_and_result_usage():
    state = WebSocketTurnState(collected_text=["hello", " world"])
    result = SimpleNamespace(
        output="ignored",
        usage=SimpleNamespace(input_tokens=3, output_tokens=5, total_tokens=8),
    )

    resolution = resolve_post_run_resolution(
        result=result,
        turn_state=state,
        agent=_Agent(history=[]),
        session_id="s4",
        logger=_Logger(),
    )

    assert resolution.response_text == "hello world"
    assert resolution.tokens_used == {
        "input_tokens": 3,
        "output_tokens": 5,
        "total_tokens": 8,
    }


def test_resolve_post_run_resolution_falls_back_to_history_and_extracts_thinking():
    agent = _Agent(
        history=[
            _AssistantMessage("final assistant reply"),
            _ModelResponse(parts=[_ThinkingPart("hidden reasoning")]),
        ],
        estimate=11,
    )
    state = WebSocketTurnState()

    resolution = resolve_post_run_resolution(
        result=False,
        turn_state=state,
        agent=agent,
        session_id="s5",
        logger=_Logger(),
    )

    assert resolution.response_text == "final assistant reply"
    assert resolution.thinking_text == "hidden reasoning"
    assert resolution.tokens_used == {
        "total_tokens": 22,
        "estimated": True,
    }
