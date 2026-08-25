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
from code_puppy.undo_manager import UndoManager
import warnings
from typing import Annotated, Any, Dict, List, Union

import json_repair
from pydantic import BaseModel, BeforeValidator, WithJsonSchema
from pydantic_ai import RunContext

from code_puppy.callbacks import on_delete_file, on_edit_file
from code_puppy.messaging import (  # Structured messaging types
    DiffLine,
    DiffMessage,
    emit_error,
    emit_warning,
    get_message_bus,
)
from code_puppy.tools import fs_access
from code_puppy.tools.common import (
    _find_best_window,
    generate_group_id,
    resolve_path,
    write_project_file,
)
from code_puppy.tools.line_endings import resolve_pattern, to_style
from code_puppy.tools.file_permission_state import (
    clear_diff_shown_flag,
    clear_user_feedback,
    get_last_user_feedback,
    was_diff_already_shown,
)


def _permission_denied(permission_results: List[Any]) -> bool:
    """Return True when any permission callback explicitly denies.

    Permission callbacks use a tri-state contract: ``False`` denies, ``True``
    approves, and ``None`` means no opinion.
    """
    return any(result is False for result in permission_results if result is not None)


def _create_rejection_response(file_path: str) -> Dict[str, Any]:
    """Create a standardized rejection response with user feedback if available.

    Args:
        file_path: Path to the file that was rejected

    Returns:
        Dict containing rejection details and any user feedback
    """
    # Check for user feedback from the permission provider. Falls back to
    # None when no provider (i.e. the file-permission plugin) is registered.
    user_feedback = get_last_user_feedback()
    # Clear feedback after reading it
    clear_user_feedback()

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
    # Check if diff was already shown during permission prompt. Defaults to
    # False (emit anyway) when no permission provider is registered.
    if was_diff_already_shown():
        # Diff already displayed in permission panel, skip redundant display
        clear_diff_shown_flag()
        return

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
    file_path = resolve_path(file_path)
    diff_text = ""
    try:
        if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
            return {"error": f"File '{file_path}' does not exist.", "diff": diff_text}
        original = fs_access.read_text(file_path)
        # Sanitize any surrogate characters from reading
        try:
            original = original.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        # Reconcile the model's \n-terminated snippet against the file's
        # actual line endings (see tools/line_endings.py).
        effective_snippet, snippet_count, _style = resolve_pattern(original, snippet)
        if not snippet_count:
            return {
                "error": f"Snippet not found in file '{file_path}'.",
                "diff": diff_text,
            }
        modified = original.replace(effective_snippet, "", 1)
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
        UndoManager().record_change(file_path, "delete_snippet")
        write_project_file(file_path, modified)
        return {
            "success": True,
            "path": file_path,
            "message": "Snippet deleted from file.",
            "changed": True,
            "diff": diff_text,
        }
    except Exception as exc:
        return {"error": str(exc), "diff": diff_text}


def _bounded_suggestion(
    haystack_lines: List[str],
    needle: str,
    max_lines: int = 6,
    max_chars: int = 400,
) -> Dict[str, Any] | None:
    """Build a whole-line-aligned, size-bounded, line-numbered hint of nearby
    text for a failed exact match. Never used to select a mutation target --
    read-only diagnostic output only. Bounding to whole lines (never a
    mid-line truncation) means a model can copy this text into an exact
    retry without the suggestion itself guaranteeing a second failure.
    """
    if not haystack_lines:
        return None
    loc, score = _find_best_window(haystack_lines, needle)
    if loc is not None:
        start, end = loc
    else:
        start, end = 0, min(len(haystack_lines), max(1, len(needle.splitlines()) or 1))
    if end - start > max_lines:
        end = start + max_lines
    end = min(end, len(haystack_lines))
    numbered = [f"{i + 1}: {haystack_lines[i]}" for i in range(start, end)]
    text = "\n".join(numbered)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + " \u2026(truncated)"
    return {
        "suggested_current_text": text,
        "jw_score": score,
        "start_line": start + 1,
        "end_line": end,
    }


def _replace_in_file(
    context: RunContext | None,
    path: str,
    replacements: List[Dict[str, str]],
    message_group: str | None = None,
) -> Dict[str, Any]:
    """Strict exact-match replacement engine.

    Contract: an empty ``old_str`` is rejected outright, zero exact matches
    and multiple (ambiguous) exact matches both fail closed without writing,
    fuzzy matching is used only to build a bounded suggestion for a failed
    match (never to select a mutation target), and every replacement in the
    batch is validated in memory before a single atomic write. Undo is
    recorded once, only immediately before that write actually happens --
    never on a validation failure or a no-op.
    """
    file_path = resolve_path(path)

    if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
        return {"error": f"File '{file_path}' does not exist.", "diff": ""}

    try:
        original = fs_access.read_text(file_path)
    except OSError as exc:
        return {"error": f"Failed to read file '{file_path}': {exc}", "diff": ""}

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

        if old_snippet == "":
            return {
                "error": "empty_old_str",
                "path": file_path,
                "message": "old_str must not be empty; an empty pattern is not a valid replacement target.",
                "diff": "",
            }

        # Models emit \n even when the file uses \r\n; reconcile the pattern
        # to the file's actual bytes instead of rewriting the file's endings.
        effective_old, match_count, style = resolve_pattern(modified, old_snippet)

        if match_count == 1:
            # Convert the replacement to the surrounding style so the edit
            # doesn't leave a mixed-terminator island behind.
            effective_new = to_style(new_snippet, style)
            modified = modified.replace(effective_old, effective_new, 1)
            continue

        if match_count == 0:
            suggestion = _bounded_suggestion(modified.splitlines(), old_snippet)
            result: Dict[str, Any] = {
                "error": "match_not_found",
                "path": file_path,
                "match_count": 0,
                "received": old_snippet,
                "diff": "",
            }
            if suggestion is not None:
                result.update(suggestion)
            return result

        # match_count > 1: ambiguous, do not guess which occurrence was meant.
        return {
            "error": "ambiguous_match",
            "path": file_path,
            "match_count": match_count,
            "message": (
                f"'old_str' matched {match_count} locations; make it unique "
                "(e.g. include more surrounding context) before retrying."
            ),
            "received": old_snippet,
            "diff": "",
        }

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

    # Snapshot pre-write state for undo now that every replacement has been
    # validated -- record_change reads current on-disk content, so it must
    # run immediately before the write, never after (after the write it
    # would snapshot the NEW content, turning undo into a no-op).
    UndoManager().record_change(path, "replace_in_file")
    try:
        write_project_file(file_path, modified)
    except OSError as exc:
        UndoManager().pop_change()
        return {
            "error": f"Failed to write file '{file_path}': {exc}",
            "diff": diff_text,
        }
    except Exception as exc:  # pragma: no cover - genuinely unexpected write failure
        UndoManager().pop_change()
        _log_error(
            f"Unexpected error writing '{file_path}' during replace_in_file",
            exc,
            message_group=message_group,
        )
        return {"error": f"Unexpected write failure: {exc}", "diff": diff_text}

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
    file_path = resolve_path(path)

    try:
        exists = fs_access.exists(file_path)
        if exists and not overwrite:
            return {
                "success": False,
                "path": file_path,
                "message": f"Cowardly refusing to overwrite existing file: {file_path}",
                "changed": False,
                "diff": "",
            }

        from code_puppy.config import get_diff_context_lines

        if exists:
            old_content = fs_access.read_text(file_path)
            try:
                old_content = old_content.encode(
                    "utf-8", errors="surrogatepass"
                ).decode("utf-8", errors="replace")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            old_lines = old_content.splitlines(keepends=True)
        else:
            old_lines = []

        diff_lines = difflib.unified_diff(
            old_lines,
            content.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
            n=get_diff_context_lines(),
        )
        diff_text = "".join(diff_lines)

        # Create local dirs only for local writes; a FS backend (e.g. ACP host)
        # manages its own topology.
        fs_access.make_dirs(os.path.dirname(file_path) or ".")
        # Snapshot pre-write state (None if the file doesn't exist yet, so
        # undo knows to delete rather than restore) immediately before the
        # write -- never after, which would snapshot the new content instead.
        UndoManager().record_change(path, "write_to_file")
        write_project_file(file_path, content)

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
    if _permission_denied(permission_results):
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
    if _permission_denied(permission_results):
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
    if _permission_denied(permission_results):
        return _create_rejection_response(path)

    res = _replace_in_file(context, path, replacements, message_group=message_group)
    diff = res.get("diff", "")
    if diff:
        _emit_diff_message(path, "modify", diff)
    return res


async def delete_snippet_from_file_async(
    context: RunContext, file_path: str, snippet: str, message_group: str | None = None
) -> Dict[str, Any]:
    """Async permission-aware variant of ``delete_snippet_from_file``."""
    from code_puppy.callbacks import on_file_permission_async

    operation_data = {"snippet": snippet}
    permission_results = await on_file_permission_async(
        context, file_path, "delete snippet from", None, message_group, operation_data
    )
    if _permission_denied(permission_results):
        return _create_rejection_response(file_path)

    res = _delete_snippet_from_file(
        context, file_path, snippet, message_group=message_group
    )
    diff = res.get("diff", "")
    if diff:
        _emit_diff_message(file_path, "modify", diff)
    return res


async def write_to_file_async(
    context: RunContext,
    path: str,
    content: str,
    overwrite: bool,
    message_group: str | None = None,
) -> Dict[str, Any]:
    """Async permission-aware variant of ``write_to_file``."""
    from code_puppy.callbacks import on_file_permission_async

    operation_data = {"content": content, "overwrite": overwrite}
    permission_results = await on_file_permission_async(
        context, path, "write", None, message_group, operation_data
    )
    if _permission_denied(permission_results):
        return _create_rejection_response(path)

    res = _write_to_file(
        context, path, content, overwrite=overwrite, message_group=message_group
    )
    diff = res.get("diff", "")
    if diff:
        operation = "modify" if overwrite else "create"
        _emit_diff_message(path, operation, diff, new_content=content)
    return res


async def replace_in_file_async(
    context: RunContext,
    path: str,
    replacements: List[Dict[str, str]],
    message_group: str | None = None,
) -> Dict[str, Any]:
    """Async permission-aware variant of ``replace_in_file``."""
    from code_puppy.callbacks import on_file_permission_async

    operation_data = {"replacements": replacements}
    permission_results = await on_file_permission_async(
        context, path, "replace text in", None, message_group, operation_data
    )
    if _permission_denied(permission_results):
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
    file_path = resolve_path(payload.file_path)

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
            file_exists = fs_access.exists(file_path)
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


async def _edit_file_async(
    context: RunContext, payload: EditFilePayload, group_id: str | None = None
) -> Dict[str, Any]:
    """Async permission-aware variant of ``_edit_file``."""
    file_path = os.path.abspath(payload.file_path)

    if group_id is None:
        group_id = generate_group_id("edit_file", file_path)

    try:
        if isinstance(payload, DeleteSnippetPayload):
            return await delete_snippet_from_file_async(
                context, file_path, payload.delete_snippet, message_group=group_id
            )
        elif isinstance(payload, ReplacementsPayload):
            replacements_dict = [
                {"old_str": rep.old_str, "new_str": rep.new_str}
                for rep in payload.replacements
            ]
            return await replace_in_file_async(
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
            return await write_to_file_async(
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
    file_path = resolve_path(file_path)

    # Use the plugin system for permission handling with operation data
    from code_puppy.callbacks import on_file_permission

    operation_data = {}  # No additional data needed for delete operations
    permission_results = on_file_permission(
        context, file_path, "delete", None, message_group, operation_data
    )

    # If any permission handler denies the operation, return cancelled result
    if _permission_denied(permission_results):
        return _create_rejection_response(file_path)

    try:
        if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
            res = {"error": f"File '{file_path}' does not exist.", "diff": ""}
        else:
            original = fs_access.read_text(file_path)
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
            # Snapshot BEFORE deleting -- once the file is gone, its content
            # cannot be recovered for undo to restore.
            UndoManager().record_change(file_path, "delete_file")
            fs_access.delete_file(file_path)
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


async def _delete_file_async(
    context: RunContext, file_path: str, message_group: str | None = None
) -> Dict[str, Any]:
    """Async permission-aware variant of ``_delete_file``."""
    file_path = resolve_path(file_path)

    from code_puppy.callbacks import on_file_permission_async

    operation_data = {}
    permission_results = await on_file_permission_async(
        context, file_path, "delete", None, message_group, operation_data
    )
    if _permission_denied(permission_results):
        return _create_rejection_response(file_path)

    try:
        if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
            res = {"error": f"File '{file_path}' does not exist.", "diff": ""}
        else:
            original = fs_access.read_text(file_path)
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
            fs_access.delete_file(file_path)
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
    """Register only the edit_file tool.

    .. deprecated::
        Use register_create_file, register_replace_in_file, and
        register_delete_snippet instead. edit_file is auto-expanded
        to these three tools when listed in an agent's tool config.
    """
    warnings.warn(
        "register_edit_file() is deprecated. Use register_create_file, "
        "register_replace_in_file, and register_delete_snippet instead. "
        "Agents listing 'edit_file' in their tools config will automatically "
        "get the three new tools via TOOL_EXPANSIONS.",
        DeprecationWarning,
        stacklevel=2,
    )

    @agent.tool
    async def edit_file(
        context: RunContext,
        payload: EditFilePayload | str = "",
    ) -> Dict[str, Any]:
        """Comprehensive file editing tool supporting multiple modification strategies.

        Supports: ContentPayload (create/overwrite), ReplacementsPayload (targeted edits),
        DeleteSnippetPayload (remove text). Prefer ReplacementsPayload for existing files.
        """
        # Handle string payload parsing (for models that send JSON strings)

        parse_error_message = "Payload must contain one of: 'content', 'replacements', or 'delete_snippet' with a 'file_path'."

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
                        "message": parse_error_message,
                        "changed": False,
                    }
            except Exception as e:
                return {
                    "success": False,
                    "path": "Not retrievable in Payload",
                    "message": f"edit_file call failed: {str(e)} - {parse_error_message}",
                    "changed": False,
                }

        # Call _edit_file which will extract file_path from payload and handle group_id generation
        result = await _edit_file_async(context, payload)
        on_edit_file(payload)
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
    async def delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        """Safely delete files with comprehensive logging and diff generation.

        Shows exactly what content was removed via diff output.
        """
        # Generate group_id for delete_file tool execution
        group_id = generate_group_id("delete_file", file_path)
        result = await _delete_file_async(context, file_path, message_group=group_id)

        # Trigger delete_file callbacks to enhance the result with rejection details
        # We do this before removing 'diff' so callbacks (like telemetry) can see what happened
        enhanced_results = on_delete_file(context, result, file_path)
        if enhanced_results:
            # Use the first non-None enhanced result
            for enhanced_result in enhanced_results:
                if enhanced_result is not None:
                    result = enhanced_result
                    break

        if "diff" in result:
            del result["diff"]

        return result


# Module-level alias captured before registration: the @agent.tool decorator's
# local 'replace_in_file' shadows the module helper inside the registration
# function (Python scoping), so we capture a reference here.
_replace_in_file_helper = replace_in_file_async


def register_create_file(agent):
    """Register the create_file tool for creating or overwriting files."""
    # Local alias to avoid shadowing by the @agent.tool decorated function below
    _write_file = write_to_file_async

    @agent.tool
    async def create_file(
        context: RunContext,
        file_path: str,
        content: str,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Create a new file or overwrite an existing one with the provided content."""
        group_id = generate_group_id("create_file", file_path)
        result = await _write_file(
            context, file_path, content, overwrite, message_group=group_id
        )
        if "diff" in result:
            del result["diff"]

        # Trigger legacy edit_file callbacks for backward compatibility
        payload = ContentPayload(
            file_path=file_path, content=content, overwrite=overwrite
        )
        enhanced_results = on_edit_file(context, result, payload)
        if enhanced_results:
            for enhanced_result in enhanced_results:
                if enhanced_result is not None:
                    result = enhanced_result
                    break

        return result


# Inline Replacement schema — avoids $defs/$ref that many LLM providers
# misinterpret (frequent validation errors / fallback to full-file rewrites).
_REPLACEMENT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "old_str": {"type": "string"},
        "new_str": {"type": "string"},
    },
    "required": ["old_str", "new_str"],
}

# Type alias used by the tool signature.  The Annotated + WithJsonSchema
# tells Pydantic to emit _REPLACEMENT_ITEM_SCHEMA inline instead of a $ref.
InlineReplacement = Annotated[Dict[str, str], WithJsonSchema(_REPLACEMENT_ITEM_SCHEMA)]


def _try_json_repair(v: Any) -> Any:
    """Best-effort: turn a JSON-ish string into a real Python value.

    Returns the parsed object on success, or the original ``v`` unchanged on
    failure (or if ``v`` isn't a string in the first place). Used by both the
    outer list coercion and the per-item validation in ``replace_in_file``.
    """
    if not isinstance(v, str):
        return v
    try:
        return json.loads(json_repair.repair_json(v))
    except Exception:
        return v


def _coerce_replacements_arg(v: Any) -> Any:
    """Coerce a stringified JSON array back into an actual list.

    Some tool-call serializers (looking at you, certain LLM clients) stringify
    list arguments into JSON before shipping them. Pydantic would otherwise
    reject those with ``Input should be a valid array``. We intercept strings
    here, best-effort parse them via ``json_repair``, and hand a real list to
    the normal validator. Non-strings pass through untouched so regular list
    inputs keep their fast path.
    """
    return _try_json_repair(v)


# List type tolerating JSON-string-encoded arrays from the wire. BeforeValidator
# widens only inbound coercion — the advertised schema stays an array.
RepairableReplacementsList = Annotated[
    List[InlineReplacement],
    BeforeValidator(_coerce_replacements_arg),
]


def register_replace_in_file(agent):
    """Register the replace_in_file tool for targeted text replacements."""

    @agent.tool
    async def replace_in_file(
        context: RunContext,
        file_path: str,
        replacements: RepairableReplacementsList,
    ) -> Dict[str, Any]:
        """Apply targeted text replacements to an existing file.

        Each replacement specifies an old_str to find and a new_str to replace it with.
        Replacements are applied sequentially. Prefer this over full file rewrites.
        """
        group_id = generate_group_id("replace_in_file", file_path)
        try:
            # Validate up front so a malformed payload returns a clean error
            # instead of tearing down the whole agent run via pydantic_ai.
            normalized: List[Dict[str, str]] = []
            for idx, raw in enumerate(replacements):
                # Per-item json_repair: some models stringify each replacement
                # individually — heal before strict validation.
                r = _try_json_repair(raw)
                if not isinstance(r, dict):
                    return {
                        "error": (
                            f"replacements[{idx}] must be an object with "
                            f"'old_str' and 'new_str' keys, got {type(raw).__name__}."
                        )
                    }
                missing = [k for k in ("old_str", "new_str") if k not in r]
                if missing:
                    return {
                        "error": (
                            f"replacements[{idx}] is missing required key(s): "
                            f"{', '.join(missing)}. Each replacement must include "
                            f"both 'old_str' and 'new_str'."
                        )
                    }
                normalized.append({"old_str": r["old_str"], "new_str": r["new_str"]})

            result = await _replace_in_file_helper(
                context, file_path, normalized, message_group=group_id
            )
            if "diff" in result:
                del result["diff"]

            # Trigger legacy edit_file callbacks for backward compatibility
            payload = ReplacementsPayload(
                file_path=file_path,
                replacements=[
                    Replacement(old_str=r["old_str"], new_str=r["new_str"])
                    for r in normalized
                ],
            )
            enhanced_results = on_edit_file(context, result, payload)
            if enhanced_results:
                for enhanced_result in enhanced_results:
                    if enhanced_result is not None:
                        result = enhanced_result
                        break

            return result
        except Exception as exc:
            # Last line of defense — never let this tool crash the agent run.
            _log_error(
                "Unhandled exception in replace_in_file",
                exc,
                message_group=group_id,
            )
            return {"error": f"replace_in_file failed: {exc}"}


def register_delete_snippet(agent):
    """Register the delete_snippet tool for removing text from files."""
    # Local alias to avoid shadowing by the @agent.tool decorated function below
    _remove_snippet = delete_snippet_from_file_async

    @agent.tool
    async def delete_snippet(
        context: RunContext,
        file_path: str,
        snippet: str,
    ) -> Dict[str, Any]:
        """Remove the first occurrence of a text snippet from a file."""
        group_id = generate_group_id("delete_snippet", file_path)
        result = await _remove_snippet(
            context, file_path, snippet, message_group=group_id
        )
        if "diff" in result:
            del result["diff"]

        # Trigger legacy edit_file callbacks for backward compatibility
        payload = DeleteSnippetPayload(file_path=file_path, delete_snippet=snippet)
        enhanced_results = on_edit_file(context, result, payload)
        if enhanced_results:
            for enhanced_result in enhanced_results:
                if enhanced_result is not None:
                    result = enhanced_result
                    break

        return result
