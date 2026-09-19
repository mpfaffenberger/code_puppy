"""Compact tool-call display and task-local suppression of tool chatter.

Results still flow to the model. Only UI messages emitted during execution
are silenced; input/confirmation requests and warnings/errors remain visible.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar

from rich.text import Text

_tool_output_active: ContextVar[bool] = ContextVar("tool_output_active", default=False)


def _format_argument(value: object) -> str:
    """Keep strings readable and multiline/large values compact."""
    from .bar_rendering import sanitize

    if isinstance(value, str):
        text = sanitize(" ".join(value.split()))
        if len(text) > 100:
            text = text[:99] + "…"
        return f'"{text}"' if not text or " " in text else text
    if isinstance(value, (dict, list, tuple)):
        # Avoid printing edit bodies, nested tool batches, or other payloads.
        opening, closing = ("{", "}") if isinstance(value, dict) else ("[", "]")
        return f"{opening}… ×{len(value)}{closing}"
    return json.dumps(value, ensure_ascii=False, default=str)


def format_tool_call(tool_name: str, arguments: object) -> Text:
    """Build a styled, literal one-line summary rather than a JSON payload."""
    from rich.style import Style

    from code_puppy.callbacks import on_prompt_text_color

    from .bar_rendering import sanitize

    name = sanitize(" ".join(tool_name.split()))
    summary = Text(no_wrap=True, overflow="ellipsis")
    summary.append(
        f"● {name}", Style(color=on_prompt_text_color() or "cyan", bold=True)
    )
    if isinstance(arguments, dict):
        for index, (key, value) in enumerate(arguments.items()):
            summary.append("  " if index == 0 else " · ", style="dim")
            summary.append(f"{sanitize(str(key))}=", style="dim")
            summary.append(_format_argument(value), style="not bold")
    elif arguments is not None:
        summary.append("  " + _format_argument(arguments), style="not bold")
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
        console = get_streaming_console()
        summary = format_tool_call(tool_name, arguments)
        # Clip before printing: terminal soft-wrap can bypass Rich's no_wrap.
        summary.truncate(max(1, console.width - 1), overflow="ellipsis")
        console.print(summary, end="\n\n", soft_wrap=False)
    token = _tool_output_active.set(True)
    try:
        yield
    finally:
        _tool_output_active.reset(token)
