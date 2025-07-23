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

    def add_system_message(self, content):
        self.system_messages.append(content)

    def add_agent_message(self, content):
        self.agent_messages.append(content)

    def add_agent_reasoning_message(self, content):
        self.agent_reasoning_messages.append(content)

    def add_error_message(self, content):
        self.error_messages.append(content)


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


if __name__ == "__main__":
    test_tui_renderer_rich_table()
    test_tui_renderer_rich_syntax()
    test_tui_renderer_rich_markdown()
    test_tui_renderer_plain_string()
    test_queue_console_rich_markdown()
    test_queue_console_mixed_content()
    print("✅ All tests passed!")
