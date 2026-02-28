"""Tests for code_puppy.messaging.rich_renderer."""

import asyncio
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    AgentReasoningMessage,
    AgentResponseMessage,
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
    SkillActivateMessage,
    SkillEntry,
    SkillListMessage,
    SpinnerControl,
    StatusPanelMessage,
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    TextMessage,
    UniversalConstructorMessage,
    UserInputRequest,
    VersionCheckMessage,
)
from code_puppy.messaging.rich_renderer import (
    RendererProtocol,
    RichConsoleRenderer,
)


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


@pytest.fixture
def renderer(bus, console):
    return RichConsoleRenderer(bus, console=console)


def output(console):
    return console.file.getvalue()


# =========================================================================
# Lifecycle
# =========================================================================


def test_start_stop(renderer, bus):
    renderer.start()
    assert renderer._running
    time.sleep(0.05)
    renderer.stop()
    assert not renderer._running


def test_start_twice(renderer):
    renderer.start()
    renderer.start()  # No-op
    renderer.stop()


def test_console_property(renderer, console):
    assert renderer.console is console


@pytest.mark.asyncio
async def test_start_stop_async(renderer, bus):
    await renderer.start_async()
    assert renderer._running
    await renderer.stop_async()
    assert not renderer._running


@pytest.mark.asyncio
async def test_start_async_processes_buffer(renderer, bus):
    # Buffer a message first
    bus.emit(TextMessage(level=MessageLevel.INFO, text="buffered"))
    await renderer.start_async()
    assert "buffered" in output(renderer.console)
    await renderer.stop_async()


def test_consume_loop_processes_buffered(renderer, bus):
    bus.emit(TextMessage(level=MessageLevel.INFO, text="buf"))
    renderer.start()
    time.sleep(0.1)
    renderer.stop()
    assert "buf" in output(renderer.console)


def test_render_sync_error_handling(renderer, console):
    """Render errors should be caught and printed."""
    # Force _do_render to raise
    with patch.object(renderer, "_do_render", side_effect=RuntimeError("test err")):
        msg = TextMessage(level=MessageLevel.INFO, text="hi")
        renderer._render_sync(msg)
    out = output(console)
    assert "Render error" in out
    assert "test err" in out


# =========================================================================
# Text Messages
# =========================================================================


def test_render_text_all_levels(renderer, console):
    for level in MessageLevel:
        renderer._render_text(TextMessage(level=level, text=f"msg-{level.value}"))
    out = output(console)
    assert "msg-info" in out
    assert "msg-error" in out


def test_render_text_version_dim(renderer, console):
    renderer._render_text(
        TextMessage(level=MessageLevel.INFO, text="Current version: 1.0")
    )
    renderer._render_text(
        TextMessage(level=MessageLevel.INFO, text="Latest version: 2.0")
    )


def test_get_level_prefix(renderer):
    assert renderer._get_level_prefix(MessageLevel.ERROR) == "✗ "
    assert renderer._get_level_prefix(MessageLevel.WARNING) == "⚠ "
    assert renderer._get_level_prefix(MessageLevel.SUCCESS) == "✓ "
    assert renderer._get_level_prefix(MessageLevel.INFO) == "ℹ "
    assert renderer._get_level_prefix(MessageLevel.DEBUG) == "• "


# =========================================================================
# File Operations
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_listing(mock_sub, renderer, console):
    msg = FileListingMessage(
        directory="/tmp/test",
        files=[
            FileEntry(path="file.py", type="file", size=100, depth=0),
            FileEntry(path="subdir", type="dir", size=0, depth=0),
            FileEntry(path="subdir/nested.py", type="file", size=200, depth=0),
        ],
        recursive=True,
        file_count=2,
        dir_count=1,
        total_size=300,
    )
    renderer._render_file_listing(msg)
    out = output(console)
    assert "file.py" in out or "DIRECTORY" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_render_file_listing_suppressed(mock_v, mock_sub, renderer, console):
    msg = FileListingMessage(
        directory="/tmp",
        files=[],
        recursive=False,
        file_count=0,
        dir_count=0,
        total_size=0,
    )
    renderer._render_file_listing(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_content(mock_sub, renderer, console):
    msg = FileContentMessage(
        path="/tmp/test.py",
        content="print('hello')",
        start_line=10,
        num_lines=5,
        total_lines=100,
        num_tokens=20,
    )
    renderer._render_file_content(msg)
    out = output(console)
    assert "test.py" in out
    assert "10" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_content_no_lines(mock_sub, renderer, console):
    msg = FileContentMessage(
        path="/tmp/test.py",
        content="hello",
        total_lines=1,
        num_tokens=5,
    )
    renderer._render_file_content(msg)
    out = output(console)
    assert "test.py" in out


# =========================================================================
# Grep
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_grep_result_no_matches(mock_sub, renderer, console):
    msg = GrepResultMessage(
        directory="/tmp",
        search_term="foo",
        matches=[],
        total_matches=0,
        files_searched=10,
        verbose=False,
    )
    renderer._render_grep_result(msg)
    out = output(console)
    assert "No matches" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_grep_result_concise(mock_sub, renderer, console):
    msg = GrepResultMessage(
        directory="/tmp",
        search_term="foo",
        matches=[
            GrepMatch(file_path="a.py", line_number=1, line_content="foo bar"),
            GrepMatch(file_path="a.py", line_number=5, line_content="foo baz"),
        ],
        total_matches=2,
        files_searched=10,
        verbose=False,
    )
    renderer._render_grep_result(msg)
    out = output(console)
    assert "2 matches" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_grep_result_verbose(mock_sub, renderer, console):
    msg = GrepResultMessage(
        directory="/tmp",
        search_term="foo",
        matches=[
            GrepMatch(file_path="a.py", line_number=1, line_content="foo bar"),
        ],
        total_matches=1,
        files_searched=10,
        verbose=True,
    )
    renderer._render_grep_result(msg)
    out = output(console)
    assert "1 match" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_grep_result_verbose_flag_search(mock_sub, renderer, console):
    msg = GrepResultMessage(
        directory="/tmp",
        search_term="--ignore-case foo",
        matches=[
            GrepMatch(file_path="a.py", line_number=1, line_content="FOO bar"),
        ],
        total_matches=1,
        files_searched=10,
        verbose=True,
    )
    renderer._render_grep_result(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_grep_result_verbose_all_flags(mock_sub, renderer, console):
    """When all parts start with -, highlighted_line = line."""
    msg = GrepResultMessage(
        directory="/tmp",
        search_term="--ignore-case",
        matches=[
            GrepMatch(file_path="a.py", line_number=1, line_content="some line"),
        ],
        total_matches=1,
        files_searched=10,
        verbose=True,
    )
    renderer._render_grep_result(msg)


# =========================================================================
# Diff
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_diff(mock_sub, renderer, console):
    msg = DiffMessage(
        path="test.py",
        operation="modify",
        diff_lines=[
            DiffLine(line_number=0, type="context", content="--- a/test.py"),
            DiffLine(line_number=0, type="context", content="+++ b/test.py"),
            DiffLine(line_number=0, type="context", content="@@ -1,3 +1,3 @@"),
            DiffLine(line_number=0, type="remove", content="old line"),
            DiffLine(line_number=0, type="add", content="new line"),
            DiffLine(line_number=0, type="context", content="unchanged"),
        ],
    )
    renderer._render_diff(msg)
    out = output(console)
    assert "EDIT FILE" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_diff_create(mock_sub, renderer, console):
    msg = DiffMessage(path="new.py", operation="create", diff_lines=[])
    renderer._render_diff(msg)
    out = output(console)
    assert "CREATE" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_diff_delete(mock_sub, renderer, console):
    msg = DiffMessage(path="old.py", operation="delete", diff_lines=[])
    renderer._render_diff(msg)


# =========================================================================
# Shell
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_shell_start(mock_sub, renderer, console):
    msg = ShellStartMessage(command="ls -la", cwd="/tmp", timeout=30, background=False)
    renderer._render_shell_start(msg)
    out = output(console)
    assert "ls -la" in out
    assert "/tmp" in out
    assert "30" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_shell_start_background(mock_sub, renderer, console):
    msg = ShellStartMessage(command="server", cwd=None, timeout=60, background=True)
    renderer._render_shell_start(msg)
    out = output(console)
    assert "BACKGROUND" in out


def test_render_shell_line(renderer, console):
    msg = ShellLineMessage(line="hello output", stream="stdout")
    renderer._render_shell_line(msg)
    out = output(console)
    assert "hello output" in out


def test_render_shell_line_with_cr(renderer, console):
    msg = ShellLineMessage(line="progress\r50%", stream="stdout")
    renderer._render_shell_line(msg)


def test_render_shell_output(renderer, console):
    msg = ShellOutputMessage(
        command="ls", exit_code=0, stdout="", stderr="", duration_seconds=0.5
    )
    renderer._render_shell_output(msg)


# =========================================================================
# Agent Messages
# =========================================================================


def test_render_agent_reasoning(renderer, console):
    msg = AgentReasoningMessage(reasoning="I think...", next_steps="Do X")
    renderer._render_agent_reasoning(msg)
    out = output(console)
    assert "AGENT REASONING" in out


def test_render_agent_reasoning_no_steps(renderer, console):
    msg = AgentReasoningMessage(reasoning="I think...", next_steps="")
    renderer._render_agent_reasoning(msg)


def test_render_agent_response(renderer, console):
    msg = AgentResponseMessage(content="**bold**", is_markdown=True)
    renderer._render_agent_response(msg)
    out = output(console)
    assert "AGENT RESPONSE" in out


def test_render_agent_response_plain(renderer, console):
    msg = AgentResponseMessage(content="plain text", is_markdown=False)
    renderer._render_agent_response(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_subagent_invocation(mock_sub, renderer, console):
    msg = SubAgentInvocationMessage(
        agent_name="qa-agent",
        session_id="sess-1",
        prompt="Do the thing" * 50,  # > 200 chars
        is_new_session=True,
        message_count=0,
    )
    renderer._render_subagent_invocation(msg)
    out = output(console)
    assert "qa-agent" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_subagent_invocation_continuing(mock_sub, renderer, console):
    msg = SubAgentInvocationMessage(
        agent_name="qa",
        session_id="s1",
        prompt="short",
        is_new_session=False,
        message_count=5,
    )
    renderer._render_subagent_invocation(msg)
    out = output(console)
    assert "Continuing" in out


def test_render_subagent_response(renderer, console):
    msg = SubAgentResponseMessage(
        agent_name="qa",
        session_id="s1",
        response="All good",
        message_count=3,
    )
    renderer._render_subagent_response(msg)
    out = output(console)
    assert "AGENT RESPONSE" in out


# =========================================================================
# Universal Constructor
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_universal_constructor_success(mock_sub, renderer, console):
    msg = UniversalConstructorMessage(
        action="build",
        tool_name="my_tool",
        success=True,
        summary="Built successfully",
        details="All good",
    )
    renderer._render_universal_constructor(msg)
    out = output(console)
    assert "BUILD" in out
    assert "my_tool" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_universal_constructor_failure(mock_sub, renderer, console):
    msg = UniversalConstructorMessage(
        action="build",
        tool_name=None,
        success=False,
        summary="Failed",
        details=None,
    )
    renderer._render_universal_constructor(msg)
    out = output(console)
    assert "✗" in out


# =========================================================================
# User interaction (async)
# =========================================================================


@pytest.mark.asyncio
async def test_render_user_input_request(renderer, bus, console):
    msg = UserInputRequest(
        prompt_id="p1",
        prompt_text="Enter name",
        default_value="default",
        input_type="text",
    )
    with patch.object(console, "input", return_value=""):
        await renderer._render_user_input_request(msg)


@pytest.mark.asyncio
async def test_render_user_input_password(renderer, bus, console):
    msg = UserInputRequest(
        prompt_id="p1",
        prompt_text="Password",
        input_type="password",
    )
    with patch.object(console, "input", return_value="secret"):
        await renderer._render_user_input_request(msg)


@pytest.mark.asyncio
async def test_render_confirmation_request(renderer, bus, console):
    msg = ConfirmationRequest(
        prompt_id="p1",
        title="Confirm?",
        description="Are you sure?",
        options=["Yes", "No"],
        allow_feedback=False,
    )
    with patch.object(console, "input", return_value="y"):
        await renderer._render_confirmation_request(msg)


@pytest.mark.asyncio
async def test_render_confirmation_with_feedback(renderer, bus, console):
    msg = ConfirmationRequest(
        prompt_id="p1",
        title="Confirm?",
        description="Sure?",
        options=["Yes", "No"],
        allow_feedback=True,
    )
    with patch.object(console, "input", side_effect=["y", "looks good"]):
        await renderer._render_confirmation_request(msg)


@pytest.mark.asyncio
async def test_render_confirmation_invalid_then_valid(renderer, bus, console):
    msg = ConfirmationRequest(
        prompt_id="p1",
        title="Confirm?",
        description="Sure?",
        options=["Yes", "No"],
        allow_feedback=False,
    )
    with patch.object(console, "input", side_effect=["invalid", "n"]):
        await renderer._render_confirmation_request(msg)


@pytest.mark.asyncio
async def test_render_confirmation_no_feedback(renderer, bus, console):
    msg = ConfirmationRequest(
        prompt_id="p1",
        title="Confirm?",
        description="Sure?",
        options=["Yes", "No"],
        allow_feedback=True,
    )
    with patch.object(console, "input", side_effect=["yes", ""]):
        await renderer._render_confirmation_request(msg)


@pytest.mark.asyncio
async def test_render_selection_request(renderer, bus, console):
    msg = SelectionRequest(
        prompt_id="p1",
        prompt_text="Pick one",
        options=["A", "B", "C"],
        allow_cancel=True,
    )
    renderer._console = MagicMock(spec=Console)
    renderer._console.input = MagicMock(return_value="2")
    renderer._console.print = MagicMock()
    await renderer._render_selection_request(msg)


@pytest.mark.asyncio
async def test_render_selection_invalid_then_valid(renderer, bus, console):
    msg = SelectionRequest(
        prompt_id="p1",
        prompt_text="Pick",
        options=["A", "B"],
        allow_cancel=False,
    )
    mock_console = MagicMock()
    mock_console.input.side_effect = ["bad", "99", "1"]
    renderer._console = mock_console
    await renderer._render_selection_request(msg)


# =========================================================================
# Control Messages
# =========================================================================


def test_render_spinner_start(renderer, console):
    msg = SpinnerControl(action="start", spinner_id="s1", text="Loading...")
    renderer._render_spinner_control(msg)
    assert "Loading" in output(console)


def test_render_spinner_update(renderer, console):
    msg = SpinnerControl(action="update", spinner_id="s1", text="Still loading...")
    renderer._render_spinner_control(msg)


def test_render_spinner_stop(renderer, console):
    msg = SpinnerControl(action="stop", spinner_id="s1")
    renderer._render_spinner_control(msg)


def test_render_divider_light(renderer, console):
    msg = DividerMessage(style="light")
    renderer._render_divider(msg)


def test_render_divider_heavy(renderer, console):
    msg = DividerMessage(style="heavy")
    renderer._render_divider(msg)


def test_render_divider_double(renderer, console):
    msg = DividerMessage(style="double")
    renderer._render_divider(msg)


def test_render_divider_default(renderer, console):
    # Test the default 'light' style
    msg = DividerMessage()
    renderer._render_divider(msg)


# =========================================================================
# Status / Version
# =========================================================================


def test_render_status_panel(renderer, console):
    msg = StatusPanelMessage(
        title="Status",
        fields={"Key1": "Val1", "Key2": "Val2"},
    )
    renderer._render_status_panel(msg)
    out = output(console)
    assert "Status" in out


def test_render_version_check_update(renderer, console):
    msg = VersionCheckMessage(
        current_version="1.0",
        latest_version="2.0",
        update_available=True,
    )
    renderer._render_version_check(msg)
    out = output(console)
    assert "Update" in out or "1.0" in out


def test_render_version_check_current(renderer, console):
    msg = VersionCheckMessage(
        current_version="2.0",
        latest_version="2.0",
        update_available=False,
    )
    renderer._render_version_check(msg)
    out = output(console)
    assert "latest" in out


# =========================================================================
# Skills
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_skill_list(mock_sub, renderer, console):
    msg = SkillListMessage(
        skills=[
            SkillEntry(
                name="skill1",
                description="A long description that is more than fifty characters to test truncation behavior",
                path="/path",
                tags=["tag1", "tag2"],
                enabled=True,
            ),
            SkillEntry(
                name="skill2",
                description="Short",
                path="/path2",
                tags=[],
                enabled=False,
            ),
        ],
        total_count=2,
        query="test",
    )
    renderer._render_skill_list(msg)
    out = output(console)
    assert "skill1" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_skill_list_empty(mock_sub, renderer, console):
    msg = SkillListMessage(skills=[], total_count=0, query=None)
    renderer._render_skill_list(msg)
    out = output(console)
    assert "No skills" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_skill_activate_success(mock_sub, renderer, console):
    msg = SkillActivateMessage(
        skill_name="skill1",
        success=True,
        skill_path="/path/skill1",
        resource_count=3,
        content_preview="Some preview content " * 10,  # > 100 chars
    )
    renderer._render_skill_activate(msg)
    out = output(console)
    assert "skill1" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_skill_activate_failure(mock_sub, renderer, console):
    msg = SkillActivateMessage(
        skill_name="skill1",
        success=False,
        skill_path="",
        resource_count=0,
        content_preview="",
    )
    renderer._render_skill_activate(msg)
    out = output(console)
    assert "failed" in out.lower()


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_skill_activate_no_resources(mock_sub, renderer, console):
    msg = SkillActivateMessage(
        skill_name="skill1",
        success=True,
        skill_path="/path",
        resource_count=0,
        content_preview="",
    )
    renderer._render_skill_activate(msg)


# =========================================================================
# Dispatch (_do_render) - route through the full dispatch chain
# =========================================================================


def test_do_render_unknown_type(renderer, console):
    msg = MagicMock()
    renderer._do_render(msg)
    out = output(console)
    assert "Unknown" in out or "unknown" in out.lower() or "MagicMock" in out


def test_do_render_all_message_types(renderer, console):
    """Route each message type through _do_render to cover dispatch branches."""
    messages = [
        TextMessage(level=MessageLevel.INFO, text="dispatch test"),
        FileContentMessage(path="f.py", content="x", total_lines=1, num_tokens=1),
        GrepResultMessage(
            directory=".",
            search_term="x",
            matches=[],
            total_matches=0,
            files_searched=0,
            verbose=False,
        ),
        DiffMessage(path="f.py", operation="modify", diff_lines=[]),
        ShellStartMessage(command="ls", timeout=30, background=False),
        ShellLineMessage(line="out", stream="stdout"),
        ShellOutputMessage(command="ls", exit_code=0, duration_seconds=0.1),
        AgentReasoningMessage(reasoning="think", next_steps=""),
        AgentResponseMessage(content="resp", is_markdown=False),
        SubAgentResponseMessage(
            agent_name="a", session_id="s", response="r", message_count=1
        ),
        SpinnerControl(action="start", spinner_id="s1", text="Loading"),
        DividerMessage(),
        StatusPanelMessage(title="T", fields={"k": "v"}),
        VersionCheckMessage(
            current_version="1.0",
            latest_version="1.0",
            update_available=False,
        ),
        UserInputRequest(prompt_id="p1", prompt_text="Enter", input_type="text"),
        ConfirmationRequest(
            prompt_id="p1",
            title="T",
            description="D",
            options=["Y", "N"],
            allow_feedback=False,
        ),
        SelectionRequest(
            prompt_id="p1",
            prompt_text="Pick",
            options=["A"],
            allow_cancel=False,
        ),
    ]
    for msg in messages:
        renderer._do_render(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_do_render_file_listing_dispatch(mock_sub, renderer, console):
    msg = FileListingMessage(
        directory="/tmp",
        files=[],
        recursive=False,
        file_count=0,
        dir_count=0,
        total_size=0,
    )
    renderer._do_render(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_do_render_subagent_invocation_dispatch(mock_sub, renderer, console):
    msg = SubAgentInvocationMessage(
        agent_name="a",
        session_id="s",
        prompt="p",
        is_new_session=True,
        message_count=0,
    )
    renderer._do_render(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_do_render_universal_constructor_dispatch(mock_sub, renderer, console):
    msg = UniversalConstructorMessage(
        action="test",
        success=True,
        summary="ok",
    )
    renderer._do_render(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_do_render_skill_list_dispatch(mock_sub, renderer, console):
    msg = SkillListMessage(skills=[], total_count=0)
    renderer._do_render(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_do_render_skill_activate_dispatch(mock_sub, renderer, console):
    msg = SkillActivateMessage(
        skill_name="s",
        success=True,
        skill_path="/p",
        resource_count=0,
        content_preview="",
    )
    renderer._do_render(msg)


# =========================================================================
# Async render dispatch
# =========================================================================


@pytest.mark.asyncio
async def test_render_dispatches_to_sync(renderer, console):
    msg = TextMessage(level=MessageLevel.INFO, text="async dispatch")
    await renderer.render(msg)
    assert "async dispatch" in output(console)


# =========================================================================
# Helpers
# =========================================================================


def test_format_size(renderer):
    assert renderer._format_size(500) == "500 B"
    assert "KB" in renderer._format_size(2048)
    assert "MB" in renderer._format_size(2 * 1024 * 1024)
    assert "GB" in renderer._format_size(2 * 1024 * 1024 * 1024)


def test_get_file_icon(renderer):
    assert renderer._get_file_icon("test.py") == "🐍"
    assert renderer._get_file_icon("test.js") == "📜"
    assert renderer._get_file_icon("test.html") == "🌐"
    assert renderer._get_file_icon("test.css") == "🎨"
    assert renderer._get_file_icon("test.md") == "📝"
    assert renderer._get_file_icon("test.json") == "⚙️"
    assert renderer._get_file_icon("test.jpg") == "🖼️"
    assert renderer._get_file_icon("test.mp3") == "🎵"
    assert renderer._get_file_icon("test.mp4") == "🎬"
    assert renderer._get_file_icon("test.pdf") == "📄"
    assert renderer._get_file_icon("test.zip") == "📦"
    assert renderer._get_file_icon("test.exe") == "⚡"
    assert renderer._get_file_icon("test.unknown") == "📄"


def test_get_banner_color(renderer):
    with patch("code_puppy.config.get_banner_color", return_value="blue"):
        assert renderer._get_banner_color("test") == "blue"


def test_format_banner(renderer):
    with patch("code_puppy.config.get_banner_color", return_value="blue"):
        result = renderer._format_banner("test", "HELLO")
        assert "HELLO" in result
        assert "blue" in result


def test_should_suppress_subagent_output(renderer):
    with patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False):
        assert not renderer._should_suppress_subagent_output()
    with patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True):
        with patch(
            "code_puppy.messaging.rich_renderer.get_subagent_verbose",
            return_value=True,
        ):
            assert not renderer._should_suppress_subagent_output()
        with patch(
            "code_puppy.messaging.rich_renderer.get_subagent_verbose",
            return_value=False,
        ):
            assert renderer._should_suppress_subagent_output()


# =========================================================================
# RendererProtocol
# =========================================================================


def test_renderer_protocol():
    assert isinstance(RichConsoleRenderer(MessageBus()), RendererProtocol)


# =========================================================================
# Async render() dispatch
# =========================================================================


@pytest.mark.asyncio
async def test_async_render_user_input(renderer, bus):
    """render() dispatches UserInputRequest to async handler."""
    msg = UserInputRequest(prompt_id="p1", prompt_text="Enter", input_type="text")
    renderer._render_user_input_request = MagicMock(return_value=asyncio.sleep(0))
    await renderer.render(msg)


@pytest.mark.asyncio
async def test_async_render_confirmation(renderer, bus):
    msg = ConfirmationRequest(
        prompt_id="p1",
        title="T",
        description="D",
        options=["Y", "N"],
        allow_feedback=False,
    )
    renderer._render_confirmation_request = MagicMock(return_value=asyncio.sleep(0))
    await renderer.render(msg)


@pytest.mark.asyncio
async def test_async_render_selection(renderer, bus):
    msg = SelectionRequest(
        prompt_id="p1",
        prompt_text="Pick",
        options=["A"],
        allow_cancel=False,
    )
    renderer._render_selection_request = MagicMock(return_value=asyncio.sleep(0))
    await renderer.render(msg)


@pytest.mark.asyncio
async def test_async_render_fallback_to_sync(renderer, bus, console):
    msg = TextMessage(level=MessageLevel.INFO, text="via render")
    await renderer.render(msg)
    assert "via render" in output(console)


# =========================================================================
# Sync start/stop lifecycle
# =========================================================================


def test_start_sync_stop_sync(bus):
    """Test the sync consume loop thread."""
    console = Console(file=StringIO(), force_terminal=False, width=120)
    renderer = RichConsoleRenderer(bus, console=console)
    renderer.start()
    assert renderer._running
    time.sleep(0.05)  # let consume loop run, hit the sleep(0.01) path
    renderer.stop()
    assert not renderer._running


@pytest.mark.asyncio
async def test_start_async_double_start(bus):
    """start_async when already running is a no-op."""
    console = Console(file=StringIO(), force_terminal=False, width=120)
    renderer = RichConsoleRenderer(bus, console=console)
    renderer._running = True
    await renderer.start_async()  # should return immediately
    assert renderer._running


def test_render_sync_error(bus):
    """_render_sync catches exceptions from _do_render."""
    console = Console(file=StringIO(), force_terminal=False, width=120)
    renderer = RichConsoleRenderer(bus, console=console)
    with patch.object(renderer, "_do_render", side_effect=RuntimeError("boom")):
        renderer._render_sync(TextMessage(level=MessageLevel.INFO, text="x"))
    assert "Render error" in console.file.getvalue()


# =========================================================================
# Sub-agent suppression tests
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_file_content(mv, ms, renderer, console):
    msg = FileContentMessage(path="f.py", content="x", total_lines=1, num_tokens=1)
    renderer._render_file_content(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_grep_result(mv, ms, renderer, console):
    msg = GrepResultMessage(
        directory=".",
        search_term="x",
        matches=[],
        total_matches=0,
        files_searched=0,
        verbose=False,
    )
    renderer._render_grep_result(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_diff(mv, ms, renderer, console):
    msg = DiffMessage(path="f.py", operation="modify", diff_lines=[])
    renderer._render_diff(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_shell_start(mv, ms, renderer, console):
    msg = ShellStartMessage(command="ls", timeout=30, background=False)
    renderer._render_shell_start(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_subagent_invocation(mv, ms, renderer, console):
    msg = SubAgentInvocationMessage(
        agent_name="a",
        session_id="s",
        prompt="p",
        is_new_session=True,
        message_count=0,
    )
    renderer._render_subagent_invocation(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_universal_constructor(mv, ms, renderer, console):
    msg = UniversalConstructorMessage(
        action="test",
        success=True,
        summary="ok",
    )
    renderer._render_universal_constructor(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_skill_list(mv, ms, renderer, console):
    msg = SkillListMessage(skills=[], total_count=0)
    renderer._render_skill_list(msg)
    assert output(console) == ""


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=True)
@patch("code_puppy.messaging.rich_renderer.get_subagent_verbose", return_value=False)
def test_suppress_skill_activate(mv, ms, renderer, console):
    msg = SkillActivateMessage(
        skill_name="s",
        success=True,
        skill_path="/p",
        resource_count=0,
        content_preview="",
    )
    renderer._render_skill_activate(msg)
    assert output(console) == ""


# =========================================================================
# File listing edge cases
# =========================================================================


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_listing_nested_dirs(mock_sub, renderer, console):
    msg = FileListingMessage(
        directory="/project",
        files=[
            FileEntry(path="README.md", type="file", size=500, depth=0),
            FileEntry(path="src", type="dir", size=0, depth=0),
            FileEntry(path="src/main.py", type="file", size=1000, depth=0),
            FileEntry(path="src/utils", type="dir", size=0, depth=0),
            FileEntry(path="src/utils/helper.py", type="file", size=200, depth=0),
        ],
        recursive=True,
        file_count=3,
        dir_count=2,
        total_size=1700,
    )
    renderer._render_file_listing(msg)
    out = output(console)
    assert "Summary" in out


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_listing_root_files_only(mock_sub, renderer, console):
    msg = FileListingMessage(
        directory="/project",
        files=[
            FileEntry(path="a.py", type="file", size=0, depth=0),
            FileEntry(path="b.py", type="file", size=100, depth=0),
        ],
        recursive=False,
        file_count=2,
        dir_count=0,
        total_size=100,
    )
    renderer._render_file_listing(msg)


@patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
def test_render_file_listing_single_file_single_dir(mock_sub, renderer, console):
    """Test singular forms in summary."""
    msg = FileListingMessage(
        directory="/project",
        files=[
            FileEntry(path="src", type="dir", size=0, depth=0),
            FileEntry(path="src/a.py", type="file", size=50, depth=0),
        ],
        recursive=True,
        file_count=1,
        dir_count=1,
        total_size=50,
    )
    renderer._render_file_listing(msg)
