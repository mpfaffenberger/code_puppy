"""Tests for the rich console renderer."""

import sys
import types
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as escape_rich_markup
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

ROOT = Path(__file__).resolve().parents[1]
MESSAGING_PATH = ROOT / "code_puppy" / "messaging"
TOOLS_PATH = ROOT / "code_puppy" / "tools"

messaging_pkg = types.ModuleType("code_puppy.messaging")
messaging_pkg.__path__ = [str(MESSAGING_PATH)]
sys.modules.setdefault("code_puppy.messaging", messaging_pkg)

tools_pkg = types.ModuleType("code_puppy.tools")
tools_pkg.__path__ = [str(TOOLS_PATH)]
sys.modules.setdefault("code_puppy.tools", tools_pkg)

common_stub = types.ModuleType("code_puppy.tools.common")
common_stub.format_diff_with_colors = lambda diff_text: diff_text
sys.modules.setdefault("code_puppy.tools.common", common_stub)

from code_puppy.messaging import rich_renderer as rich_renderer_module  # noqa: E402
from code_puppy.messaging.bus import MessageBus  # noqa: E402
from code_puppy.messaging.messages import (  # noqa: E402
    AgentReasoningMessage,
    ConfirmationRequest,
    DiffLine,
    DiffMessage,
    DividerMessage,
    FileContentMessage,
    FileEntry,
    FileListingMessage,
    GrepMatch,
    GrepResultMessage,
    MessageLevel,
    SelectionRequest,
    ShellLineMessage,
    ShellOutputMessage,
    ShellStartMessage,
    SpinnerControl,
    StatusPanelMessage,
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    TextMessage,
    UserInputRequest,
    VersionCheckMessage,
)
from code_puppy.messaging.rich_renderer import RichConsoleRenderer  # noqa: E402


def _make_renderer() -> tuple[RichConsoleRenderer, Mock]:
    bus = MessageBus()
    console = Mock(spec=Console)
    return RichConsoleRenderer(bus, console=console), console


def test_render_text_escapes_markup_and_prefix() -> None:
    renderer, console = _make_renderer()
    message = TextMessage(level=MessageLevel.ERROR, text="bad [tag]")

    renderer._render_text(message)

    printed = console.print.call_args
    expected = f"✗ {escape_rich_markup(message.text)}"
    assert expected in printed.args[0]
    assert printed.kwargs["style"] == "bold red"


def test_render_text_version_message_uses_dim_style() -> None:
    renderer, console = _make_renderer()
    message = TextMessage(level=MessageLevel.INFO, text="Current version: 1.0")

    renderer._render_text(message)

    assert console.print.call_args.kwargs["style"] == "dim"


def test_render_agent_reasoning_outputs_markdown() -> None:
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")
    message = AgentReasoningMessage(
        reasoning="**Why:** because markdown",
        next_steps="- do the thing",
    )

    renderer._render_agent_reasoning(message)

    markdown_calls = [
        call
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], Markdown)
    ]
    assert len(markdown_calls) == 2


def test_render_status_panel_and_divider() -> None:
    renderer, console = _make_renderer()
    status = StatusPanelMessage(title="Status", fields={"A": "1", "B": "2"})

    renderer._render_status_panel(status)
    panel_arg = console.print.call_args.args[0]
    assert isinstance(panel_arg, Panel)

    divider = DividerMessage(style="double")
    renderer._render_divider(divider)
    rule_arg = console.print.call_args.args[0]
    assert isinstance(rule_arg, Rule)
    assert rule_arg.characters == "═"


def test_render_diff_uses_formatter(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    monkeypatch.setattr(
        rich_renderer_module,
        "format_diff_with_colors",
        lambda diff_text: f"FORMATTED:{diff_text}",
    )

    message = DiffMessage(
        path="example.py",
        operation="modify",
        diff_lines=[
            DiffLine(line_number=1, type="context", content="@@ -1 +1 @@"),
            DiffLine(line_number=2, type="remove", content="old"),
            DiffLine(line_number=3, type="add", content="new"),
        ],
    )

    renderer._render_diff(message)

    printed = "".join(
        call.args[0]
        for call in console.print.call_args_list
        if isinstance(call.args[0], str)
    )
    assert "FORMATTED:" in printed


def test_render_grep_result_verbose_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    empty_message = GrepResultMessage(
        search_term="needle",
        directory="/tmp",
        matches=[],
        total_matches=0,
        files_searched=1,
    )
    renderer._render_grep_result(empty_message)
    assert any("No matches" in call.args[0] for call in console.print.call_args_list)

    console.reset_mock()
    matches = [
        GrepMatch(file_path="a.py", line_number=1, line_content="needle here"),
        GrepMatch(file_path="a.py", line_number=2, line_content="another needle"),
    ]
    verbose_message = GrepResultMessage(
        search_term="needle",
        directory="/tmp",
        matches=matches,
        total_matches=2,
        files_searched=1,
        verbose=True,
    )
    renderer._render_grep_result(verbose_message)
    assert any("a.py" in call.args[0] for call in console.print.call_args_list)


def test_render_file_listing_and_content() -> None:
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    listing = FileListingMessage(
        directory="/tmp",
        files=[
            FileEntry(path="alpha.txt", type="file", size=10, depth=0),
            FileEntry(path="docs", type="dir", size=0, depth=0),
            FileEntry(path="docs/readme.md", type="file", size=5, depth=1),
        ],
        recursive=True,
        total_size=15,
        dir_count=1,
        file_count=2,
    )
    renderer._render_file_listing(listing)

    content = FileContentMessage(
        path="alpha.txt",
        content="hello",
        start_line=1,
        num_lines=1,
        total_lines=1,
        num_tokens=1,
    )
    renderer._render_file_content(content)

    assert console.print.called


def test_render_shell_line_and_output() -> None:
    renderer, console = _make_renderer()
    line_message = ShellLineMessage(line="\u001b[32mgreen\u001b[0m", stream="stdout")

    renderer._render_shell_line(line_message)

    assert isinstance(console.print.call_args.args[0], Text)
    assert console.print.call_args.kwargs["style"] == "dim"

    output_message = ShellOutputMessage(
        command="ls",
        stdout="ok",
        stderr="",
        exit_code=0,
        duration_seconds=0.1,
    )
    renderer._render_shell_output(output_message)
    assert console.print.call_count == 2


def test_render_version_check_messages() -> None:
    renderer, console = _make_renderer()

    update_message = VersionCheckMessage(
        current_version="1.0",
        latest_version="2.0",
        update_available=True,
    )
    renderer._render_version_check(update_message)
    assert "Update available" in console.print.call_args.args[0]

    console.reset_mock()
    ok_message = VersionCheckMessage(
        current_version="1.0",
        latest_version="1.0",
        update_available=False,
    )
    renderer._render_version_check(ok_message)
    assert "latest version" in console.print.call_args.args[0]


def test_render_sync_handles_exceptions() -> None:
    renderer, console = _make_renderer()

    def boom(_: TextMessage) -> None:
        raise ValueError("boom [x]")

    renderer._do_render = boom  # type: ignore[assignment]

    renderer._render_sync(TextMessage(level=MessageLevel.INFO, text="hi"))

    assert "Render error" in console.print.call_args.args[0]


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (12, "12 B"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
    ],
)
def test_format_size(size_bytes: int, expected: str) -> None:
    renderer, _ = _make_renderer()
    assert renderer._format_size(size_bytes) == expected


def test_get_file_icon_defaults() -> None:
    renderer, _ = _make_renderer()
    assert renderer._get_file_icon("notes.md") == "📝"
    assert renderer._get_file_icon("unknown.bin") == "📄"


def test_markdown_rendering_to_real_console() -> None:
    bus = MessageBus()
    output = StringIO()
    console = Console(file=output)
    renderer = RichConsoleRenderer(bus, console=console)

    message = AgentReasoningMessage(reasoning="# Title", next_steps=None)
    renderer._render_agent_reasoning(message)

    rendered = output.getvalue()
    assert "Title" in rendered


def test_format_banner_and_level_prefix() -> None:
    renderer, _ = _make_renderer()
    renderer._get_banner_color = Mock(return_value="magenta")

    banner = renderer._format_banner("thinking", "HELLO")
    assert "magenta" in banner
    assert "HELLO" in banner

    assert renderer._get_level_prefix(MessageLevel.WARNING) == "⚠ "


def test_do_render_dispatches_multiple_messages() -> None:
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    messages = [
        TextMessage(level=MessageLevel.INFO, text="hi"),
        FileListingMessage(
            directory="/tmp",
            files=[FileEntry(path="alpha.txt", type="file", size=1, depth=0)],
            recursive=False,
            total_size=1,
            dir_count=0,
            file_count=1,
        ),
        FileContentMessage(
            path="alpha.txt",
            content="data",
            start_line=None,
            num_lines=None,
            total_lines=1,
            num_tokens=1,
        ),
        GrepResultMessage(
            search_term="needle",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="needle"),
            ],
            total_matches=1,
            files_searched=1,
            verbose=False,
        ),
        DiffMessage(
            path="alpha.txt",
            operation="create",
            diff_lines=[DiffLine(line_number=1, type="add", content="line")],
        ),
        ShellStartMessage(command="echo hi", cwd="/tmp", timeout=5, background=True),
        ShellLineMessage(line="ok", stream="stdout"),
        ShellOutputMessage(
            command="echo", stdout="ok", stderr="", exit_code=0, duration_seconds=0.1
        ),
        AgentReasoningMessage(reasoning="Because", next_steps=None),
        SubAgentInvocationMessage(
            agent_name="helper",
            session_id="sess-1",
            prompt="Do work",
            is_new_session=True,
            message_count=0,
        ),
        SubAgentResponseMessage(
            agent_name="helper",
            session_id="sess-1",
            response="done",
            message_count=1,
        ),
        SpinnerControl(action="start", spinner_id="spin", text="loading"),
        DividerMessage(style="light"),
        StatusPanelMessage(title="Status", fields={"A": "1"}),
        VersionCheckMessage(
            current_version="1.0", latest_version="1.0", update_available=False
        ),
        UserInputRequest(
            prompt_id="p1", prompt_text="Input", default_value=None, input_type="text"
        ),
        ConfirmationRequest(
            prompt_id="p2",
            title="Confirm",
            description="Sure?",
            options=["Yes", "No"],
            allow_feedback=False,
        ),
        SelectionRequest(
            prompt_id="p3", prompt_text="Pick", options=["A", "B"], allow_cancel=False
        ),
    ]

    for message in messages:
        renderer._do_render(message)

    class UnknownMessage:
        pass

    renderer._do_render(UnknownMessage())

    assert console.print.called


@pytest.mark.asyncio
async def test_async_user_interactions() -> None:
    renderer, console = _make_renderer()
    console.input.side_effect = ["secret", "y", "feedback", "2"]

    input_request = UserInputRequest(
        prompt_id="p1",
        prompt_text="Password",
        default_value=None,
        input_type="password",
    )
    await renderer._render_user_input_request(input_request)

    confirm_request = ConfirmationRequest(
        prompt_id="p2",
        title="Confirm",
        description="Proceed?",
        options=["Yes", "No"],
        allow_feedback=True,
    )
    await renderer._render_confirmation_request(confirm_request)

    selection_request = SelectionRequest(
        prompt_id="p3",
        prompt_text="Pick",
        options=["A", "B"],
        allow_cancel=False,
    )
    await renderer._render_selection_request(selection_request)

    assert console.input.call_count == 4
    assert console.input.call_args_list[0].kwargs["password"] is True


def test_start_stop_and_consume_buffer() -> None:
    bus = MessageBus()
    console = Mock(spec=Console)
    renderer = RichConsoleRenderer(bus, console=console)
    renderer._get_banner_color = Mock(return_value="blue")

    bus.emit(TextMessage(level=MessageLevel.INFO, text="buffered"))
    renderer._consume_loop_sync()

    renderer.start()
    renderer.stop()

    assert renderer._running is False


def test_consecutive_file_content_groups_under_single_banner() -> None:
    """Multiple consecutive FileContentMessage should share one banner."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msgs = [
        FileContentMessage(
            path=f"/src/file{i}.ts",
            content=f"content{i}",
            start_line=i * 50 + 1,
            num_lines=50,
            total_lines=100,
            num_tokens=10,
        )
        for i in range(3)
    ]

    # Render all three via _render_sync so grouping state is tracked
    for msg in msgs:
        renderer._render_sync(msg)

    # Collect all printed strings
    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    # Should have exactly ONE banner line (containing "READ FILE")
    banner_lines = [p for p in printed if "READ FILE" in p]
    assert len(banner_lines) == 1, (
        f"Expected 1 banner, got {len(banner_lines)}: {banner_lines}"
    )

    # Should have exactly THREE tree-child lines (containing "├─")
    tree_lines = [p for p in printed if "├─" in p]
    assert len(tree_lines) == 3, (
        f"Expected 3 tree lines, got {len(tree_lines)}: {tree_lines}"
    )

    # Each tree line should contain the file path
    for i in range(3):
        assert any(f"file{i}.ts" in line for line in tree_lines), (
            f"file{i}.ts not found in tree lines"
        )


def test_single_file_content_still_has_banner_and_tree() -> None:
    """A single FileContentMessage should still get banner + tree child."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msg = FileContentMessage(
        path="/src/app.py",
        content="hello",
        start_line=None,
        num_lines=None,
        total_lines=10,
        num_tokens=5,
    )

    renderer._render_sync(msg)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    # Should have banner
    assert any("READ FILE" in p for p in printed), "Missing READ FILE banner"

    # Should have tree child
    assert any("├─" in p and "app.py" in p for p in printed), "Missing tree child line"


def test_different_type_breaks_grouping() -> None:
    """A different message type between same types should reset grouping."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msg1 = FileContentMessage(
        path="/src/a.py",
        content="a",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )
    interruption = TextMessage(level=MessageLevel.INFO, text="some info")
    msg2 = FileContentMessage(
        path="/src/b.py",
        content="b",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )

    renderer._render_sync(msg1)
    renderer._render_sync(interruption)
    renderer._render_sync(msg2)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    # Should have TWO banners (grouping was broken by TextMessage)
    banner_lines = [p for p in printed if "READ FILE" in p]
    assert len(banner_lines) == 2, (
        f"Expected 2 banners, got {len(banner_lines)}: {banner_lines}"
    )


def test_spinner_does_not_break_grouping() -> None:
    """SpinnerControl is transparent and should not break grouping."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msg1 = FileContentMessage(
        path="/src/a.py",
        content="a",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )
    spinner = SpinnerControl(action="start", spinner_id="s1", text="loading")
    msg2 = FileContentMessage(
        path="/src/b.py",
        content="b",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )

    renderer._render_sync(msg1)
    renderer._render_sync(spinner)
    renderer._render_sync(msg2)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    # Should have only ONE banner (spinner didn't break the group)
    banner_lines = [p for p in printed if "READ FILE" in p]
    assert len(banner_lines) == 1, (
        f"Expected 1 banner, got {len(banner_lines)}: {banner_lines}"
    )

    # Should have TWO tree-child lines
    tree_lines = [p for p in printed if "├─" in p]
    assert len(tree_lines) == 2, (
        f"Expected 2 tree lines, got {len(tree_lines)}: {tree_lines}"
    )


def test_consecutive_diff_groups() -> None:
    """Multiple consecutive DiffMessage should share one banner."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msgs = [
        DiffMessage(
            path=f"/src/file{i}.py",
            operation="modify",
            diff_lines=[DiffLine(line_number=1, type="add", content=f"line{i}")],
        )
        for i in range(3)
    ]

    for msg in msgs:
        renderer._render_sync(msg)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    banner_lines = [p for p in printed if "EDIT FILE" in p]
    assert len(banner_lines) == 1, (
        f"Expected 1 banner, got {len(banner_lines)}: {banner_lines}"
    )

    tree_lines = [p for p in printed if "├─" in p]
    assert len(tree_lines) == 3, (
        f"Expected 3 tree lines, got {len(tree_lines)}: {tree_lines}"
    )


def test_consecutive_shell_start_groups() -> None:
    """Multiple consecutive ShellStartMessage should share one banner."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    msgs = [
        ShellStartMessage(command=f"echo {i}", cwd=None, timeout=30, background=False)
        for i in range(3)
    ]

    for msg in msgs:
        renderer._render_sync(msg)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    banner_lines = [p for p in printed if "SHELL COMMAND" in p]
    assert len(banner_lines) == 1, (
        f"Expected 1 banner, got {len(banner_lines)}: {banner_lines}"
    )

    tree_lines = [p for p in printed if "├─" in p]
    assert len(tree_lines) == 3, (
        f"Expected 3 tree lines, got {len(tree_lines)}: {tree_lines}"
    )


def test_grouping_resets_across_different_groupable_types() -> None:
    """Switching between different groupable types should print new banners."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    file_msg = FileContentMessage(
        path="/src/a.py",
        content="a",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )
    grep_msg = GrepResultMessage(
        search_term="needle",
        directory="/src",
        matches=[],
        total_matches=0,
        files_searched=1,
    )

    renderer._render_sync(file_msg)
    renderer._render_sync(grep_msg)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    # Should have both banners
    assert any("READ FILE" in p for p in printed), "Missing READ FILE banner"
    assert any("GREP" in p for p in printed), "Missing GREP banner"


@pytest.mark.asyncio
async def test_async_render_grouping_resets_across_different_groupable_types() -> None:
    """Async render path should also reset grouping when type changes."""
    renderer, console = _make_renderer()
    renderer._get_banner_color = Mock(return_value="blue")

    file_msg = FileContentMessage(
        path="/src/a.py",
        content="a",
        start_line=None,
        num_lines=None,
        total_lines=1,
        num_tokens=1,
    )
    grep_msg = GrepResultMessage(
        search_term="needle",
        directory="/src",
        matches=[],
        total_matches=0,
        files_searched=1,
    )

    await renderer.render(file_msg)
    await renderer.render(grep_msg)

    printed = [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]

    assert any("READ FILE" in p for p in printed), "Missing READ FILE banner"
    assert any("GREP" in p for p in printed), "Missing GREP banner"
