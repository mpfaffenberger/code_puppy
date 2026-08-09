"""Minimal tests for code_puppy/tools/display.py.

Keeps coverage on the core display_non_streamed_result path and the
sub-agent skip short-circuit.
"""

from io import StringIO
from unittest.mock import ANY, Mock, patch

from rich.console import Console


class TestDisplayNonStreamedResult:
    """Test suite for display_non_streamed_result function."""

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_basic_display_with_provided_console(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test display_non_streamed_result with a provided console."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "blue"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        # Create a mock console
        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function
        content = "Hello, World!"
        display_non_streamed_result(
            content=content,
            console=mock_console,
            banner_text="TEST BANNER",
            banner_name="test_banner",
        )

        # Phase 3: display must NOT touch the deprecated spinner shim
        mock_pause.assert_not_called()
        mock_resume.assert_not_called()

        # Phase 3: no artificial sleep needed without a Live spinner
        mock_sleep.assert_not_called()

        # Verify banner color was retrieved
        mock_get_banner_color.assert_called_once_with("test_banner")

        # Verify console methods were called
        assert mock_console.print.called

        # Verify parser was instantiated
        mock_parser_class.assert_called_once()

        # Verify renderer was instantiated (clipboard=False prevents OSC 52 overwrite)
        from termflow.render.style import RenderFeatures

        mock_renderer_class.assert_called_once_with(
            output=mock_console.file,
            width=mock_console.width,
            style=ANY,
            features=RenderFeatures(clipboard=False),
            highlighter=ANY,
        )

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    @patch("code_puppy.tools.display.Console")
    def test_creates_console_when_none_provided(
        self,
        mock_console_class,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that display_non_streamed_result creates a Console when none is provided."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80
        mock_console_class.return_value = mock_console

        mock_get_banner_color.return_value = "green"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        # Call the function without providing a console
        content = "Test content"
        display_non_streamed_result(content=content)

        # Verify Console was created
        mock_console_class.assert_called_once()


class TestDisplaySubagentSkip:
    """Sub-agent responses are skipped unless verbose / high output mode."""

    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=False)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_skips_display_for_subagent(self, mock_sub, mock_verbose):
        """Plain sub-agent (not verbose, not high output) short-circuits."""
        from code_puppy.tools.display import display_non_streamed_result

        result = display_non_streamed_result("test content")
        assert result is None
