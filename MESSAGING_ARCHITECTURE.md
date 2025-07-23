# Messaging Architecture in Code Puppy

This document describes the messaging system architecture used in the Code Puppy application to handle messages across different UI modes (TUI and interactive CLI).

## Overview

The messaging system decouples message generation from message rendering, allowing consistent handling of messages regardless of the UI mode. This architecture ensures that:

1. Messages can be sent using a uniform API
2. Messages are properly styled and formatted based on their type
3. The appropriate renderer for the current UI mode displays the messages
4. Rich formatting is preserved across different UI modes

## Core Components

### 1. Message Queue (`message_queue.py`)

The message queue is the central component that routes messages between senders and renderers:

- `MessageQueue`: Thread-safe queue for UI messages
- `MessageType`: Enum defining different message categories (INFO, ERROR, WARNING, etc.)
- `UIMessage`: Data structure containing message content, type, and metadata
- `emit_*` functions: Convenience wrappers for sending different types of messages

```python
# Example of the queue's role
message = UIMessage(type=MessageType.ERROR, content="An error occurred")
queue.emit(message)  # Added to queue for rendering
```

### 2. Queue Console (`queue_console.py`)

A drop-in replacement for Rich's Console that routes output to the message queue:

- `QueueConsole`: Rich Console-compatible interface that sends to the queue
- Maintains API compatibility with Rich's Console for easy migration
- Infers message types from content and styling

```python
console = get_queue_console()
console.print("Hello world")  # Automatically routed to queue
```

### 3. Renderers (`renderers.py`)

Renderers consume messages from the queue and display them appropriately:

- `MessageRenderer`: Abstract base class for all renderers
- `InteractiveRenderer`: Async renderer for interactive CLI mode
- `SynchronousInteractiveRenderer`: Thread-based renderer for interactive CLI
- `TUIRenderer`: Renderer for TUI mode that adds messages to the chat view

Each renderer is responsible for displaying messages in a way appropriate for its UI mode.

## Message Types and Styling

The system defines semantic message types that map to appropriate styling:

| Message Type | Function | Default Style | Use Case |
|--------------|----------|--------------|----------|
| INFO | `emit_info()` | Blue | General information |
| SUCCESS | `emit_success()` | Green | Success messages |
| WARNING | `emit_warning()` | Yellow | Warnings and cautions |
| ERROR | `emit_error()` | Bold red | Error messages |
| SYSTEM | `emit_system_message()` | Dim | System status messages |
| TOOL_OUTPUT | `emit_tool_output()` | - | Output from tools |
| AGENT_REASONING | `emit_agent_reasoning()` | Purple | Agent's reasoning process |

## Sending Messages

There are two main ways to send messages through the system:

### 1. Using `emit_*` functions (recommended)

These high-level, semantic functions make it clear what type of message is being sent:

```python
from code_puppy.messaging import emit_info, emit_error, emit_warning, emit_success, emit_system_message

emit_info("This is an informational message")
emit_error("Something went wrong")
emit_warning("Be careful with this operation")
emit_success("Operation completed successfully")
emit_system_message("System is starting up")
```

### 2. Using `QueueConsole`

A more direct approach that maintains compatibility with Rich's Console API:

```python
from code_puppy.messaging import get_queue_console

console = get_queue_console()
console.print("Hello world")  # Automatically infers message type
console.print("Error message", style="red")  # Style hints at message type
```

## Rich Formatting in Messages

The `emit_*` functions accept Rich formatting tags in the message content. While each function corresponds to a specific message type (info, error, warning, etc.) which determines the default styling applied to the message, you can still use Rich markup within the message content to override or enhance the formatting for parts of the text.

For example:
```python
emit_info("[bold blue]Enter your coding task:[/bold blue]")
emit_error("[bold red]Error:[/bold red] [yellow]This part is yellow[/yellow]")
```

This flexibility allows you to have consistent message routing through the queue system while still maintaining rich, custom formatting when needed. The Rich markup is preserved and rendered by the appropriate renderer for the current mode (TUI or interactive).

## Message Flow

Here's how messages flow through the system:

1. A component calls `emit_*` or `console.print()`
2. The message is wrapped in a `UIMessage` with appropriate type
3. The message is added to the global message queue
4. Active renderers consume messages from the queue
5. Each renderer formats and displays messages according to its UI mode

## Best Practices

When working with the messaging system:

1. **Prefer `emit_*` functions** for clarity and consistent styling
2. **Use appropriate message types** for semantic meaning
3. **Include Rich formatting** when needed for emphasis or clarity
4. **Don't check for UI mode** - the messaging system handles this automatically

## Renderers and UI Modes

The application has two primary UI modes, each with its own renderer:

### TUI Mode

- Uses `TUIRenderer`
- Messages are rendered in the TUI chat view
- Formatting is preserved where supported by Textual

### Interactive CLI Mode

- Uses `SynchronousInteractiveRenderer`
- Messages are rendered directly to the terminal
- Full Rich formatting support

## Future Improvements

Potential areas for improvement in the messaging system:

1. Standardize on a single renderer approach for interactive mode (async or sync)
2. Simplify the renderer hierarchy
3. Add better filtering support for message types
4. Improve testing coverage for message routing
