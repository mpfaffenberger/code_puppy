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
from code_puppy.messaging import (  # Structured messaging types
    DiffLine,
    DiffMessage,
    emit_error,
    emit_warning,
    get_message_bus,
)
from code_puppy.tools.common import _find_best_window, generate_group_id


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


def _parse_diff_lines(diff_text: str) -> List[DiffLine]:
    """Parse unified diff text into structured DiffLine objects.

    Args:
        diff_text: Raw unified diff text

    Returns:
        List of DiffLine objects with line numbers and types
    """
    if not diff_text or not diff_text.strip():
        return []

    diff_lines = []
    line_number = 0

    for line in diff_text.splitlines():
        # Determine line type based on diff markers
        if line.startswith("+") and not line.startswith("+++"):
            line_type = "add"
            line_number += 1
            content = line[1:]  # Remove the + prefix
        elif line.startswith("-") and not line.startswith("---"):
            line_type = "remove"
            line_number += 1
            content = line[1:]  # Remove the - prefix
        elif line.startswith("@@"):
            # Parse hunk header to get line number
            # Format: @@ -start,count +start,count @@
            import re

            match = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if match:
                line_number = (
                    int(match.group(1)) - 1
                )  # Will be incremented on next line
            line_type = "context"
            content = line
        elif line.startswith("---") or line.startswith("+++"):
            # File headers - treat as context
            line_type = "context"
            content = line
        else:
            line_type = "context"
            line_number += 1
            content = line

        diff_lines.append(
            DiffLine(
                line_number=max(1, line_number),
                type=line_type,
                content=content,
            )
        )

    return diff_lines


def _emit_diff_message(
    file_path: str,
    operation: str,
    diff_text: str,
    old_content: str | None = None,
    new_content: str | None = None,
) -> None:
    """Emit a structured DiffMessage for UI display.

    Args:
        file_path: Path to the file being modified
        operation: One of 'create', 'modify', 'delete'
        diff_text: Raw unified diff text
        old_content: Original file content (optional)
        new_content: New file content (optional)
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
        pass  # Permission handler not available, emit anyway

    if not diff_text or not diff_text.strip():
        return

    diff_lines = _parse_diff_lines(diff_text)

    diff_msg = DiffMessage(
        path=file_path,
        operation=operation,
        old_content=old_content,
        new_content=new_content,
        diff_lines=diff_lines,
    )
    get_message_bus().emit(diff_msg)


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
        with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
            original = f.read()
        # Sanitize any surrogate characters from reading
        try:
            original = original.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
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

    with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
        original = f.read()

    # Sanitize any surrogate characters from reading
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
        _emit_diff_message(file_path, "modify", diff)
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
        # Determine operation type based on whether file existed
        operation = "modify" if overwrite else "create"
        _emit_diff_message(path, operation, diff, new_content=content)
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
        _emit_diff_message(path, "modify", diff)
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
            with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
                original = f.read()
            # Sanitize any surrogate characters from reading
            try:
                original = original.encode("utf-8", errors="surrogatepass").decode(
                    "utf-8", errors="replace"
                )
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
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

    diff = res.get("diff", "")
    if diff:
        _emit_diff_message(file_path, "delete", diff)
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
