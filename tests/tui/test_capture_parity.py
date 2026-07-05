"""Phase 1: the capture bridge renders every message type without crashing,
reusing the classic Rich formatting (Option B).

Renderable types must produce styled Text; interactive/animated types and
AgentResponseMessage (which the classic renderer skips) must produce None.
"""

import pytest
from rich.text import Text

from code_puppy.tui.capture import RichCaptureFormatter
from code_puppy.messaging import (
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
    SkillListMessage,
    SpinnerControl,
    StatusPanelMessage,
    SubAgentInvocationMessage,
    TextMessage,
    UserInputRequest,
    VersionCheckMessage,
)


def _renderable_messages():
    return [
        TextMessage(level=MessageLevel.INFO, text="hello"),
        TextMessage(level=MessageLevel.ERROR, text="boom"),
        FileContentMessage(path="a.py", content="x=1", total_lines=1, num_tokens=3),
        GrepResultMessage(
            search_term="todo",
            directory=".",
            matches=[GrepMatch(file_path="a.py", line_number=1, line_content="todo")],
            total_matches=1,
            files_searched=1,
        ),
        DiffMessage(
            path="a.py",
            operation="create",
            new_content="x = 1",
            diff_lines=[DiffLine(line_number=1, type="add", content="x = 1")],
        ),
        ShellStartMessage(command="ls -la"),
        ShellLineMessage(line="some output", stream="stdout"),
        AgentReasoningMessage(reasoning="thinking", next_steps="do X"),
        SubAgentInvocationMessage(
            agent_name="cooper", session_id="s1", prompt="go", is_new_session=True
        ),
        DividerMessage(),
        StatusPanelMessage(title="Status", fields={"model": "opus"}),
        VersionCheckMessage(
            current_version="1.0.0", latest_version="1.1.0", update_available=True
        ),
        SkillListMessage(skills=[], total_count=0),
        SkillActivateMessage(
            skill_name="demo",
            skill_path="/tmp/demo",
            content_preview="hi",
            resource_count=0,
        ),
    ]


def _config_dependent_messages():
    """Whether these render depends on user config / output level. The bridge
    must faithfully mirror the classic gates, so we only assert it never
    crashes and returns Text-or-None.
    """
    return [
        FileListingMessage(
            directory=".",
            recursive=False,
            total_size=10,
            dir_count=0,
            file_count=1,
            files=[FileEntry(path="a.py", type="file", size=10, depth=0)],
        ),
        ShellOutputMessage(
            command="ls", stdout="a\nb\n", exit_code=0, duration_seconds=0.05
        ),
    ]


def _skipped_messages():
    return [
        AgentResponseMessage(content="streamed elsewhere", is_markdown=True),
        SpinnerControl(action="start", spinner_id="s"),
        UserInputRequest(prompt_id="p", prompt_text="name?"),
        ConfirmationRequest(prompt_id="p", title="Sure?", description="confirm"),
        SelectionRequest(prompt_id="p", prompt_text="pick", options=["a", "b"]),
    ]


@pytest.mark.parametrize("message", _renderable_messages())
def test_renderable_types_produce_text(message):
    fmt = RichCaptureFormatter()
    out = fmt.format(message, width=100)
    assert isinstance(out, Text), f"{type(message).__name__} produced no Text"
    assert out.plain.strip(), f"{type(message).__name__} produced empty text"


@pytest.mark.parametrize("message", _config_dependent_messages())
def test_config_dependent_types_never_crash(message):
    fmt = RichCaptureFormatter()
    out = fmt.format(message, width=100)
    assert out is None or isinstance(out, Text)


@pytest.mark.parametrize("message", _skipped_messages())
def test_skipped_types_return_none(message):
    fmt = RichCaptureFormatter()
    assert fmt.format(message, width=100) is None


def test_diff_output_carries_color_spans():
    fmt = RichCaptureFormatter()
    out = fmt.format(
        DiffMessage(
            path="a.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new line"),
                DiffLine(line_number=2, type="remove", content="old line"),
            ],
        ),
        width=100,
    )
    assert isinstance(out, Text)
    # ANSI from the diff formatter must survive as style spans, not plain text.
    assert len(out.spans) > 0


def test_formatter_never_raises_on_garbage():
    fmt = RichCaptureFormatter()

    class _Weird:
        category = None

        def __repr__(self):
            return "<weird>"

    # Unknown type hits the classic 'Unknown message' branch -> still Text.
    out = fmt.format(_Weird(), width=80)
    assert out is None or isinstance(out, Text)
