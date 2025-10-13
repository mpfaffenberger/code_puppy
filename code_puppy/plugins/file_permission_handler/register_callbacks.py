"""File Permission Handler Plugin.

This plugin handles user permission prompts for file operations,
providing a consistent and extensible permission system.
"""

import difflib
import os
import sys
import threading
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import get_yolo_mode
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input
from code_puppy.tools.common import _find_best_window

# Lock for preventing multiple simultaneous permission prompts
_FILE_CONFIRMATION_LOCK = threading.Lock()


def _format_diff_line(line: str) -> str:
    """Apply diff-specific formatting to a single line."""
    if line.startswith("+") and not line.startswith("+++"):
        # Addition line - green with bold
        return f"[bold green]{line}[/bold green]"
    elif line.startswith("-") and not line.startswith("---"):
        # Removal line - red with bold
        return f"[bold red]{line}[/bold red]"
    elif line.startswith("@@"):
        # Hunk info - cyan with bold
        return f"[bold cyan]{line}[/bold cyan]"
    elif line.startswith("+++") or line.startswith("---"):
        # Filename lines in diff - dim white
        return f"[dim white]{line}[/dim white]"
    else:
        # Context lines - no special formatting, just return as-is
        return line


def _format_diff_with_highlighting(diff_text: str) -> str:
    """Format diff text with proper highlighting for consistent display."""
    if not diff_text or not diff_text.strip():
        return "[dim]-- no diff available --[/dim]"

    formatted_lines = []
    for line in diff_text.splitlines():
        formatted_lines.append(_format_diff_line(line))

    return "\n".join(formatted_lines)


def _preview_delete_snippet(file_path: str, snippet: str) -> str | None:
    """Generate a preview diff for deleting a snippet without modifying the file."""
    try:
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        if snippet not in original:
            return None

        modified = original.replace(snippet, "")
        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3,
            )
        )
        return diff_text
    except Exception:
        return None


def _preview_write_to_file(
    file_path: str, content: str, overwrite: bool = False
) -> str | None:
    """Generate a preview diff for writing to a file without modifying it."""
    try:
        file_path = os.path.abspath(file_path)
        exists = os.path.exists(file_path)

        if exists and not overwrite:
            return None

        diff_lines = difflib.unified_diff(
            [] if not exists else [""],
            content.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=3,
        )
        return "".join(diff_lines)
    except Exception:
        return None


def _preview_replace_in_file(
    file_path: str, replacements: list[dict[str, str]]
) -> str | None:
    """Generate a preview diff for replacing text in a file without modifying the file."""
    try:
        file_path = os.path.abspath(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original
        for rep in replacements:
            old_snippet = rep.get("old_str", "")
            new_snippet = rep.get("new_str", "")

            if old_snippet and old_snippet in modified:
                modified = modified.replace(old_snippet, new_snippet)
                continue

            # Use the same logic as file_modifications for fuzzy matching
            orig_lines = modified.splitlines()
            loc, score = _find_best_window(orig_lines, old_snippet)

            if score < 0.95 or loc is None:
                return None

            start, end = loc
            modified = (
                "\n".join(orig_lines[:start])
                + "\n"
                + new_snippet.rstrip("\n")
                + "\n"
                + "\n".join(orig_lines[end:])
            )

        if modified == original:
            return None

        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3,
            )
        )
        return diff_text
    except Exception:
        return None


def _preview_delete_file(file_path: str) -> str | None:
    """Generate a preview diff for deleting a file without modifying it."""
    try:
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                [],
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3,
            )
        )
        return diff_text
    except Exception:
        return None


def prompt_for_file_permission(
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
) -> bool:
    """Prompt the user for permission to perform a file operation.

    This function provides a unified permission prompt system for all file operations.

    Args:
        file_path: Path to the file being modified.
        operation: Description of the operation (e.g., "edit", "delete", "create").
        preview: Optional preview of changes (diff or content preview).
        message_group: Optional message group for organizing output.

    Returns:
        True if permission is granted, False otherwise.
    """
    yolo_mode = get_yolo_mode()

    # Skip confirmation only if in yolo mode (removed TTY check for better compatibility)
    if yolo_mode:
        return True

    # Try to acquire the lock to prevent multiple simultaneous prompts
    confirmation_lock_acquired = _FILE_CONFIRMATION_LOCK.acquire(blocking=False)
    if not confirmation_lock_acquired:
        emit_warning(
            "Another file operation is currently awaiting confirmation",
            message_group=message_group,
        )
        return False

    try:
        # Build a complete prompt message to ensure atomic display
        complete_message = "\n[bold yellow]🔒 File Operation Confirmation Required[/bold yellow]\n"
        complete_message += f"Request to [bold cyan]{operation}[/bold cyan] file: [bold white]{file_path}[/bold white]"

        if preview:
            complete_message += "\n\n[bold]Preview of changes:[/bold]\n"
            # Always format the preview with proper diff highlighting
            formatted_preview = _format_diff_with_highlighting(preview)
            complete_message += formatted_preview

        complete_message += "\n[bold yellow]💡 Hint: Press Enter or 'y' to accept, 'n' to reject[/bold yellow]"
        complete_message += f"\n[bold]Are you sure you want to {operation} {file_path}? (y(es) or enter as accept/n(o)) [/bold]"

        # Emit the complete message as one unit to prevent interruption
        emit_info(complete_message, message_group=message_group)

        # Force the message to display before prompting
        sys.stdout.write("\n")
        sys.stdout.flush()

        set_awaiting_user_input(True)

        try:
            user_input = input()
            # Empty input (Enter) counts as yes, like shell commands
            confirmed = user_input.strip().lower() in {"yes", "y", ""}
        except (KeyboardInterrupt, EOFError):
            emit_warning("\n Cancelled by user", message_group=message_group)
            confirmed = False
        finally:
            set_awaiting_user_input(False)

        if not confirmed:
            emit_info(
                "[bold red]✗ Permission denied. Operation cancelled.[/bold red]",
                message_group=message_group,
            )
            return False
        else:
            emit_info(
                "[bold green]✓ Permission granted. Proceeding with operation.[/bold green]",
                message_group=message_group,
            )
            return True

    finally:
        if confirmation_lock_acquired:
            _FILE_CONFIRMATION_LOCK.release()


def handle_edit_file_permission(
    context: Any,
    file_path: str,
    operation_type: str,
    operation_data: Any,
    message_group: str | None = None,
) -> bool:
    """Handle permission for edit_file operations with automatic preview generation.

    Args:
        context: The operation context
        file_path: Path to the file being operated on
        operation_type: Type of edit operation ('write', 'replace', 'delete_snippet')
        operation_data: Operation-specific data (content, replacements, snippet, etc.)
        message_group: Optional message group

    Returns:
        True if permission granted, False if denied
    """
    preview = None

    if operation_type == "write":
        content = operation_data.get("content", "")
        overwrite = operation_data.get("overwrite", False)
        preview = _preview_write_to_file(file_path, content, overwrite)
        operation_desc = "write to"
    elif operation_type == "replace":
        replacements = operation_data.get("replacements", [])
        preview = _preview_replace_in_file(file_path, replacements)
        operation_desc = "replace text in"
    elif operation_type == "delete_snippet":
        snippet = operation_data.get("delete_snippet", "")
        preview = _preview_delete_snippet(file_path, snippet)
        operation_desc = "delete snippet from"
    else:
        operation_desc = f"perform {operation_type} operation on"

    return prompt_for_file_permission(file_path, operation_desc, preview, message_group)


def handle_delete_file_permission(
    context: Any,
    file_path: str,
    message_group: str | None = None,
) -> bool:
    """Handle permission for delete_file operations with automatic preview generation.

    Args:
        context: The operation context
        file_path: Path to the file being deleted
        message_group: Optional message group

    Returns:
        True if permission granted, False if denied
    """
    preview = _preview_delete_file(file_path)
    return prompt_for_file_permission(file_path, "delete", preview, message_group)


def handle_file_permission(
    context: Any,
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
) -> bool:
    """Callback handler for file permission checks.

    This function is called by file operations to check for user permission.
    It returns True if the operation should proceed, False if it should be cancelled.

    Args:
        context: The operation context
        file_path: Path to the file being operated on
        operation: Description of the operation
        preview: Optional preview of changes
        message_group: Optional message group

    Returns:
        True if permission granted, False if denied
    """
    return prompt_for_file_permission(file_path, operation, preview, message_group)


def get_permission_handler_help() -> str:
    """Return help information for the file permission handler."""
    return """File Permission Handler Plugin:
- Unified permission prompts for all file operations
- YOLO mode support for automatic approval
- Thread-safe confirmation system
- Consistent user experience across file operations
- Detailed preview support with diff highlighting"""


# Register the callback for file permission handling
register_callback("file_permission", handle_file_permission)