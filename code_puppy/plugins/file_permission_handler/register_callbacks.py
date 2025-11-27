"""File Permission Handler Plugin.

This plugin handles user permission prompts for file operations,
providing a consistent and extensible permission system.
"""

import difflib
import os
import threading
from typing import Any

from rich.text import Text as RichText

from code_puppy.callbacks import register_callback
from code_puppy.config import get_diff_context_lines, get_yolo_mode
from code_puppy.messaging import emit_warning
from code_puppy.tools.common import (
    _find_best_window,
    get_user_approval,
)

# Lock for preventing multiple simultaneous permission prompts
_FILE_CONFIRMATION_LOCK = threading.Lock()

# Thread-local storage for user feedback from permission prompts
_thread_local = threading.local()


def get_last_user_feedback() -> str | None:
    """Get the last user feedback from a permission prompt in this thread.

    Returns:
        The user feedback string, or None if no feedback was provided.
    """
    return getattr(_thread_local, "last_user_feedback", None)


def _set_user_feedback(feedback: str | None) -> None:
    """Store user feedback in thread-local storage."""
    _thread_local.last_user_feedback = feedback


def clear_user_feedback() -> None:
    """Clear any stored user feedback."""
    _thread_local.last_user_feedback = None


def set_diff_already_shown(shown: bool = True) -> None:
    """Mark that a diff preview was already shown during permission prompt."""
    _thread_local.diff_already_shown = shown


def was_diff_already_shown() -> bool:
    """Check if a diff was already shown during the permission prompt.

    Returns:
        True if diff was shown, False otherwise
    """
    return getattr(_thread_local, "diff_already_shown", False)


def clear_diff_shown_flag() -> None:
    """Clear the diff-already-shown flag."""
    _thread_local.diff_already_shown = False


# Diff formatting is now handled by common.format_diff_with_colors()
# Arrow selector and approval UI now handled by common.get_user_approval()


def _preview_delete_snippet(file_path: str, snippet: str) -> str | None:
    """Generate a preview diff for deleting a snippet without modifying the file."""
    try:
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return None

        with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
            original = f.read()

        # Sanitize any surrogate characters
        try:
            original = original.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        if snippet not in original:
            return None

        modified = original.replace(snippet, "")
        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=get_diff_context_lines(),
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
            n=get_diff_context_lines(),
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

        with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
            original = f.read()

        # Sanitize any surrogate characters
        try:
            original = original.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

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
                n=get_diff_context_lines(),
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

        with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
            original = f.read()

        # Sanitize any surrogate characters
        try:
            original = original.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                [],
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=get_diff_context_lines(),
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
) -> tuple[bool, str | None]:
    """Prompt the user for permission to perform a file operation.

    This function provides a unified permission prompt system for all file operations.

    Args:
        file_path: Path to the file being modified.
        operation: Description of the operation (e.g., "edit", "delete", "create").
        preview: Optional preview of changes (diff or content preview).
        message_group: Optional message group for organizing output.

    Returns:
        Tuple of (confirmed: bool, user_feedback: str | None)
        - confirmed: True if permission is granted, False otherwise
        - user_feedback: Optional feedback message from user to send back to the model
    """
    yolo_mode = get_yolo_mode()

    # Skip confirmation only if in yolo mode (removed TTY check for better compatibility)
    if yolo_mode:
        return True, None

    # Try to acquire the lock to prevent multiple simultaneous prompts
    confirmation_lock_acquired = _FILE_CONFIRMATION_LOCK.acquire(blocking=False)
    if not confirmation_lock_acquired:
        emit_warning(
            "Another file operation is currently awaiting confirmation",
            message_group=message_group,
        )
        return False, None

    try:
        # Build panel content
        panel_content = RichText()
        panel_content.append("🔒 Requesting permission to ", style="bold yellow")
        panel_content.append(operation, style="bold cyan")
        panel_content.append(":\n", style="bold yellow")
        panel_content.append("📄 ", style="dim")
        panel_content.append(file_path, style="bold white")

        # Use the common approval function
        confirmed, user_feedback = get_user_approval(
            title="File Operation",
            content=panel_content,
            preview=preview,
            border_style="dim white",
        )

        return confirmed, user_feedback

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

    confirmed, user_feedback = prompt_for_file_permission(
        file_path, operation_desc, preview, message_group
    )
    # Store feedback in thread-local storage so the tool can access it
    _set_user_feedback(user_feedback)
    return confirmed


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
    confirmed, user_feedback = prompt_for_file_permission(
        file_path, "delete", preview, message_group
    )
    # Store feedback in thread-local storage so the tool can access it
    _set_user_feedback(user_feedback)
    return confirmed


def handle_file_permission(
    context: Any,
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
    operation_data: Any = None,
) -> bool:
    """Callback handler for file permission checks.

    This function is called by file operations to check for user permission.
    It returns True if the operation should proceed, False if it should be cancelled.

    Args:
        context: The operation context
        file_path: Path to the file being operated on
        operation: Description of the operation
        preview: Optional preview of changes (deprecated - use operation_data instead)
        message_group: Optional message group
        operation_data: Operation-specific data for preview generation

    Returns:
        True if permission granted, False if denied
    """
    # Generate preview from operation_data if provided
    if operation_data is not None:
        preview = _generate_preview_from_operation_data(
            file_path, operation, operation_data
        )

    confirmed, user_feedback = prompt_for_file_permission(
        file_path, operation, preview, message_group
    )
    # Store feedback in thread-local storage so the tool can access it
    _set_user_feedback(user_feedback)
    return confirmed


def _generate_preview_from_operation_data(
    file_path: str, operation: str, operation_data: Any
) -> str | None:
    """Generate preview diff from operation data.

    Args:
        file_path: Path to the file
        operation: Type of operation
        operation_data: Operation-specific data

    Returns:
        Preview diff or None if generation fails
    """
    try:
        if operation == "delete":
            return _preview_delete_file(file_path)
        elif operation == "write":
            content = operation_data.get("content", "")
            overwrite = operation_data.get("overwrite", False)
            return _preview_write_to_file(file_path, content, overwrite)
        elif operation == "delete snippet from":
            snippet = operation_data.get("snippet", "")
            return _preview_delete_snippet(file_path, snippet)
        elif operation == "replace text in":
            replacements = operation_data.get("replacements", [])
            return _preview_replace_in_file(file_path, replacements)
        elif operation == "edit_file":
            # Handle edit_file operations
            if "delete_snippet" in operation_data:
                return _preview_delete_snippet(
                    file_path, operation_data["delete_snippet"]
                )
            elif "replacements" in operation_data:
                return _preview_replace_in_file(
                    file_path, operation_data["replacements"]
                )
            elif "content" in operation_data:
                content = operation_data.get("content", "")
                overwrite = operation_data.get("overwrite", False)
                return _preview_write_to_file(file_path, content, overwrite)

        return None
    except Exception:
        return None


def get_permission_handler_help() -> str:
    """Return help information for the file permission handler."""
    return """File Permission Handler Plugin:
- Unified permission prompts for all file operations
- YOLO mode support for automatic approval
- Thread-safe confirmation system
- Consistent user experience across file operations
- Detailed preview support with diff highlighting
- Automatic preview generation from operation data"""


def get_file_permission_prompt_additions() -> str:
    """Return file permission handling prompt additions for agents.

    This function provides the file permission rejection handling
    instructions that can be dynamically injected into agent prompts
    via the prompt hook system.

    Only returns instructions when yolo_mode is off (False).
    """
    # Only inject permission handling instructions when yolo mode is off
    if get_yolo_mode():
        return ""  # Return empty string when yolo mode is enabled

    return """
## 💬 USER FEEDBACK SYSTEM

**How User Approval Works:**

When you attempt file operations or shell commands, the user sees a beautiful prompt with three options:
1. **Press Enter or 'y'** → Approve (proceed with the operation as-is)
2. **Type 'n'** → Reject silently (cancel without feedback)
3. **Type any other text** → **Reject WITH feedback** (cancel and tell you what to do instead)

**Understanding User Feedback:**

When you receive a rejection response with `user_feedback` field populated:
- The user is **rejecting your current approach**
- They are **telling you what they want instead**
- The feedback is in the `user_feedback` field or included in the error message

Example tool response:
```
{
  "success": false,
  "user_rejection": true,
  "user_feedback": "Add error handling and use async/await",
  "message": "USER REJECTED: The user explicitly rejected these file changes. User feedback: Add error handling and use async/await"
}
```

**WHEN YOU RECEIVE USER FEEDBACK, YOU MUST:**

1. **🛑 STOP the current approach** - Do NOT retry the same operation
2. **📝 READ the feedback carefully** - The user is telling you what they want
3. **✅ IMPLEMENT their suggestion** - Modify your approach based on their feedback
4. **🔄 TRY AGAIN with the changes** - Apply the feedback and attempt the operation again

**Example Flow:**
```
You: *attempts to create function without error handling*
User: "Add try/catch error handling" → REJECTS with feedback
You: *modifies code to include try/catch*
You: *attempts operation again with improved code*
User: *approves*
```

**WHEN FEEDBACK IS EMPTY (silent rejection):**

If `user_feedback` is None/empty, the user rejected without guidance:
- **STOP immediately**
- **ASK the user** what they want instead
- **WAIT for explicit direction**

**KEY POINTS:**
- Feedback is **guidance**, not criticism - use it to improve!
- The user wants the operation done **their way**
- Implement the feedback and **try again**
- Don't ask permission again - **just do it better**

This system lets users guide you interactively! 🐶✨
"""


# Register the callback for file permission handling
register_callback("file_permission", handle_file_permission)

# Register the prompt hook for file permission instructions
register_callback("load_prompt", get_file_permission_prompt_additions)
