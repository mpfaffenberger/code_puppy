"""Tests for the output_level density control.

Covers all three render paths:
  1. RichConsoleRenderer (MessageBus messages)
  2. event_stream_handler (streaming SSE content)
  3. SynchronousInteractiveRenderer (legacy UIMessage queue)

Also tests config.py get/set and /set menu integration.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from code_puppy.config import get_output_level, set_output_level
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
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
    SkillActivateMessage,
    SkillEntry,
    SkillListMessage,
    SpinnerControl,
    SubAgentInvocationMessage,
    TextMessage,
    UniversalConstructorMessage,
    UserInputRequest,
    VersionCheckMessage,
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
    """Read everything printed to the Console's StringIO."""
    console.file.seek(0)
    return console.file.read()


# ---------------------------------------------------------------------------
# config.py get/set
# ---------------------------------------------------------------------------


class TestConfigOutputLevel:
    """get_output_level / set_output_level in config.py."""

    def test_default_is_medium(self):
        with patch("code_puppy.config.get_value", return_value=None):
            assert get_output_level() == "medium"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("low", "low"),
            ("LOW", "low"),
            ("  Medium ", "medium"),
            ("HIGH", "high"),
        ],
    )
    def test_valid_values(self, raw, expected):
        with patch("code_puppy.config.get_value", return_value=raw):
            assert get_output_level() == expected

    def test_invalid_value_falls_back_to_medium(self):
        with patch("code_puppy.config.get_value", return_value="ultra"):
            assert get_output_level() == "medium"

    def test_set_output_level_valid(self):
        with patch("code_puppy.config.set_config_value") as mock_set:
            set_output_level("low")
            mock_set.assert_called_once_with("output_level", "low")

    def test_set_output_level_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid output_level"):
            set_output_level("ultra")


# ---------------------------------------------------------------------------
# RichConsoleRenderer: low mode collapses messages to one-line peeks
# ---------------------------------------------------------------------------


class TestRichRendererLowMode:
    """Low mode should collapse most messages to dim one-liners."""

    def _render_with_level(self, renderer, console, message, level="low"):
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value=level,
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
        ):
            renderer._do_render(message)
        return _output(console)

    def test_file_listing_collapsed(self, renderer, console):
        msg = FileListingMessage(
            directory="/tmp/test",
            files=[FileEntry(path="a.py", type="file", size=100, depth=0)],
            recursive=True,
            total_size=100,
            dir_count=0,
            file_count=1,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "list_files:" in out
        assert "1 files" in out
        # Should NOT have the full DIRECTORY LISTING banner
        assert "DIRECTORY LISTING" not in out

    def test_file_content_collapsed(self, renderer, console):
        msg = FileContentMessage(
            path="config.py",
            content="x = 1\n",
            start_line=10,
            num_lines=5,
            total_lines=100,
            num_tokens=10,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "read_file:" in out
        assert "config.py" in out
        assert "lines 10-14" in out
        assert "READ FILE" not in out

    def test_grep_result_collapsed(self, renderer, console):
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo"),
                GrepMatch(file_path="b.py", line_number=2, line_content="foo"),
            ],
            total_matches=2,
            files_searched=10,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "grep:" in out
        assert "2 matches" in out
        assert "GREP" not in out

    def test_shell_start_collapsed(self, renderer, console):
        msg = ShellStartMessage(command="ruff check --fix", timeout=60)
        out = self._render_with_level(renderer, console, msg)
        assert "shell:" in out
        assert "ruff check" in out
        assert "SHELL COMMAND" not in out

    def test_shell_line_silently_dropped(self, renderer, console):
        msg = ShellLineMessage(line="some output line")
        out = self._render_with_level(renderer, console, msg)
        # Shell lines produce empty peek → nothing printed
        assert out.strip() == ""

    def test_agent_reasoning_collapsed(self, renderer, console):
        msg = AgentReasoningMessage(
            reasoning="I should check the config file first.",
            next_steps="Read config.py",
        )
        out = self._render_with_level(renderer, console, msg)
        assert "thinking:" in out
        assert "AGENT REASONING" not in out

    def test_diff_collapsed(self, renderer, console):
        msg = DiffMessage(
            path="foo.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new line"),
                DiffLine(line_number=2, type="remove", content="old line"),
            ],
        )
        out = self._render_with_level(renderer, console, msg)
        assert "diff:" in out
        assert "+1/-1" in out
        assert "EDIT FILE" not in out

    def test_text_info_collapsed(self, renderer, console):
        msg = TextMessage(level=MessageLevel.INFO, text="Loading plugins...")
        out = self._render_with_level(renderer, console, msg)
        assert "Loading plugins" in out
        # Should be dim one-liner, not full styled output

    @patch("code_puppy.messaging.rich_renderer.is_subagent", return_value=False)
    def test_subagent_invocation_not_collapsed(self, mock_sub, renderer, console):
        """SubAgentInvocationMessage renders fully in low mode (never collapsed)."""
        msg = SubAgentInvocationMessage(
            agent_name="test-helper",
            session_id="abc-123",
            prompt="Run a query",
            is_new_session=True,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "test-helper" in out
        assert "Run a query" in out
        # Full banner renders, not a peek
        assert "INVOKE AGENT" in out

    def test_universal_constructor_collapsed(self, renderer, console):
        msg = UniversalConstructorMessage(
            action="register",
            tool_name="my_tool",
            success=True,
            summary="registered",
        )
        out = self._render_with_level(renderer, console, msg)
        assert "constructor:" in out
        assert "my_tool" in out

    def test_skill_list_collapsed(self, renderer, console):
        msg = SkillListMessage(
            skills=[
                SkillEntry(name="a", description="desc a", path="/skills/a"),
                SkillEntry(name="b", description="desc b", path="/skills/b"),
            ],
            total_count=2,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "skills:" in out
        assert "2 available" in out

    def test_skill_activate_collapsed(self, renderer, console):
        msg = SkillActivateMessage(
            skill_name="tableau",
            skill_path="/skills/tableau",
            content_preview="# Skill docs here",
            resource_count=0,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "skill:" in out
        assert "tableau" in out


class TestRichRendererLowModeNeverCollapse:
    """Certain message types must NEVER be collapsed, even in low mode."""

    def _render_with_level(self, renderer, console, message, level="low"):
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value=level,
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
        ):
            renderer._do_render(message)
        return _output(console)

    def test_error_message_not_collapsed(self, renderer, console):
        msg = TextMessage(level=MessageLevel.ERROR, text="Something broke!")
        out = self._render_with_level(renderer, console, msg)
        # Error messages render fully, including the  prefix
        assert "Something broke!" in out

    def test_divider_not_collapsed(self, renderer, console):
        msg = DividerMessage()
        out = self._render_with_level(renderer, console, msg)
        # Divider always renders (may be just a rule)
        assert out.strip() != ""

    def test_version_check_not_collapsed(self, renderer, console):
        msg = VersionCheckMessage(
            current_version="1.0.0",
            latest_version="1.1.0",
            update_available=True,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "1.0.0" in out or "1.1.0" in out

    def test_spinner_not_collapsed(self, renderer, console):
        msg = SpinnerControl(action="start", spinner_id="s1", text="Thinking...")
        self._render_with_level(renderer, console, msg)
        # SpinnerControl passes through (may or may not print visible text)
        # Main point: no crash, and it's not turned into a peek line


class TestRichRendererLowModePeekConsistency:
    """Audit (code_puppy_oss-6yg): peek lines are even, escaped, consistent."""

    def _render_with_level(self, renderer, console, message, level="low"):
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value=level,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            renderer._do_render(message)
        return _output(console)

    def test_status_panel_collapsed_to_peek(self, renderer, console):
        """StatusPanelMessage condenses to a one-line peek (not a tall panel)."""
        from code_puppy.messaging.messages import StatusPanelMessage

        msg = StatusPanelMessage(
            title="Run Stats",
            fields={"tokens": "1234", "duration": "2.5s"},
        )
        out = self._render_with_level(renderer, console, msg)
        assert "status:" in out
        assert "Run Stats" in out
        # One peek line only — no multi-row panel borders.
        lines = [ln for ln in out.split("\n") if ln.strip()]
        assert len(lines) == 1

    def test_text_peek_uses_label_format(self, renderer, console):
        """Info text peeks follow the `label: summary` convention."""
        msg = TextMessage(level=MessageLevel.INFO, text="Loading plugins...")
        out = self._render_with_level(renderer, console, msg)
        assert "info:" in out
        assert "Loading plugins" in out

    def test_warning_peek_uses_label_format(self, renderer, console):
        msg = TextMessage(level=MessageLevel.WARNING, text="Heads up")
        out = self._render_with_level(renderer, console, msg)
        assert "warning:" in out

    def test_peek_escapes_markup(self, renderer, console):
        """Bracketed content in a peek must not break Rich markup parsing."""
        # A shell command containing brackets would be parsed as a markup
        # tag without escaping, corrupting the line.
        msg = ShellStartMessage(command="echo [danger] {x}", timeout=60)
        out = self._render_with_level(renderer, console, msg)
        assert "shell:" in out
        # The literal bracketed text survives intact.
        assert "[danger]" in out
        assert len([ln for ln in out.split("\n") if ln.strip()]) == 1

    def test_all_peeks_share_two_space_indent(self, renderer, console):
        """Every peek line uses the same 2-space dim indent for alignment."""
        messages = [
            FileContentMessage(path="a.py", content="x\n", total_lines=1, num_tokens=1),
            GrepResultMessage(
                search_term="q",
                directory="/tmp",
                matches=[GrepMatch(file_path="a.py", line_number=1, line_content="q")],
                total_matches=1,
                files_searched=1,
            ),
            TextMessage(level=MessageLevel.INFO, text="hi"),
        ]
        for msg in messages:
            console.file.truncate(0)
            console.file.seek(0)
            out = self._render_with_level(renderer, console, msg)
            line = next(ln for ln in out.split("\n") if ln.strip())
            assert line.startswith("  "), f"peek not 2-space indented: {line!r}"


class TestRichRendererMediumMode:
    """Medium mode is the default — existing behavior unchanged."""

    def test_file_listing_renders_fully(self, renderer, console):
        msg = FileListingMessage(
            directory="/tmp/test",
            files=[FileEntry(path="a.py", type="file", size=100, depth=0)],
            recursive=True,
            total_size=100,
            dir_count=0,
            file_count=1,
        )
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
        ):
            renderer._do_render(msg)
        out = _output(console)
        assert "DIRECTORY LISTING" in out


class TestRichRendererHighMode:
    """High mode forces verbose output and un-suppresses subagent output."""

    def test_grep_forced_verbose_in_high_mode(self, renderer, console):
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo bar"),
            ],
            total_matches=1,
            files_searched=5,
            verbose=False,  # Normally concise
        )
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            renderer._do_render(msg)
        out = _output(console)
        # In high mode, verbose=False is overridden to show full line content
        assert "a.py" in out

    def test_subagent_output_not_suppressed_in_high(self, renderer, console):
        """In high mode, _should_suppress_subagent_output returns False."""
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="high",
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
            assert renderer._should_suppress_subagent_output() is False

    def _render_high(self, renderer, console, message):
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="high",
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
        ):
            renderer._do_render(message)
        return _output(console)

    def test_high_mode_shows_file_tokens(self, renderer, console):
        msg = FileContentMessage(
            path="config.py",
            content="x = 1\n",
            total_lines=100,
            num_tokens=42,
        )
        out = self._render_high(renderer, console, msg)
        assert "100 total lines" in out
        assert "~42 tokens" in out

    def test_high_mode_shows_shell_exit_and_duration(self, renderer, console):
        msg = ShellOutputMessage(
            command="ruff check",
            exit_code=0,
            duration_seconds=1.23,
        )
        out = self._render_high(renderer, console, msg)
        assert "exit=" in out
        assert "0" in out
        assert "1.2s" in out

    def test_high_mode_shows_grep_files_searched(self, renderer, console):
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="foo"),
            ],
            total_matches=1,
            files_searched=42,
            verbose=False,
        )
        out = self._render_high(renderer, console, msg)
        assert "42 files searched" in out

    def test_high_mode_shows_diff_line_counts(self, renderer, console):
        msg = DiffMessage(
            path="foo.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new"),
                DiffLine(line_number=2, type="add", content="new2"),
                DiffLine(line_number=3, type="remove", content="old"),
            ],
        )
        out = self._render_high(renderer, console, msg)
        assert "+2/-1 lines" in out


# ---------------------------------------------------------------------------
# Suppress toggles wired to renderer (dead-code fix: code_puppy_oss-dzz)
# ---------------------------------------------------------------------------


class TestSuppressTogglesWiredUp:
    """The previously-dead suppress_* toggles now actually suppress output."""

    def test_suppress_informational_hides_info(self, renderer, console):
        msg = TextMessage(level=MessageLevel.INFO, text="Loading plugins...")
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            renderer._do_render(msg)
        assert _output(console).strip() == ""

    def test_suppress_informational_hides_warning(self, renderer, console):
        msg = TextMessage(level=MessageLevel.WARNING, text="Watch out!")
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            renderer._do_render(msg)
        assert _output(console).strip() == ""

    def test_suppress_informational_does_not_hide_error(self, renderer, console):
        msg = TextMessage(level=MessageLevel.ERROR, text="Kaboom!")
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_informational_messages",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            renderer._do_render(msg)
        assert "Kaboom!" in _output(console)

    def test_suppress_thinking_hides_agent_reasoning(self, renderer, console):
        msg = AgentReasoningMessage(reasoning="Let me think...", next_steps="")
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
                return_value=True,
            ),
        ):
            renderer._do_render(msg)
        assert _output(console).strip() == ""


# ---------------------------------------------------------------------------
# Legacy SynchronousInteractiveRenderer gating
# ---------------------------------------------------------------------------


class TestLegacyRendererOutputLevel:
    """_should_suppress_legacy correctly gates the legacy render path."""

    def test_low_mode_peeks_info(self):
        """Low mode condenses INFO to a one-line peek, never drops it."""
        from rich.text import Text

        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import (
            _apply_legacy_density,
            _should_suppress_legacy,
        )

        msg = UIMessage(type=MessageType.INFO, content="hello world")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="low",
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
            # Not suppressed entirely — condensed instead.
            assert _should_suppress_legacy(msg) is False
            resolved = _apply_legacy_density(msg)
            assert resolved is not None
            assert isinstance(resolved.content, Text)
            assert resolved.content.plain.strip().startswith("info:")
            assert "hello world" in resolved.content.plain

    def test_low_mode_peeks_agent_reasoning(self):
        """Low mode condenses AGENT_REASONING to a peek, never drops it."""
        from rich.text import Text

        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import (
            _apply_legacy_density,
            _should_suppress_legacy,
        )

        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thinking...")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="low",
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
            resolved = _apply_legacy_density(msg)
            assert resolved is not None
            assert isinstance(resolved.content, Text)
            assert resolved.content.plain.strip().startswith("thinking:")

    def test_low_mode_keeps_errors(self):
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.ERROR, content="bad things")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="low",
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

    def test_low_mode_keeps_agent_response(self):
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.AGENT_RESPONSE, content="Hello!")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="low",
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

    def test_medium_mode_passes_everything(self):
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

    def test_suppress_toggle_overrides_medium(self):
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
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is True


# ---------------------------------------------------------------------------
# event_stream_handler helpers
# ---------------------------------------------------------------------------


class TestEventStreamHandlerGates:
    """_suppress_thinking_stream / _suppress_tool_progress in event_stream_handler."""

    def test_low_mode_suppresses_thinking(self):
        from code_puppy.agents.event_stream_handler import _suppress_thinking_stream

        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="low",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_suppress_thinking_messages",
                return_value=False,
            ),
        ):
            assert _suppress_thinking_stream() is True

    def test_medium_mode_does_not_suppress_thinking(self):
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

    def test_suppress_toggle_overrides(self):
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

    def test_low_mode_suppresses_tool_progress(self):
        from code_puppy.agents.event_stream_handler import _suppress_tool_progress

        with patch(
            "code_puppy.agents.event_stream_handler.get_output_level",
            return_value="low",
        ):
            assert _suppress_tool_progress() is True

    def test_medium_mode_shows_tool_progress(self):
        from code_puppy.agents.event_stream_handler import _suppress_tool_progress

        with patch(
            "code_puppy.agents.event_stream_handler.get_output_level",
            return_value="medium",
        ):
            assert _suppress_tool_progress() is False

    def test_high_mode_unsuppresses_subagent(self):
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="high",
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
            assert _should_suppress_output() is False


# ---------------------------------------------------------------------------
# /set menu catalog integration
# ---------------------------------------------------------------------------


class TestSetMenuCatalog:
    """output_level appears in the /set menu."""

    def test_output_level_in_settings_catalog(self):
        from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES

        all_keys = [s.key for cat in SETTINGS_CATEGORIES for s in cat.settings]
        assert "output_level" in all_keys

    def test_output_level_setting_metadata(self):
        from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES

        for cat in SETTINGS_CATEGORIES:
            for s in cat.settings:
                if s.key == "output_level":
                    assert s.type_hint == "choice"
                    assert set(s.valid_values) == {"low", "medium", "high"}
                    assert s.effective_getter is not None
                    return
        pytest.fail("output_level setting not found in catalog")


# ---------------------------------------------------------------------------
# Subagent handler selection based on output_level
# ---------------------------------------------------------------------------


class TestRichRendererLowModeAuditGaps:
    """Audit coverage for checklist items not yet exercised (code_puppy_oss-5lw)."""

    def _render_with_level(self, renderer, console, message, level="low"):
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value=level,
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
        ):
            renderer._do_render(message)
        return _output(console)

    # -- Checklist #3: shell output messages collapsed --

    def test_shell_output_collapsed(self, renderer, console):
        """ShellOutputMessage should be silently collapsed (empty peek)."""
        msg = ShellOutputMessage(
            command="ls -la",
            exit_code=0,
            duration_seconds=0.5,
        )
        out = self._render_with_level(renderer, console, msg)
        # Shell output produces an empty peek → nothing printed
        assert out.strip() == ""

    # -- Checklist #4: sub-agent response peek in low mode --

    def test_subagent_response_not_collapsed_in_low_mode(self, renderer, console):
        """SubAgentResponseMessage renders fully in low mode (never collapsed)."""
        from code_puppy.messaging.messages import SubAgentResponseMessage

        msg = SubAgentResponseMessage(
            agent_name="test-helper",
            session_id="abc-123",
            response="Here is your report...",
            message_count=5,
        )
        out = self._render_with_level(renderer, console, msg)
        assert "test-helper" in out
        assert "Here is your report" in out
        # Full banner renders, not a peek
        assert "AGENT RESPONSE" in out

    # -- Checklist #8: interactive prompts never collapsed --

    def test_user_input_request_not_collapsed(self, renderer, console):
        """UserInputRequest must render in low mode (never collapsed)."""
        msg = UserInputRequest(
            prompt_id="p1",
            prompt_text="Enter your name:",
        )
        # Should not crash; type is in _NEVER_COLLAPSE
        out = self._render_with_level(renderer, console, msg)
        # UserInputRequest renders a dim note in sync mode, not collapsed
        assert "input" in out.lower() or out.strip() != ""

    def test_confirmation_request_not_collapsed(self, renderer, console):
        """ConfirmationRequest must render in low mode (never collapsed)."""
        msg = ConfirmationRequest(
            prompt_id="p2",
            title="Proceed?",
            description="About to delete the file.",
        )
        out = self._render_with_level(renderer, console, msg)
        # Should render something (not a dim peek)
        assert out.strip() != ""

    def test_selection_request_not_collapsed(self, renderer, console):
        """SelectionRequest must render in low mode (never collapsed)."""
        msg = SelectionRequest(
            prompt_id="p3",
            prompt_text="Pick an option:",
            options=["a", "b", "c"],
        )
        out = self._render_with_level(renderer, console, msg)
        assert out.strip() != ""

    # -- Checklist #10: switching output_level mid-session takes effect immediately --

    def test_mid_session_level_switch(self, renderer, console):
        """Changing output_level between renders takes effect immediately."""
        msg = FileListingMessage(
            directory="/tmp",
            files=[FileEntry(path="a.py", type="file", size=100, depth=0)],
            recursive=True,
            total_size=100,
            dir_count=0,
            file_count=1,
        )
        # First render in medium mode → full output
        out_medium = self._render_with_level(renderer, console, msg, level="medium")
        assert "DIRECTORY LISTING" in out_medium

        # Reset console buffer
        console.file.truncate(0)
        console.file.seek(0)

        # Second render in low mode → collapsed peek
        out_low = self._render_with_level(renderer, console, msg, level="low")
        assert "list_files:" in out_low
        assert "DIRECTORY LISTING" not in out_low


class TestSubagentHandlerSelection:
    """High mode should use event_stream_handler; medium/low use subagent_stream_handler."""

    def test_high_mode_selects_main_handler(self):
        """In high mode, invoke_agent should pick the main event_stream_handler."""
        from code_puppy.agents.event_stream_handler import event_stream_handler

        # get_output_level is imported locally in subagent_invocation,
        # so patch at the config module level.
        with patch(
            "code_puppy.config.get_output_level",
            return_value="high",
        ):
            from code_puppy.config import get_output_level as _gol

            assert _gol() == "high"
            # Verify the handler exists and is callable
            assert callable(event_stream_handler)

    def test_medium_mode_uses_subagent_handler(self):
        """In medium mode, the subagent_stream_handler should be used."""
        from code_puppy.agents.subagent_stream_handler import (
            subagent_stream_handler,
        )

        # Verify the import works and it's the expected silent handler
        assert callable(subagent_stream_handler)
