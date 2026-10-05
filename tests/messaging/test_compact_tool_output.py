"""Tool summaries are literal one-liners; bodies never reach the transcript."""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage
from code_puppy.messaging.messages import (
    FileContentMessage,
    MessageLevel,
    ShellLineMessage,
    TextMessage,
)
from code_puppy.messaging.rich_renderer import RichConsoleRenderer
from code_puppy.messaging.tool_output import (
    compact_tool_output,
    format_tool_call,
    suppress_tool_message,
)


def test_summary_is_one_literal_line():
    summary = format_tool_call("read_file", {"path": "[red]file", "text": "a\nb"})
    assert summary.plain == '● read_file  path=[red]file · text="a b"'
    assert summary.no_wrap


def test_nested_payloads_are_summarized():
    summary = format_tool_call(
        "replace_in_file", {"replacements": [{"new_str": "x" * 10000}]}
    )
    assert summary.plain == "● replace_in_file  replacements=[… ×1]"


def test_tool_name_uses_theme_color():
    with patch("code_puppy.callbacks.on_prompt_text_color", return_value="#aabbcc"):
        summary = format_tool_call("read_file", {})
    marker, name = summary.spans
    assert (marker.start, marker.end) == (0, 1)
    assert marker.style.color.name == "bright_blue"
    assert not marker.style.bold
    assert name.style.color.triplet == (170, 187, 204)
    assert name.start == 2
    assert summary.plain == "● read_file"


def test_arg_names_accented_and_values_dimmed():
    from rich.style import Style

    summary = format_tool_call("read_file", {"file_path": "x.py"})
    styles = {
        summary.plain[s.start : s.end]: Style.parse(str(s.style)) for s in summary.spans
    }
    assert styles["file_path"].color.name == "bright_blue"
    assert styles["x.py"].dim is True
    assert styles["="].dim is True


def test_long_call_stays_on_one_line_with_blank_separator():
    output = StringIO()
    console = Console(file=output, width=40, soft_wrap=True)
    with (
        patch(
            "code_puppy.agents.event_stream_handler.get_streaming_console",
            return_value=console,
        ),
        patch(
            "code_puppy.agents.event_stream_handler._should_suppress_output",
            return_value=False,
        ),
    ):
        with compact_tool_output("shell", {"command": "long command " * 100}):
            pass
    lines = output.getvalue().splitlines()
    assert len(lines) == 2
    assert len(lines[0]) <= 39
    assert lines[0].endswith("…")
    assert lines[1] == ""


def test_execution_suppresses_both_buses_and_restores_after_exception():
    bus = MessageBus()
    queue = MessageQueue()
    output = StringIO()
    console = Console(file=output, width=120)
    with (
        patch(
            "code_puppy.agents.event_stream_handler.get_streaming_console",
            return_value=console,
        ),
        patch(
            "code_puppy.agents.event_stream_handler._should_suppress_output",
            return_value=False,
        ),
    ):
        with pytest.raises(RuntimeError), compact_tool_output("example", {"x": 1}):
            bus.emit(ShellLineMessage(line="hidden"))
            bus.emit(TextMessage(level=MessageLevel.INFO, text="hidden"))
            bus.emit(TextMessage(level=MessageLevel.WARNING, text="visible"))
            queue.emit(UIMessage(MessageType.TOOL_OUTPUT, "hidden"))
            queue.emit(UIMessage(MessageType.HUMAN_INPUT_REQUEST, "approval"))
            raise RuntimeError("failure")
    bus.emit(TextMessage(level=MessageLevel.INFO, text="restored"))
    assert [message.text for message in bus.get_buffered_messages()] == [
        "visible",
        "restored",
    ]
    assert [message.content for message in queue.get_buffered_messages()] == [
        "approval"
    ]
    assert output.getvalue() == "● example  x=1\n\n"


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_thread_emitted_shell_output_is_hidden(level):
    output = StringIO()
    renderer = RichConsoleRenderer(bus=MessageBus(), console=Console(file=output))
    with patch(
        "code_puppy.messaging.rich_renderer.get_output_level", return_value=level
    ):
        renderer._do_render(ShellLineMessage(line="never display tool results"))
    assert output.getvalue() == ""


def test_show_tool_output_emits_execution_chatter():
    """Enabling show_tool_output stops the emit-time suppression."""
    with (
        patch("code_puppy.messaging.tool_output.is_windows", return_value=False),
        patch(
            "code_puppy.messaging.tool_output.tool_output_visible",
            return_value=True,
        ),
        patch(
            "code_puppy.agents.event_stream_handler._should_suppress_output",
            return_value=True,
        ),
    ):
        with compact_tool_output("read_file", {"path": "x.py"}):
            assert (
                suppress_tool_message(TextMessage(level=MessageLevel.INFO, text="hi"))
                is False
            )


def test_windows_always_drops_shell_even_when_showing():
    """The Windows shell-output guard ignores show_tool_output entirely."""
    with (
        patch("code_puppy.messaging.tool_output.is_windows", return_value=True),
        patch(
            "code_puppy.messaging.tool_output.tool_output_visible",
            return_value=True,
        ),
    ):
        assert suppress_tool_message(ShellLineMessage(line="pwsh garbage")) is True
        # File/diff results are not shell output and stay visible.
        assert (
            suppress_tool_message(
                FileContentMessage(
                    path="x.py", content="hi", total_lines=1, num_tokens=1
                )
            )
            is False
        )


def test_renderer_renders_shell_output_when_enabled_on_non_windows():
    output = StringIO()
    renderer = RichConsoleRenderer(bus=MessageBus(), console=Console(file=output))
    with (
        patch("code_puppy.messaging.rich_renderer.is_windows", return_value=False),
        patch(
            "code_puppy.messaging.rich_renderer.tool_output_visible",
            return_value=True,
        ),
    ):
        renderer._do_render(ShellLineMessage(line="hello from shell"))
    assert "hello from shell" in output.getvalue()


def test_renderer_drops_shell_on_windows_even_when_enabled():
    output = StringIO()
    renderer = RichConsoleRenderer(bus=MessageBus(), console=Console(file=output))
    with (
        patch("code_puppy.messaging.rich_renderer.is_windows", return_value=True),
        patch(
            "code_puppy.messaging.rich_renderer.tool_output_visible",
            return_value=True,
        ),
    ):
        renderer._do_render(ShellLineMessage(line="pwsh garbage"))
    assert output.getvalue() == ""
