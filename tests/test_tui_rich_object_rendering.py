#!/usr/bin/env python3
"""
Test that TUI renderer properly converts Rich objects to text instead of showing object references.
"""

import asyncio

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table

from code_puppy.messaging import MessageType, UIMessage
from code_puppy.messaging.message_queue import MessageQueue
from code_puppy.messaging.renderers import TUIRenderer


class MockTUIApp:
    """Mock TUI app to capture messages."""

    def __init__(self):
        self.system_messages = []
        self.agent_messages = []
        self.agent_reasoning_messages = []
        self.error_messages = []

    def add_system_message(self, content, message_group=None, group_id=None):
        self.system_messages.append(content)

    def add_agent_message(self, content, message_group=None):
        self.agent_messages.append(content)

    def add_agent_reasoning_message(self, content, message_group=None):
        self.agent_reasoning_messages.append(content)

    def add_error_message(self, content, message_group=None):
        self.error_messages.append(content)

    def add_planned_next_steps_message(self, content, message_group=None):
        self.agent_reasoning_messages.append(content)  # Can reuse for simplicity


def test_tui_renderer_rich_table():
    """Test that Rich Table objects are properly rendered to text."""
    queue = MessageQueue()
    mock_app = MockTUIApp()
    renderer = TUIRenderer(queue, mock_app)

    # Create a Rich Table
    table = Table(title="Test Table")
    table.add_column("File", style="cyan")
    table.add_column("Size", style="green")
    table.add_row("test.py", "1.2 KB")
    table.add_row("main.py", "5.4 KB")

    message = UIMessage(MessageType.TOOL_OUTPUT, table)
    asyncio.run(renderer.render_message(message))

    # Check that the message was rendered properly
    assert len(mock_app.agent_messages) == 1
    rendered_content = mock_app.agent_messages[0]

    # Should not contain object reference
    assert "object at 0x" not in rendered_content
    assert "rich.table.Table" not in rendered_content

    # Should contain table content
    assert "Test Table" in rendered_content
    assert "File" in rendered_content
    assert "Size" in rendered_content
    assert "test.py" in rendered_content
    assert "main.py" in rendered_content

    # Should contain table border characters
    assert "┏" in rendered_content or "┌" in rendered_content


def test_tui_renderer_rich_syntax():
    """Test that Rich Syntax objects are properly rendered to text."""
    queue = MessageQueue()
    mock_app = MockTUIApp()
    renderer = TUIRenderer(queue, mock_app)

    # Create a Rich Syntax object
    code = '''def hello_world():
    print("Hello, World!")
    return "success"'''
    syntax = Syntax(code, "python", theme="monokai", line_numbers=True)

    message = UIMessage(MessageType.AGENT_REASONING, syntax)
    asyncio.run(renderer.render_message(message))

    # Check that the message was rendered properly
    assert len(mock_app.agent_reasoning_messages) == 1
    rendered_content = mock_app.agent_reasoning_messages[0]

    # Should not contain object reference
    assert "object at 0x" not in rendered_content
    assert "rich.syntax.Syntax" not in rendered_content

    # Should contain code content
    assert "def hello_world()" in rendered_content
    assert 'print("Hello, World!")' in rendered_content
    assert 'return "success"' in rendered_content


def test_tui_renderer_rich_markdown():
    """Test that Rich Markdown objects are properly rendered to text."""
    queue = MessageQueue()
    mock_app = MockTUIApp()
    renderer = TUIRenderer(queue, mock_app)

    # Create a Rich Markdown object
    markdown_text = """
# Agent Reasoning

I need to:

1. **Analyze** the code structure
2. *Identify* potential issues
3. `Implement` the solution

```python
print("This is a code block")
```
"""
    markdown = Markdown(markdown_text)

    message = UIMessage(MessageType.SYSTEM, markdown)
    asyncio.run(renderer.render_message(message))

    # Check that the message was rendered properly
    assert len(mock_app.system_messages) == 1
    rendered_content = mock_app.system_messages[0]

    # Should not contain object reference
    assert "object at 0x" not in rendered_content
    assert "rich.markdown.Markdown" not in rendered_content

    # Should contain markdown content
    assert "Agent Reasoning" in rendered_content
    assert "Analyze" in rendered_content
    assert "Identify" in rendered_content
    assert "Implement" in rendered_content
    assert 'print("This is a code block")' in rendered_content


def test_tui_renderer_plain_string():
    """Test that plain strings are still handled correctly."""
    queue = MessageQueue()
    mock_app = MockTUIApp()
    renderer = TUIRenderer(queue, mock_app)

    message = UIMessage(MessageType.INFO, "This is a plain string message")
    asyncio.run(renderer.render_message(message))

    # Check that the message was rendered properly
    assert len(mock_app.system_messages) == 1
    assert mock_app.system_messages[0] == "This is a plain string message"


def test_queue_console_rich_markdown():
    """Test that QueueConsole properly handles Rich Markdown objects."""
    from code_puppy.messaging.message_queue import MessageQueue
    from code_puppy.messaging.queue_console import QueueConsole

    queue = MessageQueue()
    # Mark renderer as active so messages go to main queue instead of startup buffer
    queue.mark_renderer_active()
    console = QueueConsole(queue)

    # Create a Rich Markdown object (simulating what happens in agent reasoning)
    reasoning_text = """
# Agent Analysis

I need to:

1. **Analyze** the problem
2. *Implement* a solution
3. `Test` the fix

```python
print("This is code")
```
"""
    markdown = Markdown(reasoning_text)

    # Print the markdown object (this is what command_runner.py does)
    console.print(markdown)

    # Get the message from the queue
    message = queue.get_nowait()

    # Verify the message was processed correctly
    assert message is not None
    assert (
        message.type.value == "agent_reasoning"
    )  # Should be inferred as agent reasoning

    # The content should be the Rich Markdown object itself, not a string representation
    assert isinstance(message.content, Markdown)

    # Verify it can be rendered properly by TUIRenderer
    mock_app = MockTUIApp()
    renderer = TUIRenderer(queue, mock_app)

    # Render the message
    asyncio.run(renderer.render_message(message))

    # Check that it was rendered as text, not object reference
    assert len(mock_app.agent_reasoning_messages) == 1
    rendered_content = mock_app.agent_reasoning_messages[0]

    # Should not contain object reference
    assert "object at 0x" not in rendered_content
    assert "rich.markdown.Markdown" not in rendered_content

    # Should contain the actual markdown content
    assert "Agent Analysis" in rendered_content
    assert "Analyze" in rendered_content
    assert "Implement" in rendered_content
    assert "Test" in rendered_content
    assert 'print("This is code")' in rendered_content


def test_queue_console_mixed_content():
    """Test that QueueConsole properly handles mixed Rich and string content."""
    from code_puppy.messaging.message_queue import MessageQueue
    from code_puppy.messaging.queue_console import QueueConsole

    queue = MessageQueue()
    # Mark renderer as active so messages go to main queue instead of startup buffer
    queue.mark_renderer_active()
    console = QueueConsole(queue)

    # Create a Rich Markdown object
    markdown = Markdown("**Bold text**")

    # Print mixed content
    console.print("Prefix: ", markdown, " :suffix")

    # Get the message from the queue
    message = queue.get_nowait()

    # Should be processed as string content (not Rich object)
    assert isinstance(message.content, str)
    assert "object at 0x" not in message.content
    assert "Prefix:" in message.content
    assert "Bold text" in message.content
    assert ":suffix" in message.content


def test_system_message_grouping():
    """Test that system messages with the same group_id get concatenated."""
    from datetime import datetime, timezone

    from code_puppy.tui.models.chat_message import ChatMessage
    from code_puppy.tui.models.enums import MessageType

    # Mock ChatView to test logic without widget mounting
    class MockChatView:
        def __init__(self):
            self.messages = []

        def add_message(self, message):
            # Simplified version of the grouping logic from chat_view.py
            if (
                message.type == MessageType.SYSTEM
                and message.group_id is not None
                and self.messages
                and self.messages[-1].type == MessageType.SYSTEM
                and self.messages[-1].group_id == message.group_id
            ):
                # Concatenate with the previous system message
                previous_message = self.messages[-1]
                previous_message.content += "\n" + message.content
                return

            # Add to messages list
            self.messages.append(message)

    # Create a MockChatView instance
    chat_view = MockChatView()

    # Add first system message with group_id
    msg1 = ChatMessage(
        id="test1",
        type=MessageType.SYSTEM,
        content="First message in group",
        timestamp=datetime.now(timezone.utc),
        group_id="test_group_123",
    )
    chat_view.add_message(msg1)

    # Add second system message with same group_id
    msg2 = ChatMessage(
        id="test2",
        type=MessageType.SYSTEM,
        content="Second message in group",
        timestamp=datetime.now(timezone.utc),
        group_id="test_group_123",
    )
    chat_view.add_message(msg2)

    # Add third system message with different group_id
    msg3 = ChatMessage(
        id="test3",
        type=MessageType.SYSTEM,
        content="Different group message",
        timestamp=datetime.now(timezone.utc),
        group_id="test_group_456",
    )
    chat_view.add_message(msg3)

    # Check that only 2 messages are stored (first and third)
    assert len(chat_view.messages) == 2

    # Check that the first message content has been concatenated
    assert (
        chat_view.messages[0].content
        == "First message in group\nSecond message in group"
    )
    assert chat_view.messages[0].group_id == "test_group_123"

    # Check that the second stored message is the different group
    assert chat_view.messages[1].content == "Different group message"
    assert chat_view.messages[1].group_id == "test_group_456"


def test_tools_generate_group_ids():
    """Test that our tools generate group_ids when emitting messages."""
    import time

    from code_puppy.tools.common import generate_group_id

    # Test group_id generation
    group_id1 = generate_group_id("list_files", "/test/path")
    time.sleep(0.001)  # Small delay to ensure different timestamp
    group_id2 = generate_group_id("list_files", "/test/path")
    group_id3 = generate_group_id("edit_file", "/test/file.py")

    # Group IDs should be unique when called at different times
    assert group_id1 != group_id2

    # But should start with tool name
    assert group_id1.startswith("list_files_")
    assert group_id2.startswith("list_files_")
    assert group_id3.startswith("edit_file_")

    # Should have consistent format
    assert "_" in group_id1
    assert len(group_id1.split("_")) >= 2

    # Same tool with same context can have same ID if called at same time
    group_id4 = generate_group_id("test_tool", "same_context")
    group_id5 = generate_group_id("test_tool", "same_context")
    # This might be the same or different depending on timing, both are valid
    assert group_id4.startswith("test_tool_")
    assert group_id5.startswith("test_tool_")


if __name__ == "__main__":
    test_tui_renderer_rich_table()
    test_tui_renderer_rich_syntax()
    test_tui_renderer_rich_markdown()
    test_tui_renderer_plain_string()
    test_queue_console_rich_markdown()
    test_queue_console_mixed_content()
    test_system_message_grouping()
    test_tools_generate_group_ids()
    print("✅ All tests passed!")
