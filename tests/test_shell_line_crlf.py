"""Regression tests for the Windows shell-output ANSI-leak bug.

Bug: on Windows, subprocess output lines arrive as CRLF. The reader only
stripped the trailing LF (leaving a lone CR), and ``_render_shell_line`` treated
*any* CR as a progress-bar redraw -- routing every normal line through a raw
``sys.stdout.write`` of ANSI codes. When the console had not enabled VT
processing, those codes printed literally as ``[2m ... [0m``.

Fix: strip trailing CRLF and only treat an *interior* CR as a progress-bar
redraw; otherwise render through Rich so terminal/VT handling is deterministic.
"""

import sys
from io import StringIO
from unittest.mock import Mock

from rich.console import Console
from rich.text import Text

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import ShellLineMessage
from code_puppy.messaging.rich_renderer import RichConsoleRenderer

DIM = "\x1b[2m"
RESET = "\x1b[0m"
CR = "\r"
LF = "\n"


def _make_renderer() -> tuple[RichConsoleRenderer, Mock]:
    bus = MessageBus()
    console = Mock(spec=Console)
    return RichConsoleRenderer(bus, console=console), console


def test_trailing_crlf_line_renders_through_rich_not_raw_bypass(monkeypatch) -> None:
    """A normal line that merely ends in CR/LF must go through Rich.

    Core of the fix: the trailing CR from a Windows CRLF line ending must not be
    mistaken for a progress-bar redraw, which would leak raw ANSI to the console.
    """
    renderer, console = _make_renderer()
    fake_stdout = StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    msg = ShellLineMessage(
        line=f"{DIM}16 passed in 13.95s{RESET}{CR}{LF}", stream="stdout"
    )
    renderer._render_shell_line(msg)

    assert console.print.called, "normal line should render via Rich console"
    assert fake_stdout.getvalue() == "", "must not raw-write ANSI to stdout"

    printed = console.print.call_args.args[0]
    assert isinstance(printed, Text)
    assert "[2m" not in printed.plain and "[0m" not in printed.plain
    assert console.print.call_args.kwargs.get("style") == "dim"


def test_interior_cr_line_still_uses_raw_bypass(monkeypatch) -> None:
    """A genuine progress-bar line (interior CR) keeps the raw-stdout path."""
    renderer, console = _make_renderer()
    fake_stdout = StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    msg = ShellLineMessage(line=f"downloading 50%{CR}downloading 60%", stream="stdout")
    renderer._render_shell_line(msg)

    assert not console.print.called, "progress-bar line should bypass Rich"
    assert "downloading 60%" in fake_stdout.getvalue()


def test_plain_lf_line_is_unchanged_macos_equivalence(monkeypatch) -> None:
    """macOS/Linux safety: a normal LF-only line behaves exactly as before.

    On Unix, shell output ends in a bare LF with no CR, so rstrip('\r\n')
    strips the same trailing newline rstrip('\n') did, and the interior-CR
    check is False either way -> the line still routes through Rich. The fix is
    therefore a no-op for non-Windows output; it only changes lines that carry a
    trailing CR (the Windows CRLF case).
    """
    renderer, console = _make_renderer()
    fake_stdout = StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    msg = ShellLineMessage(line=f"{DIM}hello from macos{RESET}{LF}", stream="stdout")
    renderer._render_shell_line(msg)

    assert console.print.called, "plain LF line should render via Rich"
    assert fake_stdout.getvalue() == "", "must not raw-write ANSI to stdout"
    printed = console.print.call_args.args[0]
    assert isinstance(printed, Text)
    assert printed.plain == "hello from macos"
