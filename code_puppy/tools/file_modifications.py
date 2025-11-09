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
import traceback
from typing import Any, Dict, List, Union

import json_repair
from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.callbacks import on_delete_file, on_edit_file
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import _find_best_window, generate_group_id

# File permission handling is now managed by the file_permission_handler plugin


def _create_rejection_response(file_path: str) -> Dict[str, Any]:
    """Create a standardized rejection response with user feedback if available.

    Args:
        file_path: Path to the file that was rejected

    Returns:
        Dict containing rejection details and any user feedback
    """
    # Check for user feedback from permission handler
    try:
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            clear_user_feedback,
            get_last_user_feedback,
        )

        user_feedback = get_last_user_feedback()
        # Clear feedback after reading it
        clear_user_feedback()
    except ImportError:
        user_feedback = None

    rejection_message = (
        "USER REJECTED: The user explicitly rejected these file changes."
    )
    if user_feedback:
        rejection_message += f" User feedback: {user_feedback}"
    else:
        rejection_message += " Please do not retry the same changes or any other changes - immediately ask for clarification."

    return {
        "success": False,
        "path": file_path,
        "message": rejection_message,
        "changed": False,
        "user_rejection": True,
        "rejection_type": "explicit_user_denial",
        "user_feedback": user_feedback,
    }


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


def _colorize_diff(diff_text: str) -> str:
    """Add color highlighting to diff lines based on user style preference.

    This function supports two modes:
    - 'text': ANSI color codes for additions (green) and deletions (red)
    - 'highlighted': Intelligent foreground/background color pairs for maximum contrast
    """
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
        get_diff_highlight_style,
    )

    if not diff_text:
        return diff_text

    style = get_diff_highlight_style()

    # Highlighted mode - use intelligent color pairs
    addition_base_color = get_diff_addition_color()
    deletion_base_color = get_diff_deletion_color()

    if style == "text":
        # Plain text mode - use simple Rich markup for additions and deletions
        colored_lines = []
        for line in diff_text.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                # Added lines - green
                colored_lines.append(
                    f"[{addition_base_color}]{line}[/{addition_base_color}]"
                )
            elif line.startswith("-") and not line.startswith("---"):
                # Removed lines - red
                colored_lines.append(
                    f"[{deletion_base_color}]{line}[/{deletion_base_color}]"
                )
            elif line.startswith("@@"):
                # Diff headers - cyan
                colored_lines.append(f"[cyan]{line}[/cyan]")
            elif line.startswith("+++") or line.startswith("---"):
                # File headers - yellow
                colored_lines.append(f"[yellow]{line}[/yellow]")
            else:
                # Unchanged lines - no color
                colored_lines.append(line)
        return "\n".join(colored_lines)

    # Get optimal foreground/background color pairs
    addition_fg, addition_bg = _get_optimal_color_pair(addition_base_color, "green")
    deletion_fg, deletion_bg = _get_optimal_color_pair(deletion_base_color, "orange1")

    # Create the color combinations
    addition_color = f"{addition_fg} on {addition_bg}"
    deletion_color = f"{deletion_fg} on {deletion_bg}"

    colored_lines = []
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            # Added lines - optimal contrast text on chosen background
            colored_lines.append(f"[{addition_color}]{line}[/{addition_color}]")
        elif line.startswith("-") and not line.startswith("---"):
            # Removed lines - optimal contrast text on chosen background
            colored_lines.append(f"[{deletion_color}]{line}[/{deletion_color}]")
        elif line.startswith("@@"):
            # Diff headers (cyan)
            colored_lines.append(f"[cyan]{line}[/cyan]")
        elif line.startswith("+++") or line.startswith("---"):
            # File headers (yellow)
            colored_lines.append(f"[yellow]{line}[/yellow]")
        else:
            # Unchanged lines (default color)
            colored_lines.append(line)

    return "\n".join(colored_lines)


def _get_optimal_color_pair(background_color: str, fallback_bg: str) -> tuple[str, str]:
    """Get optimal foreground/background color pair for maximum contrast and readability.

    This function maps each background color to the best foreground color
    for optimal contrast, following accessibility guidelines and color theory.

    Args:
        background_color: The requested background color name
        fallback_bg: A fallback background color that's known to work

    Returns:
        A tuple of (foreground_color, background_color) for optimal contrast
    """
    # Clean the color name (remove 'on_' prefix if present)
    clean_color = background_color.replace("on_", "")

    # Known valid background colors that work well as backgrounds
    valid_background_colors = {
        "red",
        "bright_red",
        "dark_red",
        "indian_red",
        "green",
        "bright_green",
        "dark_green",
        "sea_green",
        "blue",
        "bright_blue",
        "dark_blue",
        "deep_sky_blue",
        "yellow",
        "bright_yellow",
        "gold",
        "dark_gold",
        "magenta",
        "bright_magenta",
        "dark_magenta",
        "cyan",
        "bright_cyan",
        "dark_cyan",
        "white",
        "bright_white",
        "grey",
        "dark_grey",
        "orange1",
        "orange3",
        "orange4",  # These work
        "purple",
        "bright_purple",
        "dark_purple",
        "pink",
        "bright_pink",
        "dark_pink",
    }

    # Color mappings for common names that don't work as backgrounds
    color_mappings = {
        "orange": "orange1",  # orange doesn't work as bg, but orange1 does
        "bright_orange": "bright_yellow",  # bright_orange doesn't exist as bg
        "dark_orange": "orange3",  # dark_orange doesn't exist as bg
        "gold": "yellow",  # gold doesn't work as bg
        "dark_gold": "dark_yellow",  # dark_gold doesn't work as bg
    }

    # Apply mappings first
    if clean_color in color_mappings:
        clean_color = color_mappings[clean_color]

    # If the color is not valid as a background, use fallback
    if clean_color not in valid_background_colors:
        clean_color = fallback_bg

    # Optimal foreground color mapping for each background
    # Based on contrast ratios and readability
    optimal_foreground_map = {
        # Light backgrounds → dark text
        "white": "black",
        "bright_white": "black",
        "grey": "black",
        "yellow": "black",
        "bright_yellow": "black",
        "orange1": "black",
        "orange3": "white",  # Darker orange, white works better
        "orange4": "white",  # Darkest orange, white works best
        "bright_green": "black",
        "sea_green": "black",
        "bright_cyan": "black",
        "bright_blue": "white",  # Light blue but saturated, white better
        "bright_magenta": "white",
        "bright_purple": "white",
        "bright_pink": "black",  # Light pink, black better
        "bright_red": "white",
        # Dark backgrounds → light text
        "dark_grey": "white",
        "dark_red": "white",
        "dark_green": "white",
        "dark_blue": "white",
        "dark_magenta": "white",
        "dark_cyan": "white",
        "dark_purple": "white",
        "dark_pink": "white",
        "dark_yellow": "black",  # Dark yellow is actually olive-ish, black better
        # Medium/saturated backgrounds → specific choices
        "red": "white",
        "green": "white",
        "blue": "white",
        "magenta": "white",
        "cyan": "black",  # Cyan is light, black better
        "purple": "white",
        "pink": "black",  # Pink is light, black better
        "indian_red": "white",
        "deep_sky_blue": "black",  # Light sky blue, black better
    }

    # Get the optimal foreground color, defaulting to white for safety
    foreground_color = optimal_foreground_map.get(clean_color, "white")

    return foreground_color, clean_color


def _get_valid_background_color(color: str, fallback: str) -> str:
    """Legacy function - use _get_optimal_color_pair instead.

    Args:
        color: The requested color name
        fallback: A fallback color that's known to work as background

    Returns:
        A valid Rich background color name
    """
    _, bg_color = _get_optimal_color_pair(color, fallback)
    return bg_color


def _print_diff(diff_text: str, message_group: str | None = None) -> None:
    """Pretty-print *diff_text* with colour-coding.

    Skips printing if the diff was already shown during permission approval.
    """
    # Check if diff was already shown during permission prompt
    try:
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            clear_diff_shown_flag,
            was_diff_already_shown,
        )

        if was_diff_already_shown():
            # Diff already displayed in permission panel, skip redundant display
            clear_diff_shown_flag()
            return
    except ImportError:
        pass  # Permission handler not available, show diff anyway

    emit_info(
        "[bold cyan]\n── DIFF ────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )

    # Apply color formatting to diff lines
    formatted_diff = _colorize_diff(diff_text)

    emit_info(formatted_diff, highlight=False, message_group=message_group)

    emit_info(
        "[bold cyan]───────────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )


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
        from code_puppy.config import get_diff_context_lines

        diff_text = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=get_diff_context_lines(),
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

    from code_puppy.config import get_diff_context_lines

    diff_text = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=get_diff_context_lines(),
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

        from code_puppy.config import get_diff_context_lines

        diff_lines = difflib.unified_diff(
            [] if not exists else [""],
            content.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=get_diff_context_lines(),
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
    # Use the plugin system for permission handling with operation data
    from code_puppy.callbacks import on_file_permission

    operation_data = {"snippet": snippet}
    permission_results = on_file_permission(
        context, file_path, "delete snippet from", None, message_group, operation_data
    )

    # If any permission handler denies the operation, return cancelled result
    if permission_results and any(
        not result for result in permission_results if result is not None
    ):
        return _create_rejection_response(file_path)

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
    # Use the plugin system for permission handling with operation data
    from code_puppy.callbacks import on_file_permission

    operation_data = {"content": content, "overwrite": overwrite}
    permission_results = on_file_permission(
        context, path, "write", None, message_group, operation_data
    )

    # If any permission handler denies the operation, return cancelled result
    if permission_results and any(
        not result for result in permission_results if result is not None
    ):
        return _create_rejection_response(path)

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
    # Use the plugin system for permission handling with operation data
    from code_puppy.callbacks import on_file_permission

    operation_data = {"replacements": replacements}
    permission_results = on_file_permission(
        context, path, "replace text in", None, message_group, operation_data
    )

    # If any permission handler denies the operation, return cancelled result
    if permission_results and any(
        not result for result in permission_results if result is not None
    ):
        return _create_rejection_response(path)

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
    file_path = os.path.abspath(file_path)

    # Use the plugin system for permission handling with operation data
    from code_puppy.callbacks import on_file_permission

    operation_data = {}  # No additional data needed for delete operations
    permission_results = on_file_permission(
        context, file_path, "delete", None, message_group, operation_data
    )

    # If any permission handler denies the operation, return cancelled result
    if permission_results and any(
        not result for result in permission_results if result is not None
    ):
        return _create_rejection_response(file_path)

    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            res = {"error": f"File '{file_path}' does not exist.", "diff": ""}
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                original = f.read()
            from code_puppy.config import get_diff_context_lines

            diff_text = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    [],
                    fromfile=f"a/{os.path.basename(file_path)}",
                    tofile=f"b/{os.path.basename(file_path)}",
                    n=get_diff_context_lines(),
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

        # Trigger edit_file callbacks to enhance the result with rejection details
        enhanced_results = on_edit_file(context, result, payload)
        if enhanced_results:
            # Use the first non-None enhanced result
            for enhanced_result in enhanced_results:
                if enhanced_result is not None:
                    result = enhanced_result
                    break

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

        # Trigger delete_file callbacks to enhance the result with rejection details
        enhanced_results = on_delete_file(context, result, file_path)
        if enhanced_results:
            # Use the first non-None enhanced result
            for enhanced_result in enhanced_results:
                if enhanced_result is not None:
                    result = enhanced_result
                    break

        return result
