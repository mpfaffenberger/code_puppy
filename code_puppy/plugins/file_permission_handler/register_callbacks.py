"""File Permission Handler Plugin.

This plugin handles user permission prompts for file operations,
providing a consistent and extensible permission system.
"""

import sys
import threading
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import get_yolo_mode
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

# Lock for preventing multiple simultaneous permission prompts
_FILE_CONFIRMATION_LOCK = threading.Lock()


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

    # Skip confirmation if in yolo mode or not in an interactive TTY
    if yolo_mode or not sys.stdin.isatty():
        if not yolo_mode and not sys.stdin.isatty():
            emit_warning(
                "[yellow]Non-interactive terminal detected - auto-approving file operation[/yellow]",
                message_group=message_group,
            )
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
        emit_info(
            "\n[bold yellow]🔒 File Operation Confirmation Required[/bold yellow]",
            message_group=message_group,
        )

        emit_info(
            f"Request to [bold cyan]{operation}[/bold cyan] file: [bold white]{file_path}[/bold white]",
            message_group=message_group,
        )

        if preview:
            emit_info(
                "\n[bold]Preview of changes:[/bold]",
                message_group=message_group,
            )
            # Check if the preview is already formatted (contains color tags)
            if "[" in preview and "]" in preview and ("green" in preview or "red" in preview or "cyan" in preview):
                # Preview is already formatted with colors, emit as-is
                emit_info(preview, highlight=False, message_group=message_group)
            else:
                # Format the preview with diff coloring
                from code_puppy.tools.file_modifications import _format_diff_with_highlighting
                formatted_preview = _format_diff_with_highlighting(preview)
                emit_info(formatted_preview, highlight=False, message_group=message_group)

            emit_info(
                "[bold yellow]💡 Hint: Press Enter or 'y' to accept, 'n' to reject[/bold yellow]",
                message_group=message_group,
            )

        emit_info(
            f"\n[bold]Are you sure you want to {operation} {file_path}? (y(es) or enter as accept/n(o)) [/bold]",
            message_group=message_group,
        )
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