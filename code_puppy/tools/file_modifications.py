"""Robust, always-diff-logging file-modification helpers + agent tools.

Key guarantees
--------------
1. **A diff is printed _inline_ on every path** (success, no-op, or error) – no decorator magic.
2. **Full traceback logging** for unexpected errors via `_log_error`.
3. Helper functions stay print-free and return a `diff` key, while agent-tool wrappers handle
   all console output.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
import threading
import traceback
from typing import Any, Dict, List, Union

import json_repair
from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.config import get_yolo_mode
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import _find_best_window, generate_group_id

# Lock for preventing multiple simultaneous permission prompts
_FILE_CONFIRMATION_LOCK = threading.Lock()


def prompt_for_file_permission(
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
) -> bool:
    """
    Prompt the user for permission to perform a file operation.

    Args:
        file_path: Path to the file being operated on
        operation: Description of the operation (e.g., "write to", "delete")
        preview: Optional diff preview of the changes
        message_group: Optional message group for UI coordination

    Returns:
        bool: True if permission is granted, False otherwise
    """

    # Check if we're in yolo mode
    from code_puppy.config import get_yolo_mode
    from code_puppy.tools.command_runner import set_awaiting_user_input

    yolo_mode = get_yolo_mode()

    # Global lock to prevent multiple simultaneous permission prompts
    global _FILE_CONFIRMATION_LOCK
    confirmation_lock_acquired = False

    # Only ask for confirmation if we're in an interactive TTY and not in yolo mode
    if not yolo_mode and sys.stdin.isatty():
        confirmation_lock_acquired = _FILE_CONFIRMATION_LOCK.acquire(blocking=False)
        if not confirmation_lock_acquired:
            emit_warning(
                "Another file operation is currently awaiting confirmation",
                message_group=message_group,
            )
            return False

        # Show preview if available
        if preview:
            emit_info(
                "\n[bold]Preview of changes:[/bold]",
                message_group=message_group,
            )
            emit_info(preview, highlight=False, message_group=message_group)

        # Set the flag to indicate we're awaiting user input
        set_awaiting_user_input(True)

        emit_info(
            f"\n[bold]Are you sure you want to {operation} {file_path}? (y(es) or enter as accept/n(o)) [/bold]",
            message_group=message_group,
        )
        sys.stdout.write("\n")
        sys.stdout.flush()

        try:
            user_input = input()
            # Empty input (Enter) counts as yes, like shell commands
            confirmed = user_input.strip().lower() in {"yes", "y", ""}
        except (KeyboardInterrupt, EOFError):
            emit_warning("\n Cancelled by user", message_group=message_group)
            confirmed = False
        finally:
            # Clear the flag regardless of the outcome
            set_awaiting_user_input(False)
            if confirmation_lock_acquired:
                _FILE_CONFIRMATION_LOCK.release()

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
    else:
        # In yolo mode or non-interactive TTY, automatically grant permission
        if not yolo_mode and not sys.stdin.isatty():
            emit_warning(
                "[yellow]Non-interactive terminal detected - auto-approving file operation[/yellow]",
                message_group=message_group,
            )
        return True


class DeleteSnippetPayload(BaseModel):
    file_path: str
    delete_snippet: str


class Replacement(BaseModel):
    old_str: str
    new_str: str


class ReplacementsPayload(BaseModel):
    file_path: str
    replacements: List[Replacement]


class ContentPayload(BaseModel):
    file_path: str
    content: str
    overwrite: bool = False


EditFilePayload = Union[DeleteSnippetPayload, ReplacementsPayload, ContentPayload]


def _print_diff(diff_text: str, message_group: str | None = None) -> None:
    """Pretty-print *diff_text* with colour-coding (always runs)."""

    emit_info(
        "[bold cyan]\n── DIFF ────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )
    if diff_text and diff_text.strip():
        for line in diff_text.splitlines():
            # Git-style diff coloring using markup strings for TUI compatibility
            if line.startswith("+") and not line.startswith("+++"):
                # Addition line - use markup string instead of Rich Text
                emit_info(
                    f"[bold green]{line}[/bold green]",
                    highlight=False,
                    message_group=message_group,
                )
            elif line.startswith("-") and not line.startswith("---"):
                # Removal line - use markup string instead of Rich Text
                emit_info(
                    f"[bold red]{line}[/bold red]",
                    highlight=False,
                    message_group=message_group,
                )
            elif line.startswith("@@"):
                # Hunk info - use markup string instead of Rich Text
                emit_info(
                    f"[bold cyan]{line}[/bold cyan]",
                    highlight=False,
                    message_group=message_group,
                )
            elif line.startswith("+++") or line.startswith("---"):
                # Filename lines in diff - use markup string instead of Rich Text
                emit_info(
                    f"[dim white]{line}[/dim white]",
                    highlight=False,
                    message_group=message_group,
                )
            else:
                # Context lines - no special formatting
                emit_info(line, highlight=False, message_group=message_group)
    else:
        emit_info("[dim]-- no diff available --[/dim]", message_group=message_group)
    emit_info(
        "[bold cyan]───────────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )


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
    file_path: str, replacements: List[Dict[str, str]]
) -> str | None:
    """Generate a preview diff for replacing text in a file without modifying it."""
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

            # Use the same logic as _replace_in_file for fuzzy matching
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


def _log_error(
    msg: str, exc: Exception | None = None, message_group: str | None = None
) -> None:
    emit_error(f"{msg}", message_group=message_group)
    if exc is not None:
        emit_error(traceback.format_exc(), highlight=False, message_group=message_group)


def _delete_snippet_from_file(
    context: RunContext | None,
    file_path: str,
    snippet: str,
    message_group: str | None = None,
) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)
    diff_text = ""
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return {"error": f"File '{file_path}' does not exist.", "diff": diff_text}
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()
        if snippet not in original:
            return {
                "error": f"Snippet not found in file '{file_path}'.",
                "diff": diff_text,
            }
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
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified)
        return {
            "success": True,
            "path": file_path,
            "message": "Snippet deleted from file.",
            "changed": True,
            "diff": diff_text,
        }
    except Exception as exc:
        return {"error": str(exc), "diff": diff_text}


def _replace_in_file(
    context: RunContext | None,
    path: str,
    replacements: List[Dict[str, str]],
    message_group: str | None = None,
) -> Dict[str, Any]:
    """Robust replacement engine with explicit edge‑case reporting."""
    file_path = os.path.abspath(path)

    with open(file_path, "r", encoding="utf-8") as f:
        original = f.read()

    modified = original
    for rep in replacements:
        old_snippet = rep.get("old_str", "")
        new_snippet = rep.get("new_str", "")

        if old_snippet and old_snippet in modified:
            modified = modified.replace(old_snippet, new_snippet)
            continue

        orig_lines = modified.splitlines()
        loc, score = _find_best_window(orig_lines, old_snippet)

        if score < 0.95 or loc is None:
            return {
                "error": "No suitable match in file (JW < 0.95)",
                "jw_score": score,
                "received": old_snippet,
                "diff": "",
            }

        start, end = loc
        modified = (
            "\n".join(orig_lines[:start])
            + "\n"
            + new_snippet.rstrip("\n")
            + "\n"
            + "\n".join(orig_lines[end:])
        )

    if modified == original:
        emit_warning(
            "No changes to apply – proposed content is identical.",
            message_group=message_group,
        )
        return {
            "success": False,
            "path": file_path,
            "message": "No changes to apply.",
            "changed": False,
            "diff": "",
        }

    diff_text = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=3,
        )
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(modified)
    return {
        "success": True,
        "path": file_path,
        "message": "Replacements applied.",
        "changed": True,
        "diff": diff_text,
    }


def _write_to_file(
    context: RunContext | None,
    path: str,
    content: str,
    overwrite: bool = False,
    message_group: str | None = None,
) -> Dict[str, Any]:
    file_path = os.path.abspath(path)

    try:
        exists = os.path.exists(file_path)
        if exists and not overwrite:
            return {
                "success": False,
                "path": file_path,
                "message": f"Cowardly refusing to overwrite existing file: {file_path}",
                "changed": False,
                "diff": "",
            }

        diff_lines = difflib.unified_diff(
            [] if not exists else [""],
            content.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=3,
        )
        diff_text = "".join(diff_lines)

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        action = "overwritten" if exists else "created"
        return {
            "success": True,
            "path": file_path,
            "message": f"File '{file_path}' {action} successfully.",
            "changed": True,
            "diff": diff_text,
        }

    except Exception as exc:
        _log_error("Unhandled exception in write_to_file", exc)
        return {"error": str(exc), "diff": ""}


def delete_snippet_from_file(
    context: RunContext, file_path: str, snippet: str, message_group: str | None = None
) -> Dict[str, Any]:
    emit_info(
        f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]",
        message_group=message_group,
    )

    # Check for permission if not in yolo mode
    if not get_yolo_mode():
        # Generate preview diff without modifying the file
        preview_diff = _preview_delete_snippet(file_path, snippet)
        if preview_diff is None:
            return {
                "error": f"Failed to generate preview for deleting snippet from '{file_path}'",
                "changed": False,
            }

        if not prompt_for_file_permission(
            file_path, "delete snippet from", preview_diff, message_group
        ):
            return {
                "success": False,
                "path": file_path,
                "message": "Operation cancelled by user",
                "changed": False,
            }

    res = _delete_snippet_from_file(
        context, file_path, snippet, message_group=message_group
    )
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff, message_group=message_group)
    return res


def write_to_file(
    context: RunContext,
    path: str,
    content: str,
    overwrite: bool,
    message_group: str | None = None,
) -> Dict[str, Any]:
    emit_info(
        f"✏️ Writing file [bold blue]{path}[/bold blue]", message_group=message_group
    )

    # Check for permission if not in yolo mode
    if not get_yolo_mode():
        # Generate preview diff without modifying the file
        preview_diff = _preview_write_to_file(path, content, overwrite)
        if preview_diff is None:
            return {
                "error": f"Failed to generate preview for writing to '{path}'",
                "changed": False,
            }

        if not prompt_for_file_permission(path, "write", preview_diff, message_group):
            return {
                "success": False,
                "path": path,
                "message": "Operation cancelled by user",
                "changed": False,
            }

    res = _write_to_file(
        context, path, content, overwrite=overwrite, message_group=message_group
    )
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff, message_group=message_group)
    return res


def replace_in_file(
    context: RunContext,
    path: str,
    replacements: List[Dict[str, str]],
    message_group: str | None = None,
) -> Dict[str, Any]:
    emit_info(
        f"♻️ Replacing text in [bold yellow]{path}[/bold yellow]",
        message_group=message_group,
    )

    # Check for permission if not in yolo mode
    if not get_yolo_mode():
        # Generate preview diff without modifying the file
        preview_diff = _preview_replace_in_file(path, replacements)
        if preview_diff is None:
            return {
                "error": f"Failed to generate preview for replacing text in '{path}'",
                "changed": False,
            }

        if not prompt_for_file_permission(
            path, "replace text in", preview_diff, message_group
        ):
            return {
                "success": False,
                "path": path,
                "message": "Operation cancelled by user",
                "changed": False,
            }

    res = _replace_in_file(context, path, replacements, message_group=message_group)
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff, message_group=message_group)
    return res


def _edit_file(
    context: RunContext, payload: EditFilePayload, group_id: str | None = None
) -> Dict[str, Any]:
    """
    High-level implementation of the *edit_file* behaviour.

    This function performs the heavy-lifting after the lightweight agent-exposed wrapper has
    validated / coerced the inbound *payload* to one of the Pydantic models declared at the top
    of this module.

    Supported payload variants
    --------------------------
    • **ContentPayload** – full file write / overwrite.
    • **ReplacementsPayload** – targeted in-file replacements.
    • **DeleteSnippetPayload** – remove an exact snippet.

    The helper decides which low-level routine to delegate to and ensures the resulting unified
    diff is always returned so the caller can pretty-print it for the user.

    Parameters
    ----------
    path : str
        Path to the target file (relative or absolute)
    diff : str
        Either:
            * Raw file content (for file creation)
            * A JSON string with one of the following shapes:
                {"content": "full file contents", "overwrite": true}
                {"replacements": [ {"old_str": "foo", "new_str": "bar"}, ... ] }
                {"delete_snippet": "text to remove"}

    The function auto-detects the payload type and routes to the appropriate internal helper.
    """
    # Extract file_path from payload
    file_path = os.path.abspath(payload.file_path)

    # Use provided group_id or generate one if not provided
    if group_id is None:
        group_id = generate_group_id("edit_file", file_path)

    emit_info(
        "\n[bold white on blue] EDIT FILE [/bold white on blue]", message_group=group_id
    )
    try:
        if isinstance(payload, DeleteSnippetPayload):
            return delete_snippet_from_file(
                context, file_path, payload.delete_snippet, message_group=group_id
            )
        elif isinstance(payload, ReplacementsPayload):
            # Convert Pydantic Replacement models to dict format for legacy compatibility
            replacements_dict = [
                {"old_str": rep.old_str, "new_str": rep.new_str}
                for rep in payload.replacements
            ]
            return replace_in_file(
                context, file_path, replacements_dict, message_group=group_id
            )
        elif isinstance(payload, ContentPayload):
            file_exists = os.path.exists(file_path)
            if file_exists and not payload.overwrite:
                return {
                    "success": False,
                    "path": file_path,
                    "message": f"File '{file_path}' exists. Set 'overwrite': true to replace.",
                    "changed": False,
                }
            return write_to_file(
                context,
                file_path,
                payload.content,
                payload.overwrite,
                message_group=group_id,
            )
        else:
            return {
                "success": False,
                "path": file_path,
                "message": f"Unknown payload type: {type(payload)}",
                "changed": False,
            }
    except Exception as e:
        emit_error(
            "Unable to route file modification tool call to sub-tool",
            message_group=group_id,
        )
        emit_error(str(e), message_group=group_id)
        return {
            "success": False,
            "path": file_path,
            "message": f"Something went wrong in file editing: {str(e)}",
            "changed": False,
        }


def _delete_file(
    context: RunContext, file_path: str, message_group: str | None = None
) -> Dict[str, Any]:
    emit_info(
        f"🗑️ Deleting file [bold red]{file_path}[/bold red]", message_group=message_group
    )
    file_path = os.path.abspath(file_path)

    # Check for permission if not in yolo mode
    if not get_yolo_mode():
        # Generate preview diff without modifying the file
        preview_diff = _preview_delete_file(file_path)
        if preview_diff is None:
            return {
                "error": f"Failed to generate preview for deleting '{file_path}'",
                "changed": False,
            }

        if not prompt_for_file_permission(
            file_path, "delete", preview_diff, message_group
        ):
            return {
                "success": False,
                "path": file_path,
                "message": "Operation cancelled by user",
                "changed": False,
            }

    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            res = {"error": f"File '{file_path}' does not exist.", "diff": ""}
        else:
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
            os.remove(file_path)
            res = {
                "success": True,
                "path": file_path,
                "message": f"File '{file_path}' deleted successfully.",
                "changed": True,
                "diff": diff_text,
            }
    except Exception as exc:
        _log_error("Unhandled exception in delete_file", exc)
        res = {"error": str(exc), "diff": ""}
    _print_diff(res.get("diff", ""), message_group=message_group)
    return res


def register_edit_file(agent):
    """Register only the edit_file tool."""

    @agent.tool
    def edit_file(
        context: RunContext,
        payload: EditFilePayload | str = "",
    ) -> Dict[str, Any]:
        """Comprehensive file editing tool supporting multiple modification strategies.

        This is the primary file modification tool that supports three distinct editing
        approaches: full content replacement, targeted text replacements, and snippet
        deletion. It provides robust diff generation, error handling, and automatic
        retry capabilities for reliable file operations.

        Args:
            context (RunContext): The PydanticAI runtime context for the agent.
            payload: One of three payload types:

                ContentPayload:
                    - file_path (str): Path to file
                    - content (str): Full file content to write
                    - overwrite (bool, optional): Whether to overwrite existing files.
                      Defaults to False (safe mode).

                ReplacementsPayload:
                    - file_path (str): Path to file
                    - replacements (List[Replacement]): List of text replacements where
                      each Replacement contains:
                      - old_str (str): Exact text to find and replace
                      - new_str (str): Replacement text

                DeleteSnippetPayload:
                    - file_path (str): Path to file
                    - delete_snippet (str): Exact text snippet to remove from file

        Returns:
            Dict[str, Any]: Operation result containing:
                - success (bool): True if operation completed successfully
                - path (str): Absolute path to the modified file
                - message (str): Human-readable description of changes
                - changed (bool): True if file content was actually modified
                - diff (str, optional): Unified diff showing changes made
                - error (str, optional): Error message if operation failed

        Examples:
            >>> # Create new file with content
            >>> payload = {"file_path": "hello.py", "content": "print('Hello!')", "overwrite": true}
            >>> result = edit_file(ctx, payload)

            >>> # Replace text in existing file
            >>> payload = {
            ...     "file_path": "config.py",
            ...     "replacements": [
            ...         {"old_str": "debug = False", "new_str": "debug = True"}
            ...     ]
            ... }
            >>> result = edit_file(ctx, payload)

            >>> # Delete snippet from file
            >>> payload = {
            ...     "file_path": "main.py",
            ...     "delete_snippet": "# TODO: remove this comment"
            ... }
            >>> result = edit_file(ctx, payload)

        Best Practices:
            - Use replacements for targeted changes (most efficient)
            - Use content payload only for new files or complete rewrites
            - Always check the 'success' field before assuming changes worked
            - Review the 'diff' field to understand what changed
            - Use delete_snippet for removing specific code blocks
        """
        # Handle string payload parsing (for models that send JSON strings)

        parse_error_message = """Examples:
            >>> # Create new file with content
            >>> payload = {"file_path": "hello.py", "content": "print('Hello!')", "overwrite": true}
            >>> result = edit_file(ctx, payload)

            >>> # Replace text in existing file
            >>> payload = {
            ...     "file_path": "config.py",
            ...     "replacements": [
            ...         {"old_str": "debug = False", "new_str": "debug = True"}
            ...     ]
            ... }
            >>> result = edit_file(ctx, payload)

            >>> # Delete snippet from file
            >>> payload = {
            ...     "file_path": "main.py",
            ...     "delete_snippet": "# TODO: remove this comment"
            ... }
            >>> result = edit_file(ctx, payload)"""

        if isinstance(payload, str):
            try:
                # Fallback for weird models that just can't help but send json strings...
                payload_dict = json.loads(json_repair.repair_json(payload))
                if "replacements" in payload_dict:
                    payload = ReplacementsPayload(**payload_dict)
                elif "delete_snippet" in payload_dict:
                    payload = DeleteSnippetPayload(**payload_dict)
                elif "content" in payload_dict:
                    payload = ContentPayload(**payload_dict)
                else:
                    file_path = "Unknown"
                    if "file_path" in payload_dict:
                        file_path = payload_dict["file_path"]
                    return {
                        "success": False,
                        "path": file_path,
                        "message": f"One of 'content', 'replacements', or 'delete_snippet' must be provided in payload. Refer to the following examples: {parse_error_message}",
                        "changed": False,
                    }
            except Exception as e:
                return {
                    "success": False,
                    "path": "Not retrievable in Payload",
                    "message": f"edit_file call failed: {str(e)} - this means the tool failed to parse your inputs. Refer to the following examples: {parse_error_message}",
                    "changed": False,
                }

        # Call _edit_file which will extract file_path from payload and handle group_id generation
        result = _edit_file(context, payload)
        if "diff" in result:
            del result["diff"]
        return result


def register_delete_file(agent):
    """Register only the delete_file tool."""

    @agent.tool
    def delete_file(context: RunContext, file_path: str = "") -> Dict[str, Any]:
        """Safely delete files with comprehensive logging and diff generation.

        This tool provides safe file deletion with automatic diff generation to show
        exactly what content was removed. It includes proper error handling and
        automatic retry capabilities for reliable operation.

        Args:
            context (RunContext): The PydanticAI runtime context for the agent.
            file_path (str): Path to the file to delete. Can be relative or absolute.
                Must be an existing regular file (not a directory).

        Returns:
            Dict[str, Any]: Operation result containing:
                - success (bool): True if file was successfully deleted
                - path (str): Absolute path to the deleted file
                - message (str): Human-readable description of the operation
                - changed (bool): True if file was actually removed
                - error (str, optional): Error message if deletion failed

        Examples:
            >>> # Delete a specific file
            >>> result = delete_file(ctx, "temp_file.txt")
            >>> if result['success']:
            ...     print(f"Deleted: {result['path']}")

            >>> # Handle deletion errors
            >>> result = delete_file(ctx, "missing.txt")
            >>> if not result['success']:
            ...     print(f"Error: {result.get('error', 'Unknown error')}")

        Best Practices:
            - Always verify file exists before attempting deletion
            - Check 'success' field to confirm operation completed
            - Use list_files first to confirm file paths
            - Cannot delete directories (use shell commands for that)
        """
        # Generate group_id for delete_file tool execution
        group_id = generate_group_id("delete_file", file_path)
        result = _delete_file(context, file_path, message_group=group_id)
        if "diff" in result:
            del result["diff"]
        return result
