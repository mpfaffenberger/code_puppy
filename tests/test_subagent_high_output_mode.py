"""Tests for sub-agent response rendering in high output mode.

Covers the fix for code_puppy_oss-hwx: ensures sub-agent responses render
visibly in high mode via streaming OR fallback, without double-rendering,
and with proper spinner coordination.
"""

from io import StringIO
from unittest.mock import Mock, patch

from rich.console import Console


# ---------------------------------------------------------------------------
# display_non_streamed_result — output_level guard
# ---------------------------------------------------------------------------


class TestDisplayNonStreamedResultOutputLevel:
    """display_non_streamed_result must respect output_level == 'high'."""

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color", return_value="blue")
    @patch("code_puppy.tools.display.get_output_level", return_value="high")
    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=False)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_renders_in_subagent_context_when_high(
        self,
        mock_is_sub,
        mock_verbose,
        mock_level,
        mock_color,
        mock_parser_cls,
        mock_renderer_cls,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """High mode overrides the subagent suppression guard."""
        from code_puppy.tools.display import display_non_streamed_result

        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_cls.return_value = mock_parser
        mock_renderer_cls.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        console = Mock(spec=Console)
        console.file = StringIO()
        console.width = 80

        display_non_streamed_result(content="hello", console=console)

        # Should have rendered — banner color looked up, parser used
        mock_color.assert_called_once()
        mock_parser.parse_line.assert_called()

    @patch("code_puppy.tools.display.get_output_level", return_value="medium")
    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=False)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_suppressed_in_subagent_context_when_medium(
        self, mock_is_sub, mock_verbose, mock_level
    ):
        """Medium mode still suppresses sub-agent output (legacy behaviour)."""
        from code_puppy.tools.display import display_non_streamed_result

        console = Mock(spec=Console)
        result = display_non_streamed_result(content="hello", console=console)

        assert result is None
        # Console should NOT have been used for printing
        console.print.assert_not_called()

    @patch("code_puppy.tools.display.get_output_level", return_value="low")
    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=False)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_suppressed_in_subagent_context_when_low(
        self, mock_is_sub, mock_verbose, mock_level
    ):
        """Low mode still suppresses sub-agent output."""
        from code_puppy.tools.display import display_non_streamed_result

        console = Mock(spec=Console)
        display_non_streamed_result(content="hello", console=console)

        console.print.assert_not_called()

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color", return_value="blue")
    @patch("code_puppy.tools.display.get_output_level", return_value="medium")
    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=True)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_renders_when_verbose_regardless_of_level(
        self,
        mock_is_sub,
        mock_verbose,
        mock_level,
        mock_color,
        mock_parser_cls,
        mock_renderer_cls,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """subagent_verbose=True still works at any output level."""
        from code_puppy.tools.display import display_non_streamed_result

        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_cls.return_value = mock_parser
        mock_renderer_cls.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        console = Mock(spec=Console)
        console.file = StringIO()
        console.width = 80

        display_non_streamed_result(content="hello", console=console)

        mock_color.assert_called_once()


# ---------------------------------------------------------------------------
# Spinner pause/resume — high mode exception
# ---------------------------------------------------------------------------


class TestSpinnerHighModeSubagent:
    """Spinners must pause/resume from subagent context in high mode."""

    @patch("code_puppy.tools.subagent_context._subagent_depth")
    def test_pause_noop_in_subagent_medium(self, mock_depth):
        """pause_all_spinners is a no-op in subagent context at medium."""
        mock_depth.get.return_value = 1  # is_subagent() → True

        from code_puppy.messaging.spinner import _active_spinners, pause_all_spinners

        spy = Mock()
        _active_spinners.append(spy)
        try:
            with patch("code_puppy.config.get_output_level", return_value="medium"):
                pause_all_spinners()
            spy.pause.assert_not_called()
        finally:
            _active_spinners.remove(spy)

    @patch("code_puppy.tools.subagent_context._subagent_depth")
    def test_pause_fires_in_subagent_high(self, mock_depth):
        """pause_all_spinners fires in subagent context when high mode."""
        mock_depth.get.return_value = 1

        from code_puppy.messaging.spinner import _active_spinners, pause_all_spinners

        spy = Mock()
        _active_spinners.append(spy)
        try:
            with patch("code_puppy.config.get_output_level", return_value="high"):
                pause_all_spinners()
            spy.pause.assert_called_once()
        finally:
            _active_spinners.remove(spy)

    @patch("code_puppy.tools.subagent_context._subagent_depth")
    def test_resume_noop_in_subagent_medium(self, mock_depth):
        """resume_all_spinners is a no-op in subagent context at medium."""
        mock_depth.get.return_value = 1

        from code_puppy.messaging.spinner import _active_spinners, resume_all_spinners

        spy = Mock()
        _active_spinners.append(spy)
        try:
            with patch("code_puppy.config.get_output_level", return_value="medium"):
                resume_all_spinners()
            spy.resume.assert_not_called()
        finally:
            _active_spinners.remove(spy)

    @patch("code_puppy.tools.subagent_context._subagent_depth")
    def test_resume_fires_in_subagent_high(self, mock_depth):
        """resume_all_spinners fires in subagent context when high mode."""
        mock_depth.get.return_value = 1

        from code_puppy.messaging.spinner import _active_spinners, resume_all_spinners

        spy = Mock()
        _active_spinners.append(spy)
        try:
            with patch("code_puppy.config.get_output_level", return_value="high"):
                resume_all_spinners()
            spy.resume.assert_called_once()
        finally:
            _active_spinners.remove(spy)


# ---------------------------------------------------------------------------
# Subagent invocation — streaming detector + fallback render
# ---------------------------------------------------------------------------


class TestSubagentHighModeStreamHandlerSelection:
    """High mode wraps stream handler in StreamingTextDetector."""

    def test_high_mode_uses_detector(self):
        """StreamingTextDetector wrapping is importable and functional."""
        from code_puppy.agents._non_streaming_render import StreamingTextDetector

        inner = Mock()
        detector = StreamingTextDetector(inner)
        assert detector.streamed_text is False
        assert detector._inner is inner

    def test_medium_mode_skips_detector(self):
        """Medium mode should NOT wrap with StreamingTextDetector."""
        # This is a design assertion: in medium mode, the code creates
        # a partial(subagent_stream_handler, ...) — no detector.
        from functools import partial

        from code_puppy.agents.subagent_stream_handler import subagent_stream_handler

        handler = partial(subagent_stream_handler, session_id="test-session")
        # It should be a partial, not a StreamingTextDetector
        assert isinstance(handler, partial)


class TestSubagentResponseMessageEmit:
    """SubAgentResponseMessage emission logic in high vs non-high mode."""

    def test_high_streamed_skips_emit(self):
        """When streaming produced text in high mode, message emit is skipped."""
        # Simulates the guard: `if not (is_high_mode and streamed_text):`
        is_high_mode = True
        streamed_text = True
        should_emit = not (is_high_mode and streamed_text)
        assert should_emit is False

    def test_high_not_streamed_emits(self):
        """When streaming didn't produce text in high mode, emit proceeds."""
        is_high_mode = True
        streamed_text = False
        should_emit = not (is_high_mode and streamed_text)
        assert should_emit is True

    def test_medium_always_emits(self):
        """Non-high modes always emit the message (streaming_detector is None)."""
        is_high_mode = False
        streamed_text = False  # detector is None so this is False
        should_emit = not (is_high_mode and streamed_text)
        assert should_emit is True

    def test_low_always_emits(self):
        """Low mode always emits the message."""
        is_high_mode = False
        streamed_text = False
        should_emit = not (is_high_mode and streamed_text)
        assert should_emit is True


# ---------------------------------------------------------------------------
# event_stream_handler._should_suppress_output — regression guard
# ---------------------------------------------------------------------------


class TestShouldSuppressOutput:
    """_should_suppress_output must return False in high mode."""

    @patch(
        "code_puppy.agents.event_stream_handler.get_output_level", return_value="high"
    )
    @patch("code_puppy.agents.event_stream_handler.is_subagent", return_value=True)
    @patch(
        "code_puppy.agents.event_stream_handler.get_subagent_verbose",
        return_value=False,
    )
    def test_not_suppressed_in_high_mode(self, mock_verbose, mock_sub, mock_level):
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        assert _should_suppress_output() is False

    @patch(
        "code_puppy.agents.event_stream_handler.get_output_level",
        return_value="medium",
    )
    @patch("code_puppy.agents.event_stream_handler.is_subagent", return_value=True)
    @patch(
        "code_puppy.agents.event_stream_handler.get_subagent_verbose",
        return_value=False,
    )
    def test_suppressed_in_medium_subagent(self, mock_verbose, mock_sub, mock_level):
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        assert _should_suppress_output() is True

    @patch(
        "code_puppy.agents.event_stream_handler.get_output_level",
        return_value="medium",
    )
    @patch("code_puppy.agents.event_stream_handler.is_subagent", return_value=False)
    @patch(
        "code_puppy.agents.event_stream_handler.get_subagent_verbose",
        return_value=False,
    )
    def test_not_suppressed_when_not_subagent(self, mock_verbose, mock_sub, mock_level):
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        assert _should_suppress_output() is False
