"""
Comprehensive tests for QueueConsole functionality.

Tests cover console output, message queue integration, Rich object handling,
message type inference, and error handling.

Target coverage: 85%+
"""

from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from code_puppy.messaging.message_queue import MessageQueue, MessageType
from code_puppy.messaging.queue_console import QueueConsole, get_queue_console


class TestQueueConsoleInitialization:
    """Test QueueConsole initialization and configuration."""

    def test_init_default_queue(self):
        """Test initialization with default global queue."""
        with patch(
            "code_puppy.messaging.queue_console.get_global_queue"
        ) as mock_get_queue:
            mock_queue = Mock(spec=MessageQueue)
            mock_get_queue.return_value = mock_queue
            console = QueueConsole()
            assert console.queue == mock_queue
            assert console.fallback_console is not None

    def test_init_custom_queue(self):
        """Test initialization with custom queue."""
        custom_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=custom_queue)
        assert console.queue is custom_queue

    def test_init_custom_fallback_console(self):
        """Test initialization with custom fallback console."""
        custom_console = Mock(spec=Console)
        console = QueueConsole(fallback_console=custom_console)
        assert console.fallback_console is custom_console

    def test_init_both_custom(self):
        """Test initialization with both custom queue and console."""
        custom_queue = Mock(spec=MessageQueue)
        custom_console = Mock(spec=Console)
        console = QueueConsole(queue=custom_queue, fallback_console=custom_console)
        assert console.queue is custom_queue
        assert console.fallback_console is custom_console

    def test_get_queue_console_function(self):
        """Test the get_queue_console factory function."""
        console = get_queue_console()
        assert isinstance(console, QueueConsole)

    def test_get_queue_console_with_custom_queue(self):
        """Test get_queue_console with custom queue."""
        custom_queue = Mock(spec=MessageQueue)
        console = get_queue_console(queue=custom_queue)
        assert console.queue is custom_queue


class TestPrintBasic:
    """Test basic print functionality."""

    def test_print_simple_string(self):
        """Test printing a simple string."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Hello")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.INFO
        assert "Hello" in str(args[1])

    def test_print_multiple_values(self):
        """Test printing multiple values."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Hello", "World")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert "Hello" in content
        assert "World" in content

    def test_print_with_separator(self):
        """Test printing with custom separator."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("a", "b", "c", sep="-")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert "a" in content
        assert "b" in content
        assert "c" in content

    def test_print_with_end(self):
        """Test printing with custom end parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Test", end="!!!")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert content.endswith("!!!")

    def test_print_with_style(self):
        """Test printing with style parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Error", style="red")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR  # Inferred from 'red' style
        assert isinstance(args[1], Text)  # Should be Text object due to style

    def test_print_with_highlight(self):
        """Test printing with highlight parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Code", highlight=False)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert kwargs.get("highlight") is False

    def test_print_empty_string(self):
        """Test printing empty string."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("")
        mock_queue.emit_simple.assert_called_once()

    def test_print_numeric_values(self):
        """Test printing numeric values."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print(42, 3.14, True)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert "42" in content
        assert "3.14" in content


class TestPrintRichObjects:
    """Test printing Rich objects like Text, Table, Markdown."""

    def test_print_rich_text(self):
        """Test printing a Rich Text object."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        text = Text("Styled", style="bold")
        console.print(text)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[1] is text

    def test_print_markdown(self):
        """Test printing a Markdown object."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        markdown = Markdown("# Title")
        console.print(markdown)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        # Should infer AGENT_REASONING from Markdown type
        assert args[0] == MessageType.AGENT_REASONING

    def test_print_table(self):
        """Test printing a Rich Table object."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        table = Table(title="Data")
        table.add_column("Name")
        table.add_row("Item")
        console.print(table)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        # Should infer TOOL_OUTPUT from Table type
        assert args[0] == MessageType.TOOL_OUTPUT

    def test_print_syntax(self):
        """Test printing a Syntax (code) object."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        syntax = Syntax("print('hello')", "python")
        console.print(syntax)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        # Syntax objects have __rich_console__, so they go through as-is
        # The type inference depends on actual attributes
        assert args[0] in [MessageType.TOOL_OUTPUT, MessageType.INFO]

    def test_print_rich_object_with_style_override(self):
        """Test printing Rich object with style parameter overrides type."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        text = Text("Message")
        console.print(text, style="red")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        # Style should override and infer ERROR
        assert args[0] == MessageType.ERROR


class TestPrintException:
    """Test exception printing functionality."""

    def test_print_exception_basic(self):
        """Test printing exception with default parameters."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        try:
            raise ValueError("Test error")
        except ValueError:
            console.print_exception()

        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR
        assert "Exception" in str(args[1])
        assert "ValueError" in str(args[1])
        assert kwargs.get("exception") is True

    def test_print_exception_with_show_locals(self):
        """Test print_exception with show_locals parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        try:
            raise RuntimeError("Local test")
        except RuntimeError:
            console.print_exception(show_locals=True)

        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert kwargs.get("show_locals") is True

    def test_print_exception_parameters_ignored(self):
        """Test that additional parameters don't break print_exception."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        try:
            raise TypeError("Test")
        except TypeError:
            # These parameters are accepted but mostly ignored in simplified version
            console.print_exception(
                width=100,
                extra_lines=5,
                theme="monokai",
                word_wrap=True,
                indent_guides=False,
                max_frames=50,
            )

        mock_queue.emit_simple.assert_called_once()


class TestLogMethod:
    """Test log method functionality."""

    def test_log_simple(self):
        """Test simple logging."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("Log message")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.INFO
        assert kwargs.get("log") is True

    def test_log_multiple_values(self):
        """Test logging multiple values."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("msg1", "msg2", "msg3")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert "msg1" in content
        assert "msg2" in content
        assert "msg3" in content

    def test_log_with_separator(self):
        """Test logging with custom separator."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("a", "b", sep="|")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert "a" in content and "b" in content

    def test_log_with_style_error(self):
        """Test logging with error style infers ERROR type."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("Error occurred", style="red")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_log_with_style_warning(self):
        """Test logging with warning style infers WARNING type."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("Warning", style="yellow")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.WARNING

    def test_log_with_style_success(self):
        """Test logging with success style infers SUCCESS type."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("Done", style="green")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS

    def test_log_with_log_locals(self):
        """Test logging with log_locals parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log("Debug", log_locals=True)
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert kwargs.get("log_locals") is True

    def test_log_with_various_parameters(self):
        """Test logging with various parameters."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.log(
            "test",
            sep=",",
            end=";\n",
            justify="center",
            emoji=True,
            markup=True,
            highlight=True,
        )
        mock_queue.emit_simple.assert_called_once()


class TestMessageTypeInference:
    """Test message type inference from styles and content."""

    def test_infer_error_from_style(self):
        """Test ERROR type inference from red/error style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        # Test 'red' style
        console.print("Message", style="red")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

        # Test 'error' style
        mock_queue.reset_mock()
        console.print("Message", style="error")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_infer_warning_from_style(self):
        """Test WARNING type inference from yellow/warning style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message", style="yellow")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.WARNING

    def test_infer_success_from_style(self):
        """Test SUCCESS type inference from green/success style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message", style="green")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS

    def test_infer_info_from_style(self):
        """Test INFO type inference from blue style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message", style="blue")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.INFO

    def test_infer_agent_reasoning_from_style(self):
        """Test AGENT_REASONING from purple/magenta style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message", style="purple")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.AGENT_REASONING

    def test_infer_system_from_style(self):
        """Test SYSTEM from dim style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message", style="dim")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SYSTEM

    def test_infer_error_from_content(self):
        """Test ERROR type inference from content keywords."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("An error occurred")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_infer_warning_from_content(self):
        """Test WARNING type inference from content keywords."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Warning: something might go wrong")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.WARNING

    def test_infer_success_from_content(self):
        """Test SUCCESS type inference from content keywords."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Task completed successfully")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS

    def test_infer_tool_output_from_content(self):
        """Test TOOL_OUTPUT type inference from content keywords."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("tool output here")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.TOOL_OUTPUT

    def test_infer_default_info(self):
        """Test default INFO type when no style or keywords match."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Generic message")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.INFO


class TestRuleMethod:
    """Test the rule method for printing horizontal rules."""

    def test_rule_no_title(self):
        """Test printing a rule without title."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.rule()
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SYSTEM
        assert kwargs.get("rule") is True

    def test_rule_with_title(self):
        """Test printing a rule with title."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.rule("Section")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SYSTEM
        assert "Section" in str(args[1])
        assert kwargs.get("rule") is True

    def test_rule_with_alignment(self):
        """Test rule with alignment parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.rule("Title", align="left")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert "Title" in str(args[1])

    def test_rule_with_style(self):
        """Test rule with custom style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.rule("Styled", style="bold red")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert kwargs.get("style") == "bold red"


class TestStatusMethod:
    """Test the status method for progress indicators."""

    def test_status_simple(self):
        """Test showing a simple status message."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.status("Processing...")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.INFO
        assert "Processing" in str(args[1])
        assert kwargs.get("status") is True

    def test_status_with_spinner(self):
        """Test status with custom spinner."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.status("Loading", spinner="line")
        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert kwargs.get("spinner") == "line"


class TestInputMethod:
    """Test the input method for user interaction."""

    @patch("sys.stderr")
    def test_input_basic(self, mock_stderr):
        """Test basic user input."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        with patch("builtins.input", return_value="user response"):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                result = console.input("Enter name: ")

        assert result == "user response"
        # Should emit the prompt message
        assert mock_queue.emit_simple.call_count >= 1
        # First call should be SYSTEM type for prompt
        first_call = mock_queue.emit_simple.call_args_list[0]
        assert first_call[0][0] == MessageType.SYSTEM

    @patch("sys.stderr")
    def test_input_empty_prompt(self, mock_stderr):
        """Test input without prompt."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        with patch("builtins.input", return_value="test"):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                result = console.input()

        assert result == "test"
        # With empty prompt, should still emit response
        assert mock_queue.emit_simple.call_count >= 1

    @patch("sys.stderr")
    def test_input_keyboard_interrupt(self, mock_stderr):
        """Test handling KeyboardInterrupt during input."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                result = console.input("Prompt: ")

        assert result == ""
        # Should emit cancellation warning
        # Check that at least one call was made with WARNING type
        calls = mock_queue.emit_simple.call_args_list
        assert len(calls) >= 2  # Prompt and warning

    @patch("sys.stderr")
    def test_input_eof_error(self, mock_stderr):
        """Test handling EOFError during input."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        with patch("builtins.input", side_effect=EOFError):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                result = console.input("Prompt: ")

        assert result == ""

    @patch("sys.stderr")
    def test_input_sets_flag(self, mock_stderr):
        """Test that input sets the awaiting_user_input flag."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        with patch("builtins.input", return_value="test"):
            with patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ) as mock_set_flag:
                result = console.input("test: ")

        assert result == "test"
        # Should be called at least once to set True
        assert mock_set_flag.call_count >= 1


class TestFileProperty:
    """Test the file property for console compatibility."""

    def test_file_property_getter(self):
        """Test getting the file property."""
        mock_fallback = Mock(spec=Console)
        mock_fallback.file = StringIO()
        console = QueueConsole(fallback_console=mock_fallback)

        file_obj = console.file
        assert file_obj == mock_fallback.file

    def test_file_property_setter(self):
        """Test setting the file property."""
        mock_fallback = Mock(spec=Console)
        mock_fallback.file = None
        console = QueueConsole(fallback_console=mock_fallback)

        new_file = StringIO()
        console.file = new_file
        assert mock_fallback.file == new_file


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_print_none_values(self):
        """Test printing None values."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print(None)
        mock_queue.emit_simple.assert_called_once()

    def test_print_object_with_str(self):
        """Test printing custom object with __str__."""

        class CustomObject:
            def __str__(self):
                return "custom output"

        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print(CustomObject())
        mock_queue.emit_simple.assert_called_once()
        args, _ = mock_queue.emit_simple.call_args
        assert "custom output" in str(args[1])

    def test_print_with_unicode(self):
        """Test printing Unicode characters."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("🐕 Woof! 你好")
        mock_queue.emit_simple.assert_called_once()
        args, _ = mock_queue.emit_simple.call_args
        assert "🐕" in str(args[1]) or "Woof" in str(args[1])

    def test_print_very_long_string(self):
        """Test printing very long strings."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        long_string = "x" * 10000
        console.print(long_string)
        mock_queue.emit_simple.assert_called_once()

    def test_print_special_characters(self):
        """Test printing special characters and escape sequences."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("Line1\nLine2\tTabbed")
        mock_queue.emit_simple.assert_called_once()

    def test_print_mixed_rich_and_strings(self):
        """Test printing mixed Rich objects and strings."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        text = Text("Rich")
        console.print("String", text, 42)
        mock_queue.emit_simple.assert_called_once()

    def test_print_without_kwargs(self):
        """Test print with minimal arguments."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("test")
        mock_queue.emit_simple.assert_called_once()

    def test_style_case_insensitive(self):
        """Test that style matching is case insensitive."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("test", style="RED")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_combined_style_attributes(self):
        """Test style with multiple attributes."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)
        console.print("test", style="bold red")
        args, _ = mock_queue.emit_simple.call_args
        # Should infer from 'red' part
        assert args[0] == MessageType.ERROR


class TestMissingCoverageEdgeCases:
    """Test cases to cover remaining uncovered lines."""

    def test_print_rich_object_with_lexer_name(self):
        """Test detection of objects with lexer_name attribute (Syntax-like)."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        # Create a mock object with lexer_name attribute
        mock_syntax = Mock()
        mock_syntax.__rich_console__ = Mock()
        mock_syntax.lexer_name = "python"

        # This should be treated as having __rich_console__
        console.print(mock_syntax)
        mock_queue.emit_simple.assert_called_once()

    def test_infer_message_type_magenta_style(self):
        """Test AGENT_REASONING inference from magenta style."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("message", style="magenta")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.AGENT_REASONING

    def test_print_with_no_style_but_error_content(self):
        """Test error inference from content when no style provided."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("An exception occurred")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_print_rich_object_no_inference_attributes(self):
        """Test Rich object type that doesn't match known types."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        # Create a generic Rich-like object without the problematic attributes
        generic_rich = MagicMock()
        # Set only __rich_console__ without other attributes that might be inferred
        del generic_rich.lexer_name

        console.print(generic_rich)
        mock_queue.emit_simple.assert_called_once()
        args, _ = mock_queue.emit_simple.call_args
        # Rich objects go through as-is, type inference happens after
        assert args[0] in [MessageType.INFO, MessageType.TOOL_OUTPUT]

    def test_print_failed_keyword_in_content(self):
        """Test ERROR inference from 'failed' keyword in content."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Operation failed unexpectedly")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_print_warn_keyword_in_content(self):
        """Test WARNING inference from 'warn' keyword."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("warn: this is important")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.WARNING

    def test_print_command_keyword_in_content(self):
        """Test TOOL_OUTPUT inference from 'command' keyword."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        # 'success' keyword is checked first, so use only 'command'
        console.print("command output here")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.TOOL_OUTPUT

    def test_print_running_keyword_in_content(self):
        """Test TOOL_OUTPUT inference from 'running' keyword."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("running tests now")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.TOOL_OUTPUT

    def test_log_with_end_parameter(self):
        """Test log with custom end parameter."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.log("message", end=":::")
        mock_queue.emit_simple.assert_called_once()
        args, _ = mock_queue.emit_simple.call_args
        content = str(args[1])
        assert content.endswith(":::")

    def test_style_with_bold_red(self):
        """Test combined style attributes (bold red)."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Error", style="bold red")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_style_with_bold_yellow(self):
        """Test combined style attributes (bold yellow)."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Warning", style="bold yellow")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.WARNING

    def test_style_with_bold_green(self):
        """Test combined style attributes (bold green)."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Success", style="bold green")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS

    def test_print_completed_keyword_in_content(self):
        """Test SUCCESS inference from 'completed' keyword."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Task completed")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS

    def test_print_done_keyword_in_content(self):
        """Test SUCCESS inference from 'done' keyword."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("All done!")
        args, _ = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.SUCCESS


class TestIntegration:
    """Integration tests for QueueConsole."""

    def test_multiple_prints_sequence(self):
        """Test sequence of print calls."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("First")
        console.print("Second")
        console.print("Third")

        assert mock_queue.emit_simple.call_count == 3

    def test_mixed_method_calls(self):
        """Test calling different console methods."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        console.print("Message")
        console.log("Log")
        console.rule("Rule")
        console.status("Status")

        assert mock_queue.emit_simple.call_count == 4

    def test_print_with_all_rich_types(self):
        """Test printing all supported Rich object types."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        rich_objects = [
            Text("Text", style="bold"),
            Markdown("# Markdown"),
            Table(title="Table"),
            Syntax("code", "python"),
        ]

        for obj in rich_objects:
            mock_queue.reset_mock()
            console.print(obj)
            mock_queue.emit_simple.assert_called_once()

    def test_exception_flow(self):
        """Test exception handling flow."""
        mock_queue = Mock(spec=MessageQueue)
        console = QueueConsole(queue=mock_queue)

        try:
            raise ValueError("Test")
        except Exception:
            console.print_exception()

        mock_queue.emit_simple.assert_called_once()
        args, kwargs = mock_queue.emit_simple.call_args
        assert args[0] == MessageType.ERROR

    def test_console_state_isolation(self):
        """Test that multiple console instances don't interfere."""
        queue1 = Mock(spec=MessageQueue)
        queue2 = Mock(spec=MessageQueue)

        console1 = QueueConsole(queue=queue1)
        console2 = QueueConsole(queue=queue2)

        console1.print("Console 1")
        console2.print("Console 2")

        assert queue1.emit_simple.call_count == 1
        assert queue2.emit_simple.call_count == 1

        # Verify different queues were called
        assert queue1 is not queue2
