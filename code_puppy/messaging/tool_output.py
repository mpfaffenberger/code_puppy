"""Compact tool-call display and task-local suppression of tool chatter.

Results still flow to the model. By default only UI messages emitted during
execution are silenced; input/confirmation requests and warnings/errors
remain visible. Enabling ``show_tool_output`` keeps the full result bodies
visible too. On Windows, shell output is always silenced regardless.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar

from rich.text import Text

from code_puppy.platform_utils import is_windows

from .theme_accent import agent_accent

_tool_output_active: ContextVar[bool] = ContextVar("tool_output_active", default=False)

# Queue message types that carry shell command output.
_SHELL_MESSAGE_TYPES = frozenset({"command_output"})


def is_shell_message(message: object) -> bool:
    """Return True for shell command output (stdout/stderr lines & summary).

    Handles both the structured bus messages (:class:`ShellLineMessage` etc.)
    and the legacy queue ``UIMessage`` types, so every emit path can apply
    the Windows shell-output guard uniformly.
    """
    from .messages import ShellLineMessage, ShellOutputMessage, ShellStartMessage

    if isinstance(message, (ShellStartMessage, ShellLineMessage, ShellOutputMessage)):
        return True
    kind = getattr(message, "type", None)
    return getattr(kind, "value", kind) in _SHELL_MESSAGE_TYPES


def tool_output_visible() -> bool:
    """Return True when the user opted into full tool-call results.

    Backed by the ``show_tool_output`` setting (default off). Keeping the
    lookup in one place means the emit-time and render-time gates can never
    disagree about whether results are shown.
    """
    from code_puppy.config import get_show_tool_output

    return get_show_tool_output()


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


def format_activity_heading(label: str, *, secondary: bool = False) -> Text:
    """Shared accent bullet and bold foreground label for transcript activity."""
    from rich.style import Style

    from code_puppy.callbacks import on_prompt_text_color

    from .bar_rendering import sanitize

    name = sanitize(" ".join(label.split()))
    summary = Text(no_wrap=True, overflow="ellipsis")
    # Explicit RGB bypasses Rich's separate named-color remapping.
    accent = Style(color="cyan" if secondary else agent_accent())
    summary.append("●", accent)
    summary.append(" ")
    label_color = "cyan" if secondary else (on_prompt_text_color() or "cyan")
    summary.append(name, Style(color=label_color, bold=True))
    return summary


def format_tool_call(tool_name: str, arguments: object) -> Text:
    """Build a styled, literal one-line summary rather than a JSON payload."""
    from .bar_rendering import sanitize

    summary = format_activity_heading(tool_name)
    accent = agent_accent()
    if isinstance(arguments, dict):
        for index, (key, value) in enumerate(arguments.items()):
            summary.append("  " if index == 0 else " · ", style="dim")
            summary.append(sanitize(str(key)), accent)
            summary.append("=", style="dim")
            summary.append(_format_argument(value), style="dim")
    elif arguments is not None:
        summary.append("  " + _format_argument(arguments), style="dim")
    return summary


def suppress_tool_message(message: object) -> bool:
    """Keep consent and diagnostics visible while dropping execution chatter.

    On Windows, shell output is *always* dropped -- PowerShell control
    characters brick SIGINT and make Code Puppy impossible to cancel.
    When ``show_tool_output`` is enabled, execution chatter is kept so the
    full tool results reach the renderer.
    """
    # Windows shells can corrupt the terminal and swallow Ctrl+C.
    if is_shell_message(message) and is_windows():
        return True

    if not _tool_output_active.get():
        return False

    # User opted into full tool results: nothing is suppressed mid-run.
    if tool_output_visible():
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
