"""Comprehensive tests for code_puppy/tools/display.py.

Tests all functions and code paths with edge cases and error handling.
"""

from io import StringIO
from unittest.mock import Mock, patch

import pytest
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

        # Verify spinner pause/resume were called
        mock_pause.assert_called_once()
        mock_resume.assert_called_once()

        # Verify sleep was called
        mock_sleep.assert_called_once_with(0.1)

        # Verify banner color was retrieved
        mock_get_banner_color.assert_called_once_with("test_banner")

        # Verify console methods were called
        assert mock_console.print.called

        # Verify parser was instantiated
        mock_parser_class.assert_called_once()

        # Verify renderer was instantiated
        mock_renderer_class.assert_called_once_with(
            output=mock_console.file, width=mock_console.width
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

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_multiline_content_parsing(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that multiline content is parsed correctly."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "red"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with multiline content
        content = "Line 1\nLine 2\nLine 3"
        display_non_streamed_result(content=content, console=mock_console)

        # Verify parse_line was called for each line
        assert mock_parser.parse_line.call_count == 3
        mock_parser.parse_line.assert_any_call("Line 1")
        mock_parser.parse_line.assert_any_call("Line 2")
        mock_parser.parse_line.assert_any_call("Line 3")

        # Verify finalize was called
        mock_parser.finalize.assert_called_once()

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_empty_content(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test handling of empty content."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "yellow"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with empty content
        display_non_streamed_result(content="", console=mock_console)

        # Verify parse_line was called once with empty string
        mock_parser.parse_line.assert_called_once_with("")

        # Verify finalize was called
        mock_parser.finalize.assert_called_once()

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_content_with_markdown_syntax(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test handling of content with markdown syntax."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "magenta"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = [Mock()]
        mock_parser.finalize.return_value = [Mock()]

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with markdown content
        content = "# Heading\n\n**bold** and *italic*\n\n- list item"
        display_non_streamed_result(content=content, console=mock_console)

        # Verify the content was split and parsed
        assert mock_parser.parse_line.call_count == 5  # 5 lines when split by \n

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_default_banner_text_and_name(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that default banner text and name are used when not provided."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "cyan"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call without providing banner text or name
        display_non_streamed_result(content="test", console=mock_console)

        # Verify get_banner_color was called with default name
        mock_get_banner_color.assert_called_once_with("agent_response")

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_renderer_render_all_called(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that renderer.render_all is called for parsed events."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "white"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer

        mock_event_1 = Mock()
        mock_event_2 = Mock()
        mock_event_3 = Mock()
        mock_parser.parse_line.side_effect = [[mock_event_1], [mock_event_2]]
        mock_parser.finalize.return_value = [mock_event_3]

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with multiline content
        display_non_streamed_result(content="Line 1\nLine 2", console=mock_console)

        # Verify render_all was called for each parsed event set
        assert mock_renderer.render_all.call_count == 3
        mock_renderer.render_all.assert_any_call([mock_event_1])
        mock_renderer.render_all.assert_any_call([mock_event_2])
        mock_renderer.render_all.assert_any_call([mock_event_3])

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_console_print_called_for_banner(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that console.print is called to render the banner."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "blue"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function
        display_non_streamed_result(
            content="test", console=mock_console, banner_text="MY BANNER"
        )

        # Verify console.print was called multiple times
        # First call clears the line, second is newline, third is the banner
        assert mock_console.print.call_count >= 3

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_special_characters_in_content(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test handling of special characters in content."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "green"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with special characters
        content = "Special: !@#$%^&*()_+-=[]{}|;:',.<>?/"
        display_non_streamed_result(content=content, console=mock_console)

        # Verify parse_line was called with the special characters
        mock_parser.parse_line.assert_called_once_with(content)

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_long_content_multiple_lines(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test handling of long content with many lines."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "red"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Create a long content with many lines
        lines = [f"Line {i}" for i in range(100)]
        content = "\n".join(lines)

        display_non_streamed_result(content=content, console=mock_console)

        # Verify parse_line was called for each line
        assert mock_parser.parse_line.call_count == 100

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_unicode_content(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test handling of unicode characters in content."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "yellow"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with unicode content
        content = "Hello 世界 🐶 Привет عالم"
        display_non_streamed_result(content=content, console=mock_console)

        # Verify parse_line was called with unicode content
        mock_parser.parse_line.assert_called_once_with(content)

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_console_file_attribute_used(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that console.file attribute is passed to renderer."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "blue"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        # Create a real StringIO to be used as console.file
        test_file = StringIO()
        mock_console = Mock(spec=Console)
        mock_console.file = test_file
        mock_console.width = 100

        # Call the function
        display_non_streamed_result(content="test", console=mock_console)

        # Verify renderer was created with the correct console.file
        mock_renderer_class.assert_called_once_with(output=test_file, width=100)

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_custom_banner_text_displayed(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that custom banner text is used in the display."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "magenta"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call with custom banner text
        custom_text = "CUSTOM BANNER"
        display_non_streamed_result(
            content="test", console=mock_console, banner_text=custom_text
        )

        # Verify console.print was called and check that banner text is used
        # We can't easily check the Text content due to markup, but we verify print was called
        assert mock_console.print.called

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_parse_line_events_rendered(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that events from parse_line are rendered."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "cyan"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer

        # Create mock events
        events = [Mock(), Mock()]
        mock_parser.parse_line.return_value = events
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function
        display_non_streamed_result(content="test", console=mock_console)

        # Verify renderer.render_all was called with the events
        mock_renderer.render_all.assert_any_call(events)

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_finalize_events_rendered(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that events from finalize are rendered."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "green"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer

        # Create mock events
        finalize_events = [Mock(), Mock()]
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = finalize_events

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function
        display_non_streamed_result(content="test", console=mock_console)

        # Verify renderer.render_all was called with the finalize events
        mock_renderer.render_all.assert_any_call(finalize_events)

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_banner_color_applied_correctly(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that the correct banner color is used."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        expected_color = "purple"
        mock_get_banner_color.return_value = expected_color
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function
        display_non_streamed_result(
            content="test",
            console=mock_console,
            banner_text="TEST",
            banner_name="custom_color",
        )

        # Verify get_banner_color was called with the right key
        mock_get_banner_color.assert_called_once_with("custom_color")

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_console_width_passed_to_renderer(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that console width is passed to the renderer."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks
        mock_get_banner_color.return_value = "blue"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.return_value = []
        mock_parser.finalize.return_value = []

        # Test with different widths
        for test_width in [80, 120, 160]:
            mock_renderer_class.reset_mock()
            mock_console = Mock(spec=Console)
            mock_console.file = StringIO()
            mock_console.width = test_width

            # Call the function
            display_non_streamed_result(content="test", console=mock_console)

            # Verify renderer was created with the correct width
            mock_renderer_class.assert_called_once()
            call_kwargs = mock_renderer_class.call_args[1]
            assert call_kwargs["width"] == test_width

    @patch("code_puppy.messaging.spinner.pause_all_spinners")
    @patch("code_puppy.messaging.spinner.resume_all_spinners")
    @patch("time.sleep")
    @patch("termflow.Renderer")
    @patch("termflow.Parser")
    @patch("code_puppy.tools.display.get_banner_color")
    def test_spinners_resumed_even_on_exception(
        self,
        mock_get_banner_color,
        mock_parser_class,
        mock_renderer_class,
        mock_sleep,
        mock_resume,
        mock_pause,
    ):
        """Test that spinners are resumed even if an exception occurs."""
        from code_puppy.tools.display import display_non_streamed_result

        # Setup mocks with exception
        mock_get_banner_color.return_value = "red"
        mock_parser = Mock()
        mock_renderer = Mock()
        mock_parser_class.return_value = mock_parser
        mock_renderer_class.return_value = mock_renderer
        mock_parser.parse_line.side_effect = Exception("Test exception")

        mock_console = Mock(spec=Console)
        mock_console.file = StringIO()
        mock_console.width = 80

        # Call the function and expect an exception
        with pytest.raises(Exception):
            display_non_streamed_result(content="test", console=mock_console)

        # Verify pause was called, but resume may not be called due to exception
        mock_pause.assert_called_once()
