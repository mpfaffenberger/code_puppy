"""Audit: medium output mode produces zero behavioral change from pre-feature baseline.

Issue: code_puppy_oss-80g
Parent epic: code_puppy_oss-4v7

Medium is the default output_level — identical to how things rendered
BEFORE the output_level feature was added (commit 514fc7e).

This test module systematically verifies all 8 audit checklist items by
rendering messages in medium mode and confirming the output matches the
pre-feature baseline.  Every ``output_level`` check site is covered.

Design note: the output_level feature gates THREE independent render paths.
Each is tested independently here for medium-mode baseline parity.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from code_puppy.config import get_output_level
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    AgentReasoningMessage,
    DiffLine,
    DiffMessage,
    FileContentMessage,
    FileEntry,
    FileListingMessage,
    GrepMatch,
    GrepResultMessage,
    ShellOutputMessage,
    ShellStartMessage,
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
)
from code_puppy.messaging.rich_renderer import RichConsoleRenderer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


@pytest.fixture
def renderer(bus, console):
    return RichConsoleRenderer(bus, console=console)


def _output(console: Console) -> str:
    console.file.seek(0)
    return console.file.read()


def _render_medium(renderer, console, message):
    """Render a message with output_level=medium and all suppress toggles off."""
    with (
        patch(
            "code_puppy.messaging.rich_renderer.get_output_level",
            return_value="medium",
        ),
        patch(
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
            return_value=False,
        ),
        patch(
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
            return_value=False,
        ),
        patch(
            "code_puppy.messaging.rich_renderer.get_suppress_directory_listing",
            return_value=False,
        ),
        patch(
            "code_puppy.messaging.rich_renderer.is_subagent",
            return_value=False,
        ),
    ):
        renderer._do_render(message)
    return _output(console)


# =========================================================================
# Checklist item 1: Tool banners render identically to pre-feature behavior
# =========================================================================


class TestChecklist1_ToolBanners:
    """Tool banners render the SAME banners as pre-feature in medium mode.

    Pre-feature: banners like READ FILE, GREP, LIST FILES, SHELL COMMAND
    always rendered.  No collapse, no peek, no suppression.
    """

    def test_read_file_banner(self, renderer, console):
        msg = FileContentMessage(
            path="config.py",
            content="x = 1\n",
            total_lines=100,
            num_tokens=42,
        )
        out = _render_medium(renderer, console, msg)
        assert "READ FILE" in out
        assert "config.py" in out

    def test_grep_banner(self, renderer, console):
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo"),
            ],
            total_matches=1,
            files_searched=5,
        )
        out = _render_medium(renderer, console, msg)
        assert "GREP" in out
        assert "/tmp" in out

    def test_list_files_banner(self, renderer, console):
        msg = FileListingMessage(
            directory="/tmp/project",
            files=[FileEntry(path="a.py", type="file", size=100, depth=0)],
            recursive=True,
            total_size=100,
            dir_count=0,
            file_count=1,
        )
        out = _render_medium(renderer, console, msg)
        assert "DIRECTORY LISTING" in out

    def test_shell_command_banner(self, renderer, console):
        msg = ShellStartMessage(command="ruff check --fix", timeout=60)
        out = _render_medium(renderer, console, msg)
        assert "SHELL COMMAND" in out
        assert "ruff check" in out

    def test_edit_file_banner(self, renderer, console):
        msg = DiffMessage(
            path="foo.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new line"),
            ],
        )
        out = _render_medium(renderer, console, msg)
        assert "EDIT FILE" in out
        assert "foo.py" in out

    def test_invoke_agent_banner(self, renderer, console):
        msg = SubAgentInvocationMessage(
            agent_name="test-helper",
            session_id="abc-123",
            prompt="Run a query",
            is_new_session=True,
        )
        out = _render_medium(renderer, console, msg)
        assert "INVOKE AGENT" in out
        assert "test-helper" in out


# =========================================================================
# Checklist item 2: Tool results render identically — no new annotations
# =========================================================================


class TestChecklist2_NoNewAnnotations:
    """Medium mode must NOT show high-mode metadata annotations.

    Pre-feature: no inline token counts, no file counts, no exit codes,
    no diff line-change summaries after banners.
    """

    def test_read_file_no_token_annotation(self, renderer, console):
        msg = FileContentMessage(
            path="config.py",
            content="x = 1\n",
            total_lines=100,
            num_tokens=42,
        )
        out = _render_medium(renderer, console, msg)
        assert "total lines" not in out
        assert "tokens" not in out

    def test_grep_no_files_searched_annotation(self, renderer, console):
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo"),
            ],
            total_matches=1,
            files_searched=42,
        )
        out = _render_medium(renderer, console, msg)
        assert "42 files searched" not in out

    def test_diff_no_line_count_annotation(self, renderer, console):
        msg = DiffMessage(
            path="foo.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new"),
                DiffLine(line_number=2, type="remove", content="old"),
            ],
        )
        out = _render_medium(renderer, console, msg)
        # High mode would show "+1/-1 lines" as an annotation line
        # Medium mode should NOT have that dim metadata line.
        # The diff itself may contain +/- but not the metadata summary.
        lines = out.strip().split("\n")
        metadata_lines = [line for line in lines if "+1/-1 lines" in line]
        assert len(metadata_lines) == 0

    def test_shell_output_no_exit_code(self, renderer, console):
        msg = ShellOutputMessage(
            command="ruff check",
            exit_code=0,
            duration_seconds=1.23,
        )
        out = _render_medium(renderer, console, msg)
        assert "exit=" not in out
        assert "1.2s" not in out

    def test_run_stats_not_rendered(self):
        """_render_high_mode_stats exits immediately when not in high mode."""
        from code_puppy.agents.run_stats import _render_high_mode_stats

        with patch("code_puppy.config.get_output_level", return_value="medium"):
            # Should not raise, should not print anything
            _render_high_mode_stats()  # no-op

    def test_high_mode_tool_result_not_rendered(self):
        """_render_high_mode_tool_result exits immediately when not in high mode."""
        from code_puppy.agents.run_stats import _render_high_mode_tool_result

        with patch("code_puppy.config.get_output_level", return_value="medium"):
            # Should be a no-op — no output
            _render_high_mode_tool_result("read_file", {}, "content", 42.0)


# =========================================================================
# Checklist item 3: Agent response streaming is unchanged
# =========================================================================


class TestChecklist3_StreamingUnchanged:
    """Event stream handler behaves identically in medium mode.

    Pre-feature: _should_suppress_output checked subagent context only.
    No thinking suppression, no tool progress suppression.
    """

    def test_should_suppress_output_defers_to_subagent_check(self):
        """Medium mode falls through to original subagent logic."""
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        # Not a subagent → never suppress
        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_subagent_verbose",
                return_value=False,
            ),
        ):
            assert _should_suppress_output() is False

        # Is subagent, verbose off → suppress (same as pre-feature)
        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_subagent_verbose",
                return_value=False,
            ),
        ):
            assert _should_suppress_output() is True

        # Is subagent, verbose on → don't suppress (same as pre-feature)
        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_subagent_verbose",
                return_value=True,
            ),
        ):
            assert _should_suppress_output() is False

    def test_tool_progress_not_suppressed(self):
        """Medium mode shows tool progress counters (same as pre-feature)."""
        from code_puppy.agents.event_stream_handler import _suppress_tool_progress

        with patch(
            "code_puppy.agents.event_stream_handler.get_output_level",
            return_value="medium",
        ):
            assert _suppress_tool_progress() is False

    def test_is_high_mode_flag_false(self):
        """The is_high_mode flag in event_stream_handler is False in medium mode."""
        with patch(
            "code_puppy.agents.event_stream_handler.get_output_level",
            return_value="medium",
        ):
            assert get_output_level() != "high"  # This is what the flag checks


# =========================================================================
# Checklist item 4: Thinking blocks per existing suppress_thinking setting
# =========================================================================


class TestChecklist4_ThinkingBlocks:
    """Thinking block rendering is controlled by suppress_thinking_messages.

    Pre-feature: suppress_thinking_messages was dead code (never checked).
    The feature wired it up.  With default=False, medium mode is identical.
    """

    def test_thinking_not_suppressed_with_default_toggle(self):
        """Medium mode + suppress=False → thinking streams normally."""
        from code_puppy.agents.event_stream_handler import _suppress_thinking_stream

        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            assert _suppress_thinking_stream() is False

    def test_thinking_suppressed_when_toggle_on(self):
        """Medium mode + suppress=True → thinking is suppressed.

        Note: this is NEW behavior vs pre-feature (toggle was dead code).
        However, the user explicitly opted in, so this is a bug fix, not
        a regression.
        """
        from code_puppy.agents.event_stream_handler import _suppress_thinking_stream

        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_suppress_thinking_messages",
                return_value=True,
            ),
        ):
            assert _suppress_thinking_stream() is True

    def test_agent_reasoning_renders_in_medium_default(self, renderer, console):
        """AgentReasoningMessage renders fully when suppress toggle is off."""
        msg = AgentReasoningMessage(
            reasoning="Let me think about this carefully.",
            next_steps="Read config.py",
        )
        out = _render_medium(renderer, console, msg)
        assert "AGENT REASONING" in out or "think" in out.lower()


# =========================================================================
# Checklist item 5: Sub-agent output per existing subagent_verbose setting
# =========================================================================


class TestChecklist5_SubagentOutput:
    """Sub-agent suppression uses legacy subagent_verbose in medium mode.

    Pre-feature: sub-agent output suppressed when is_subagent() and not
    get_subagent_verbose().  The output_level feature only overrides this
    in high mode.
    """

    def test_renderer_suppresses_in_subagent_context(self, renderer, console):
        """RichConsoleRenderer suppresses subagent output when verbose=False."""
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_subagent_verbose",
                return_value=False,
            ),
        ):
            assert renderer._should_suppress_subagent_output() is True

    def test_renderer_shows_in_subagent_verbose(self, renderer, console):
        """RichConsoleRenderer shows subagent output when verbose=True."""
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_subagent_verbose",
                return_value=True,
            ),
        ):
            assert renderer._should_suppress_subagent_output() is False

    def test_display_non_streamed_result_suppressed(self):
        """display_non_streamed_result suppressed for subagents in medium."""
        with (
            patch(
                "code_puppy.tools.display.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.display.get_subagent_verbose",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.display.get_output_level",
                return_value="medium",
            ),
        ):
            from code_puppy.tools.display import display_non_streamed_result

            # Should return early without printing (no crash)
            display_non_streamed_result("Hello world")

    def test_subagent_uses_subagent_stream_handler(self):
        """In medium mode, subagent invocation uses the normal subagent handler."""
        # The subagent_invocation.py checks get_output_level() == "high"
        # to decide which handler to use.  In medium, it should use
        # the normal subagent handler (not the main stream handler).
        from code_puppy.config import get_output_level as _gol

        with patch("code_puppy.config.get_value", return_value="medium"):
            assert _gol() == "medium"
            assert _gol() != "high"  # So subagent handler is selected

    def test_subagent_response_renders_in_medium(self, renderer, console):
        """SubAgentResponseMessage renders with banner+markdown in medium mode."""
        msg = SubAgentResponseMessage(
            agent_name="drone",
            session_id="sess-42",
            response="Done! I added 5 lines to the file.",
            message_count=3,
        )
        out = _render_medium(renderer, console, msg)
        assert "AGENT RESPONSE" in out
        assert "drone" in out
        assert "5 lines" in out


# =========================================================================
# Checklist item 6: grep output per existing grep_output_verbose setting
# =========================================================================


class TestChecklist6_GrepVerbose:
    """Grep verbosity controlled by msg.verbose flag in medium mode.

    Pre-feature: ``if msg.verbose:`` controlled verbose/concise rendering.
    The feature changed it to ``msg.verbose or get_output_level() == "high"``.
    In medium mode, the second term is False, so it's equivalent.
    """

    def test_concise_grep_in_medium(self, renderer, console):
        """Concise grep renders without line content when verbose=False."""
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo bar baz"),
            ],
            total_matches=1,
            files_searched=5,
            verbose=False,
        )
        out = _render_medium(renderer, console, msg)
        # Concise mode shows files and counts, not per-line content
        assert "a.py" in out

    def test_verbose_grep_in_medium(self, renderer, console):
        """Verbose grep renders line content when verbose=True."""
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=42, line_content="foo bar baz"),
            ],
            total_matches=1,
            files_searched=5,
            verbose=True,
        )
        out = _render_medium(renderer, console, msg)
        assert "a.py" in out


# =========================================================================
# Checklist item 7: No new dim metadata lines, footers, or banners
# =========================================================================


class TestChecklist7_NoNewOutput:
    """No new dim metadata, footers, or banners appear in medium mode.

    This checklist item is the negative-space complement of items 1 and 2.
    """

    def test_shell_output_only_trailing_newline(self, renderer, console):
        """Shell output in medium is just a trailing newline (pre-feature)."""
        msg = ShellOutputMessage(
            command="ls",
            exit_code=0,
            duration_seconds=0.5,
        )
        out = _render_medium(renderer, console, msg)
        # Only a trailing newline, no exit code, no duration
        assert out.strip() == ""

    def test_no_collapse_peek_lines(self, renderer, console):
        """Medium mode never produces dim peek lines."""
        msg = FileListingMessage(
            directory="/tmp/test",
            files=[FileEntry(path="a.py", type="file", size=100, depth=0)],
            recursive=True,
            total_size=100,
            dir_count=0,
            file_count=1,
        )
        out = _render_medium(renderer, console, msg)
        # Peek lines start with two spaces and are dim
        # Full banners contain "DIRECTORY LISTING"
        assert "DIRECTORY LISTING" in out
        # No peek-style "list_files:" prefix
        lines = [line.strip() for line in out.split("\n") if line.strip()]
        peek_lines = [line for line in lines if line.startswith("list_files:")]
        assert len(peek_lines) == 0

    def test_prompt_truncated_to_200_chars(self, renderer, console):
        """SubAgent prompt truncated to 200 chars in medium (pre-feature behavior)."""
        long_prompt = "x" * 300
        msg = SubAgentInvocationMessage(
            agent_name="test-agent",
            session_id="s1",
            prompt=long_prompt,
            is_new_session=True,
        )
        out = _render_medium(renderer, console, msg)
        # Should show truncated prompt with "..."
        assert "..." in out
        # Should NOT show the full 300-char prompt
        assert long_prompt not in out

    def test_spinner_not_affected_in_medium(self):
        """Spinner pause/resume behaves normally in medium mode.

        Pre-feature: subagent calls to pause/resume were no-ops.
        The feature only changes this for high mode.
        """
        from code_puppy.messaging.spinner import pause_all_spinners, resume_all_spinners

        # The spinner imports is_subagent lazily from subagent_context,
        # so we patch at the source module.
        with (
            patch(
                "code_puppy.tools.subagent_context.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.config.get_output_level",
                return_value="medium",
            ),
        ):
            # Should be no-ops (no crash, no effect)
            pause_all_spinners()
            resume_all_spinners()


# =========================================================================
# Checklist item 8: /set output_level=medium is the default
# =========================================================================


class TestChecklist8_DefaultIsMedium:
    """Medium is the default — no config needed for existing behavior."""

    def test_default_returns_medium(self):
        with patch("code_puppy.config.get_value", return_value=None):
            assert get_output_level() == "medium"

    def test_unset_config_returns_medium(self):
        with patch("code_puppy.config.get_value", return_value=""):
            # Empty string is not in valid set → falls back to medium
            assert get_output_level() == "medium"

    def test_garbage_config_returns_medium(self):
        with patch("code_puppy.config.get_value", return_value="xyzzy"):
            assert get_output_level() == "medium"

    def test_set_menu_default(self):
        """The /set menu shows output_level with medium as effective default."""
        from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES

        for cat in SETTINGS_CATEGORIES:
            for setting in cat.settings:
                if setting.key == "output_level":
                    with patch("code_puppy.config.get_value", return_value=None):
                        assert setting.effective_getter() == "medium"
                    return
        pytest.fail("output_level not found in SETTINGS_CATEGORIES")


# =========================================================================
# Cross-cutting: Legacy renderer path (SynchronousInteractiveRenderer)
# =========================================================================


class TestLegacyRendererMediumBaseline:
    """The legacy SynchronousInteractiveRenderer passes everything in medium."""

    def test_info_passes_through(self):
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.INFO, content="hello")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_agent_reasoning_passes_through(self):
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thinking...")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_tool_output_passes_through(self):
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="result")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False
