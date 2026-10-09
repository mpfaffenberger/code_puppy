"""
Tool Call Argument Formatters

Provides human-readable formatting for different tool types.
Used by permission system to display tool details in a user-friendly way.
"""

from typing import Any, Dict


def format_shell_command(args: Dict[str, Any]) -> str:
    """Format shell command arguments for display."""
    command = args.get("command", "")
    cwd = args.get("cwd")
    timeout = args.get("timeout", 60)
    background = args.get("background", False)

    lines = []
    lines.append(f"Command: {command}")
    if cwd:
        lines.append(f"Directory: {cwd}")
    lines.append(f"Timeout: {timeout}s")
    if background:
        lines.append("Mode: Background")

    return "\n".join(lines)


def format_file_operation(tool_name: str, args: Dict[str, Any]) -> str:
    """Format file operation arguments for display."""
    file_path = args.get("file_path", "")

    lines = []
    if "read_file" in tool_name.lower():
        lines.append(f"Read file: {file_path}")
        if "start_line" in args:
            lines.append(
                f"Lines: {args['start_line']}-{args['start_line'] + args.get('num_lines', 0)}"
            )
    elif "edit_file" in tool_name.lower() or "write_file" in tool_name.lower():
        lines.append(f"Edit file: {file_path}")
        content_preview = str(args.get("new_content", ""))[:100]
        if len(content_preview) == 100:
            content_preview += "..."
        lines.append(f"Content preview: {content_preview}")
    elif "delete_file" in tool_name.lower():
        lines.append(f"⚠️ DELETE file: {file_path}")
    else:
        lines.append(f"File: {file_path}")

    return "\n".join(lines)


def format_agent_invocation(args: Dict[str, Any]) -> str:
    """Format agent invocation arguments for display."""
    agent_name = args.get("agent_name", "")
    prompt = args.get("prompt", "")
    session_id = args.get("session_id")

    lines = []
    lines.append(f"Agent: {agent_name}")

    # Truncate long prompts
    prompt_preview = prompt[:200]
    if len(prompt) > 200:
        prompt_preview += "..."
    lines.append(f"Prompt: {prompt_preview}")

    if session_id:
        lines.append(f"Session: {session_id}")

    return "\n".join(lines)


def format_grep(args: Dict[str, Any]) -> str:
    """Format grep arguments for display."""
    search_string = args.get("search_string", "")
    directory = args.get("directory", ".")

    return f"Search: {search_string}\nDirectory: {directory}"


def format_list_files(args: Dict[str, Any]) -> str:
    """Format list_files arguments for display."""
    directory = args.get("directory", ".")
    recursive = args.get("recursive", True)

    mode = "Recursive" if recursive else "Non-recursive"
    return f"List files: {directory}\nMode: {mode}"


def format_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Format tool call arguments in a human-readable way.

    Args:
        tool_name: Name of the tool being called
        args: Tool arguments dict

    Returns:
        Human-readable formatted string
    """
    # Shell commands
    if "shell" in tool_name.lower() or "command" in tool_name.lower():
        return format_shell_command(args)

    # File operations
    if any(
        word in tool_name.lower()
        for word in ["file", "read", "write", "edit", "delete"]
    ):
        return format_file_operation(tool_name, args)

    # Agent invocations
    if "agent" in tool_name.lower() or "invoke" in tool_name.lower():
        return format_agent_invocation(args)

    # Grep
    if "grep" in tool_name.lower() or "search" in tool_name.lower():
        return format_grep(args)

    # List files
    if "list" in tool_name.lower():
        return format_list_files(args)

    # Generic fallback - show all args
    lines = []
    for key, value in args.items():
        value_str = str(value)
        if len(value_str) > 100:
            value_str = value_str[:100] + "..."
        lines.append(f"{key}: {value_str}")

    return "\n".join(lines) if lines else "No arguments"


# Export main function
__all__ = ["format_tool_call"]
