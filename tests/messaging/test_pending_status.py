"""Pending work is obvious on the bar and silent in the transcript."""

from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text

from code_puppy.messaging.message_queue import MessageType, UIMessage
from code_puppy.messaging.renderers import _print_message
from code_puppy.messaging.status_line import render_status_line


@pytest.mark.parametrize("width", [20, 40, 120])
def test_pending_survives_long_status(width):
    rendered = render_status_line("tokens " * 100, " (1 pending)", width)
    text = Text.from_ansi(rendered)
    assert "(1 pending)" in text.plain
    assert text.cell_len <= width
    style = text.get_style_at_offset(Console(), text.plain.index("pending"))
    assert style.bold
    assert style.reverse
    assert not style.dim
    assert style.color.number == 5


def test_empty_queue_has_no_badge():
    text = Text.from_ansi(render_status_line("tokens", "", 80))
    assert text.plain == "tokens"


def test_queue_ack_does_not_print():
    output = StringIO()
    _print_message(
        Console(file=output), UIMessage(MessageType.QUEUED, "for next turn: secret")
    )
    assert output.getvalue() == ""


def test_control_sequences_in_suffix_are_not_executed():
    rendered = render_status_line("tokens", "\x1b[2J(1 pending)", 80)
    assert "\x1b[2J" not in rendered
