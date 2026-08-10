"""Tests for code_puppy.messaging.queue_console."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from code_puppy.messaging.message_queue import MessageQueue, MessageType
from code_puppy.messaging.queue_console import QueueConsole, get_queue_console


@pytest.fixture
def mq():
    q = MessageQueue(maxsize=100)
    q.mark_renderer_active()
    return q


@pytest.fixture
def qc(mq):
    return QueueConsole(queue=mq)


# =========================================================================
# print
# =========================================================================


def test_print_single_rich_object(qc, mq):
    table = Table()
    table.add_column("X")
    table.add_row("val")
    qc.print(table)
    msg = mq.get_nowait()
    assert msg is not None
    assert msg.type == MessageType.TOOL_OUTPUT


def test_print_string(qc, mq):
    qc.print("hello world")
    msg = mq.get_nowait()
    assert msg is not None


def test_print_with_style(qc, mq):
    qc.print("error!", style="bold red")
    msg = mq.get_nowait()
    assert msg is not None
    assert msg.type == MessageType.ERROR


def test_print_multiple_values_with_rich_object(qc, mq):
    t = Text("hello")
    qc.print("prefix", t, "suffix")
    msg = mq.get_nowait()
    assert msg is not None


@pytest.mark.parametrize(
    ("style", "text", "expected_type"),
    [
        pytest.param("green", "ok", MessageType.SUCCESS, id="green"),
        pytest.param("yellow", "warn", MessageType.WARNING, id="yellow"),
        pytest.param("blue", "info", MessageType.INFO, id="blue"),
        pytest.param("purple", "think", MessageType.AGENT_REASONING, id="purple"),
        pytest.param("magenta", "think", MessageType.AGENT_REASONING, id="magenta"),
        pytest.param("dim", "sys", MessageType.SYSTEM, id="dim"),
    ],
)
def test_print_with_style_maps_to_type(qc, mq, style, text, expected_type):
    qc.print(text, style=style)
    msg = mq.get_nowait()
    assert msg.type == expected_type


# =========================================================================
# print_exception
# =========================================================================


def test_print_exception(qc, mq):
    try:
        raise ValueError("test error")
    except ValueError:
        qc.print_exception()
    msg = mq.get_nowait()
    assert msg is not None
    assert msg.type == MessageType.ERROR


# =========================================================================
# log
# =========================================================================


def test_log_basic(qc, mq):
    qc.log("log message")
    msg = mq.get_nowait()
    assert msg is not None
    assert msg.type == MessageType.INFO


def test_log_with_style(qc, mq):
    qc.log("error log", style="red")
    msg = mq.get_nowait()
    assert msg.type == MessageType.ERROR


# =========================================================================
# _infer_message_type
# =========================================================================


def test_infer_message_type_from_content(qc):
    assert qc._infer_message_type("error occurred") == MessageType.ERROR
    assert qc._infer_message_type("failed!") == MessageType.ERROR
    assert qc._infer_message_type("exception raised") == MessageType.ERROR
    assert qc._infer_message_type("warning: something") == MessageType.WARNING
    assert qc._infer_message_type("warn about this") == MessageType.WARNING
    assert qc._infer_message_type("success!") == MessageType.SUCCESS
    assert qc._infer_message_type("completed task") == MessageType.SUCCESS
    assert qc._infer_message_type("done now") == MessageType.SUCCESS
    assert qc._infer_message_type("tool output") == MessageType.TOOL_OUTPUT
    assert qc._infer_message_type("command here") == MessageType.TOOL_OUTPUT
    assert qc._infer_message_type("running now") == MessageType.TOOL_OUTPUT
    assert qc._infer_message_type("normal text") == MessageType.INFO


# =========================================================================
# _infer_message_type_from_rich_object
# =========================================================================


def test_infer_from_rich_object_markdown(qc):
    md = Markdown("**hello**")
    assert qc._infer_message_type_from_rich_object(md) == MessageType.AGENT_REASONING


def test_infer_from_rich_object_table(qc):
    t = Table()
    assert qc._infer_message_type_from_rich_object(t) == MessageType.TOOL_OUTPUT


def test_infer_from_rich_object_syntax(qc):
    obj = MagicMock()
    obj.lexer_name = "python"
    assert qc._infer_message_type_from_rich_object(obj) == MessageType.TOOL_OUTPUT


def test_infer_from_rich_object_default(qc):
    obj = MagicMock(spec=[])  # No lexer_name, not Markdown, not Table
    assert qc._infer_message_type_from_rich_object(obj) == MessageType.INFO


def test_infer_from_rich_object_with_styles(qc):
    obj = MagicMock(spec=[])
    assert qc._infer_message_type_from_rich_object(obj, "red") == MessageType.ERROR
    assert qc._infer_message_type_from_rich_object(obj, "error") == MessageType.ERROR
    assert qc._infer_message_type_from_rich_object(obj, "yellow") == MessageType.WARNING
    assert (
        qc._infer_message_type_from_rich_object(obj, "warning") == MessageType.WARNING
    )
    assert qc._infer_message_type_from_rich_object(obj, "green") == MessageType.SUCCESS
    assert (
        qc._infer_message_type_from_rich_object(obj, "success") == MessageType.SUCCESS
    )
    assert qc._infer_message_type_from_rich_object(obj, "blue") == MessageType.INFO
    assert (
        qc._infer_message_type_from_rich_object(obj, "purple")
        == MessageType.AGENT_REASONING
    )
    assert (
        qc._infer_message_type_from_rich_object(obj, "magenta")
        == MessageType.AGENT_REASONING
    )
    assert qc._infer_message_type_from_rich_object(obj, "dim") == MessageType.SYSTEM


# =========================================================================
# rule, status
# =========================================================================


def test_rule(qc, mq):
    qc.rule("Title")
    msg = mq.get_nowait()
    assert msg is not None
    assert "Title" in str(msg.content)


def test_rule_no_title(qc, mq):
    qc.rule()
    msg = mq.get_nowait()
    assert msg is not None


def test_status(qc, mq):
    qc.status("Loading...")
    msg = mq.get_nowait()
    assert msg is not None
    assert "Loading" in str(msg.content)


# =========================================================================
# input
# =========================================================================


@patch("code_puppy.tools.command_runner.set_awaiting_user_input")
@pytest.mark.parametrize(
    (
        "mock_return",
        "side_effect",
        "prompt",
        "expected",
    ),
    [
        ("user response", None, "Enter:", "user response"),  # normal
        ("", None, "Enter:", ""),  # empty input
        (None, KeyboardInterrupt, "Enter:", ""),  # Ctrl+C
        (None, EOFError, "Enter:", ""),  # EOF
        ("val", None, None, "val"),  # no prompt
    ],
    ids=["normal", "empty", "keyboard_interrupt", "eof", "no_prompt"],
)
def test_input(mock_set, mock_return, side_effect, prompt, expected, qc, mq):
    with patch("builtins.input", return_value=mock_return, side_effect=side_effect):
        result = qc.input(prompt) if prompt is not None else qc.input()
    assert result == expected


# =========================================================================
# file property
# =========================================================================


def test_file_property(qc):
    f = qc.file
    assert f is not None


def test_file_setter(qc):
    sio = StringIO()
    qc.file = sio
    assert qc.fallback_console.file is sio


# =========================================================================
# get_queue_console
# =========================================================================


def test_get_queue_console(mq):
    qc = get_queue_console(mq)
    assert isinstance(qc, QueueConsole)
