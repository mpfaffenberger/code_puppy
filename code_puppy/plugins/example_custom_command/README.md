# Example Custom Command Plugin

> **Note**: This example demonstrates **custom commands** via the callback system.
> For **built-in commands**, see the built-in command files in `code_puppy/command_line/`.

## Overview

This plugin demonstrates how to create custom commands using Code Puppy's callback system.

**Important**: Custom commands use `register_callback()`, NOT `@register_command`.

## Command Types in Code Puppy

### 1. Built-in Commands (Core Functionality)
- Use `@register_command` decorator
- Located in `code_puppy/command_line/core_commands.py`, `session_commands.py`, `config_commands.py`
- Examples: `/help`, `/cd`, `/set`, `/agent`
- Check those files for implementation examples

### 2. Custom Commands (Plugins) ← **This Example**
- Use `register_callback()` function
- Located in plugin directories like this one
- Examples: `/woof`, `/echo` (from this plugin)
- Designed for plugin-specific functionality

## How This Plugin Works

### File Structure

```
code_puppy/plugins/example_custom_command/
├── register_callbacks.py    # Plugin implementation
└── README.md                # This file
```

### Implementation

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info

# Optional dependency on the sibling ``customizable_commands`` plugin.
# Returning a ``MarkdownCommandResult`` tells the dispatcher to forward
# the wrapped content to the agent as a user prompt.
try:
    from code_puppy.plugins.customizable_commands.register_callbacks import (
        MarkdownCommandResult,
    )
except ImportError:
    MarkdownCommandResult = None

# 1. Define help entries for your commands
def _custom_help():
    return [
        ("woof", "Ask the agent for a dog fact (or any prompt you tack on)"),
        ("echo", "Echo back your text (display only)"),
    ]

# 2. Define command handler
def _handle_custom_command(command: str, name: str):
    """Handle custom commands."""
    if name == "woof":
        parts = command.split(maxsplit=1)
        prompt = parts[1] if len(parts) == 2 else "Tell me a dog fact"
        emit_info(f"🐶 Woof! sending prompt: {prompt}")
        # Forward to the agent when possible; otherwise degrade gracefully
        # to display-only so the user still sees the echoed prompt.
        if MarkdownCommandResult is not None:
            return MarkdownCommandResult(prompt)
        return prompt

    if name == "echo":
        # Display-only: dispatcher echoes the returned string and stops.
        parts = command.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1]
        return ""

    return None  # Not our command

# 3. Register callbacks
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
```

## Commands Provided

### `/woof [text]`

**Description**: Playful command that sends a prompt to the model.

**Behavior**:
- Without text: Sends "Tell me a dog fact" to the model
- With text: Sends your text as the prompt

**Examples**:
```bash
/woof
# → Sends prompt: "Tell me a dog fact"

/woof What's the best breed?
# → Sends prompt: "What's the best breed?"
```

### `/echo <text>`

**Description**: Display-only command that shows your text.

**Behavior**:
- Shows the text you provide via `emit_info`
- Does **not** send anything to the model — the dispatcher treats a bare
  `str` return as display-only and short-circuits the REPL

**Examples**:
```bash
/echo Hello world
# → Displays: "example plugin echo -> Hello world"
# → No model round-trip
```

## Creating Your Own Plugin

Plugins can live at any of the three discovery tiers:

| Tier | Location | Scope |
|------|----------|-------|
| **Builtin** | `code_puppy/plugins/<name>/` | Shipped with Code Puppy |
| **User** | `~/.code_puppy/plugins/<name>/` | Personal, all projects |
| **Project** | `<CWD>/.code_puppy/plugins/<name>/` | Repo-specific, team-shared |

All tiers use the exact same `register_callbacks.py` pattern.

### Step 1: Create Plugin Directory

**Builtin plugin** (shipped with Code Puppy):

```bash
mkdir -p code_puppy/plugins/my_plugin
touch code_puppy/plugins/my_plugin/__init__.py
touch code_puppy/plugins/my_plugin/register_callbacks.py
```

**User plugin** (personal, applies to all projects):

```bash
mkdir -p ~/.code_puppy/plugins/my_plugin
touch ~/.code_puppy/plugins/my_plugin/register_callbacks.py
```

**Project plugin** (shared with your team via git):

```bash
mkdir -p .code_puppy/plugins/my_plugin
touch .code_puppy/plugins/my_plugin/register_callbacks.py
```

> **Note:** Code Puppy never auto-creates `.code_puppy/plugins/` — your team
> opts in by creating the directory. Project plugins load last (after builtin
> and user), giving them highest precedence for override-style hooks.

### Step 2: Implement Callbacks

```python
# code_puppy/plugins/my_plugin/register_callbacks.py

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success

def _custom_help():
    """Provide help text for /help display."""
    return [
        ("mycommand", "Description of my command"),
    ]

def _handle_custom_command(command: str, name: str):
    """Handle your custom commands."""
    if name == "mycommand":
        # Your command logic here
        emit_success("My command executed!")
        return True  # Command handled
    
    return None  # Not our command

# Register the callbacks
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
```

### Step 3: Test Your Plugin

```bash
# Restart Code Puppy to load the plugin
code-puppy

# Try your command
/mycommand
```

## Return Value Behaviors

Your `_handle_custom_command` function can return:

| Return Value | Behavior |
|-------------|----------|
| `None` | Command not recognized, try next plugin |
| `True` | Command handled successfully, no model invocation |
| `str` | Display-only message — dispatcher emits it and stops (agent NOT invoked) |
| `MarkdownCommandResult(content)` | Forwards `content` to the agent as a user prompt |

## Best Practices

### ✅ DO:

- **Use for plugin-specific features**: OAuth flows, integrations, utilities
- **Return `True` for display-only commands**: Avoid unnecessary model calls
- **Return strings to invoke the model**: Let users interact naturally
- **Provide clear help text**: Users see this in `/help`
- **Handle errors gracefully**: Use try/except and emit_error
- **Keep commands simple**: Complex logic → separate module

### ❌ DON'T:

- **Don't use `@register_command`**: That's for built-in commands only
- **Don't modify global state**: Use Code Puppy's config system
- **Don't make blocking calls**: Keep commands fast and responsive
- **Don't invoke the model directly**: return a `MarkdownCommandResult` and let the dispatcher forward it
- **Don't duplicate built-in commands**: Check existing commands first

## Command Execution Order

1. **Built-in commands** checked first (via registry)
2. **Legacy fallback** checked (for backward compatibility)
3. **Custom commands** checked (via callbacks) ← Your plugin runs here
4. If no match, show "Unknown command" warning

## Available Messaging Functions

```python
from code_puppy.messaging import (
    emit_info,     # Blue info message
    emit_success,  # Green success message
    emit_warning,  # Yellow warning message
    emit_error,    # Red error message
)

# Examples
emit_info("Processing...")
emit_success("Done!")
emit_warning("This might take a while")
emit_error("Something went wrong")
```

## Testing Your Plugin

### Manual Testing

```bash
# Start Code Puppy
code-puppy

# Test your commands
/mycommand
/help  # Verify your command appears
```

### Unit Testing

```python
# tests/test_my_plugin.py

from code_puppy.plugins.my_plugin.register_callbacks import _handle_custom_command

def test_my_command():
    result = _handle_custom_command("/mycommand", "mycommand")
    assert result is True

def test_unknown_command():
    result = _handle_custom_command("/unknown", "unknown")
    assert result is None
```

## Plugin Discovery Tiers

| Feature | Builtin | User | Project |
|---------|---------|------|---------|
| **Location** | `code_puppy/plugins/` | `~/.code_puppy/plugins/` | `<CWD>/.code_puppy/plugins/` |
| **Load order** | First | Second | Last (highest precedence) |
| **Auto-created** | N/A (in package) | No | No — team must create intentionally |
| **Name collisions** | N/A | Warning logged | Warning logged, still loads (shadow) |
| **Module namespace** | `code_puppy.plugins.<name>` | `<name>.register_callbacks` | `project_plugins.<name>.register_callbacks` |
| **Shared via git** | Yes (in repo) | No (local only) | Yes (in `.code_puppy/`) |

## Difference from Built-in Commands

| Feature | Built-in Commands | Custom Commands (Plugins) |
|---------|------------------|---------------------------|
| **Decorator/Function** | `@register_command` | `register_callback()` |
| **Location** | `core_commands.py`, etc. | Plugin directory |
| **Purpose** | Core functionality | Plugin features |
| **Auto-discovery** | Via imports | Via plugin loader |
| **Priority** | Checked first | Checked last |
| **Help display** | Automatic | Manual via callback |

## Example Plugins in This Repo

- **`example_custom_command/`** (this plugin) - Basic command examples
- **`customizable_commands/`** - Markdown file commands
- **`claude_code_oauth/`** - OAuth integration example
- **`chatgpt_oauth/`** - Another OAuth example
- **`file_permission_handler/`** - File system integration

## Further Reading

- `code_puppy/callbacks.py` - Callback system implementation
- `code_puppy/command_line/command_handler.py` - Command dispatcher
- `code_puppy/command_line/core_commands.py` - Example built-in commands
- `code_puppy/command_line/command_registry.py` - Registry system

## Questions?

If you're unsure whether to create a custom command or a built-in command:

- **Is it core Code Puppy functionality?** → Use `@register_command` (built-in)
  - Add to appropriate category file: `core_commands.py`, `session_commands.py`, or `config_commands.py`
- **Is it plugin-specific?** → Use `register_callback()` (custom)
  - Create a plugin directory and use the callback system (like this example)
- **Is it a prompt template?** → Use markdown file in `.claude/commands/`
  - The `customizable_commands` plugin will auto-load `.md` files
