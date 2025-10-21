"""Unit tests for code_puppy.messaging.queue_console module."""
from unittest.mock import Mock, MagicMock, patch
from rich.text import Text
from rich.markdown import Markdown
from rich.table import Table

import pytest

from code_puppy.messaging.queue_console import QueueConsole, get_queue_console
from code_puppy.messaging.message_queue import MessageType


class TestQueueConsoleInit:
    """Test QueueConsole initialization."""
    
    def test_init_with_queue(self):
        """Test QueueConsole init with custom queue."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        assert console.queue is mock_queue
        assert console.fallback_console is not None
    
    def test_init_default_queue(self):
        """Test QueueConsole init with default global queue."""
        console = QueueConsole()
        
        assert console.queue is not None
        assert console.fallback_console is not None


class TestPrint:
    """Test QueueConsole.print method."""
    
    def test_print_simple_string(self):
        """Test printing a simple string."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.print("Hello, world!")
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert "Hello, world!" in str(call_args)
    
    def test_print_multiple_values(self):
        """Test printing multiple values."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.print("Value1", "Value2", "Value3")
        
        mock_queue.emit_simple.assert_called_once()
    
    def test_print_with_style(self):
        """Test printing with style parameter."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.print("Styled text", style="bold red")
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert call_args[1]["style"] == "bold red"
    
    def test_print_with_separator(self):
        """Test print with custom separator."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.print("A", "B", "C", sep="-")
        
        mock_queue.emit_simple.assert_called_once()


class TestLog:
    """Test QueueConsole.log method."""
    
    def test_log_simple_message(self):
        """Test logging a simple message."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.log("Log message")
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert call_args[1]["log"] is True
    
    def test_log_with_style(self):
        """Test logging with style."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.log("Important log", style="bold green")
        
        mock_queue.emit_simple.assert_called_once()


class TestPrintException:
    """Test QueueConsole.print_exception method."""
    
    def test_print_exception(self):
        """Test printing exception information."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        try:
            raise ValueError("Test error")
        except ValueError:
            console.print_exception()
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert call_args[0][0] == MessageType.ERROR
        assert "Exception" in str(call_args)


class TestInferMessageType:
    """Test message type inference."""
    
    def test_infer_error_from_style(self):
        """Test inferring ERROR type from red style."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Test", style="bold red")
        
        assert msg_type == MessageType.ERROR
    
    def test_infer_warning_from_style(self):
        """Test inferring WARNING type from yellow style."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Test", style="yellow")
        
        assert msg_type == MessageType.WARNING
    
    def test_infer_success_from_style(self):
        """Test inferring SUCCESS type from green style."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Test", style="bold green")
        
        assert msg_type == MessageType.SUCCESS
    
    def test_infer_from_content_error(self):
        """Test inferring ERROR from content."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Error occurred")
        
        assert msg_type == MessageType.ERROR
    
    def test_infer_from_content_warning(self):
        """Test inferring WARNING from content."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Warning: something happened")
        
        assert msg_type == MessageType.WARNING
    
    def test_infer_from_content_success(self):
        """Test inferring SUCCESS from content."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type("Success! Task completed")
        
        assert msg_type == MessageType.SUCCESS


class TestInferMessageTypeFromRichObject:
    """Test message type inference from Rich objects."""
    
    def test_infer_from_markdown(self):
        """Test inferring type from Markdown object."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        md = Markdown("# Test")
        msg_type = console._infer_message_type_from_rich_object(md)
        
        assert msg_type == MessageType.AGENT_REASONING
    
    def test_infer_from_table(self):
        """Test inferring type from Table object."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        table = Table()
        msg_type = console._infer_message_type_from_rich_object(table)
        
        assert msg_type == MessageType.TOOL_OUTPUT
    
    def test_infer_from_style_purple(self):
        """Test inferring AGENT_REASONING from purple style."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        msg_type = console._infer_message_type_from_rich_object("test", style="purple")
        
        assert msg_type == MessageType.AGENT_REASONING


class TestRule:
    """Test QueueConsole.rule method."""
    
    def test_rule_with_title(self):
        """Test printing a rule with title."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.rule("Section Title")
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert "Section Title" in str(call_args)
        assert call_args[1]["rule"] is True
    
    def test_rule_without_title(self):
        """Test printing a rule without title."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.rule()
        
        mock_queue.emit_simple.assert_called_once()


class TestStatus:
    """Test QueueConsole.status method."""
    
    def test_status_message(self):
        """Test displaying status message."""
        mock_queue = Mock()
        console = QueueConsole(queue=mock_queue)
        
        console.status("Processing...")
        
        mock_queue.emit_simple.assert_called_once()
        call_args = mock_queue.emit_simple.call_args
        assert call_args[1]["status"] is True


class TestFileProperty:
    """Test file property."""
    
    def test_file_getter(self):
        """Test getting file property."""
        console = QueueConsole()
        
        # Should return fallback console's file
        assert console.file is not None
    
    def test_file_setter(self):
        """Test setting file property."""
        console = QueueConsole()
        import sys
        
        console.file = sys.stdout
        
        assert console.fallback_console.file == sys.stdout


class TestGetQueueConsole:
    """Test get_queue_console helper function."""
    
    def test_get_queue_console_default(self):
        """Test getting queue console with default queue."""
        console = get_queue_console()
        
        assert isinstance(console, QueueConsole)
        assert console.queue is not None
    
    def test_get_queue_console_custom_queue(self):
        """Test getting queue console with custom queue."""
        mock_queue = Mock()
        console = get_queue_console(queue=mock_queue)
        
        assert isinstance(console, QueueConsole)
        assert console.queue is mock_queue
