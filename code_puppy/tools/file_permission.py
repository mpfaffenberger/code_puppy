"""File permission prompt system for code-puppy.

This module provides a permission prompt system that asks users for confirmation
before making file edits, similar to how yolo_mode works for shell commands.
"""

from __future__ import annotations

import sys
import threading


from code_puppy.config import get_yolo_mode
from code_puppy.messaging import emit_error, emit_info, emit_warning

# Lock for preventing multiple simultaneous permission prompts
_FILE_CONFIRMATION_LOCK = threading.Lock()


def prompt_for_file_permission(
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
) -> bool:
    """Prompt the user for permission to perform a file operation.

    This function mimics the behavior of shell command confirmation in command_runner.py.

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
            emit_info(preview, highlight=False, message_group=message_group)

        emit_info(
            "\n[bold]Do you want to proceed with this operation?[/bold]",
            message_group=message_group,
        )
        emit_info(
            "[dim]Enter 'y' or 'yes' to continue, anything else to cancel.[/dim]",
            message_group=message_group,
        )

        try:
            response = input().strip().lower()
            if response in ("y", "yes"):
                emit_info(
                    "[bold green]✓ Permission granted. Proceeding with operation.[/bold green]",
                    message_group=message_group,
                )
                return True
            else:
                emit_info(
                    "[bold red]✗ Permission denied. Operation cancelled.[/bold red]",
                    message_group=message_group,
                )
                return False
        except (EOFError, KeyboardInterrupt):
            emit_warning(
                "[bold yellow]⚠ No response received. Operation cancelled for safety.[/bold yellow]",
                message_group=message_group,
            )
            return False
        except Exception as e:
            emit_error(
                f"[bold red]✗ Error getting permission: {str(e)}. Operation cancelled for safety.[/bold red]",
                message_group=message_group,
            )
            return False
    finally:
        if confirmation_lock_acquired:
            _FILE_CONFIRMATION_LOCK.release()
