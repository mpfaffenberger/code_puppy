"""Compact tool-call display and task-local suppression of tool chatter.

Results still flow to the model. Only UI messages emitted during execution
are silenced; input/confirmation requests and warnings/errors remain visible.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar

from rich.text import Text

_tool_output_active: ContextVar[bool] = ContextVar("tool_output_active", default=False)


def format_tool_call(tool_name: str, arguments: object) -> Text:
    """Build a literal, single-line summary without interpreting Rich markup."""
    args = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), default=str)
    # JSON escapes embedded newlines; also neutralize controls in tool names.
    name = " ".join(tool_name.split())
    summary = Text(f"● {name} {args}", no_wrap=True, overflow="ellipsis")
    return summary


def suppress_tool_message(message: object) -> bool:
    """Keep consent and diagnostics visible while dropping execution chatter."""
    if not _tool_output_active.get():
        return False
    category = getattr(message, "category", None)
    kind = getattr(message, "type", None)
    level = getattr(message, "level", None)
    values = {getattr(value, "value", value) for value in (category, kind, level)}
    return not values.intersection(
        {"user_interaction", "human_input_request", "warning", "error"}
    )


@contextmanager
def compact_tool_output(tool_name: str, arguments: object):
    """Show one call summary, then silence task-local tool UI until it finishes."""
    from code_puppy.agents.event_stream_handler import (
        _should_suppress_output,
        get_streaming_console,
    )

    if not _should_suppress_output():
        get_streaming_console().print(format_tool_call(tool_name, arguments))
    token = _tool_output_active.set(True)
    try:
        yield
    finally:
        _tool_output_active.reset(token)
