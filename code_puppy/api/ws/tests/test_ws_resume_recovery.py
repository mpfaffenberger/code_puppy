from __future__ import annotations

from code_puppy.api.ws.ws_resume_recovery import (
    sanitize_trailing_incomplete_tool_history,
)


class ToolCallPart: ...


class ToolReturnPart: ...


class TextPart: ...


class _Msg:
    def __init__(self, parts):
        self.parts = parts


def test_sanitize_trims_trailing_tool_call_only_messages():
    history = [
        _Msg([TextPart()]),
        _Msg([ToolCallPart()]),
        _Msg([ToolCallPart()]),
    ]

    sanitized, removed = sanitize_trailing_incomplete_tool_history(history)

    assert removed == 2
    assert len(sanitized) == 1


def test_sanitize_keeps_messages_with_tool_return_or_text():
    history = [
        _Msg([ToolCallPart(), ToolReturnPart()]),
        _Msg([ToolCallPart(), TextPart()]),
    ]

    sanitized, removed = sanitize_trailing_incomplete_tool_history(history)

    assert removed == 0
    assert len(sanitized) == 2
