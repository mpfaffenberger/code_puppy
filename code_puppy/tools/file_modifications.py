"""Robust file-modification helpers + agent tools.

Key guarantees
--------------
1. **Create/edit operations emit diffs** when there are changes to show.
2. **Delete-file operations do not print removed content**; they only report deletion.
3. **Full traceback logging** for unexpected errors via `_log_error`.
4. Helper functions stay print-free while agent-tool wrappers handle console output.
"""

from __future__ import annotations

import difflib
import json
import os
import traceback
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
    emit_success,
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
        modified = original.replace(snippet, "", 1)
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

        modified = original
        for rep in replacements:
            old_snippet = rep.get("old_str", "")
            new_snippet = rep.get("new_str", "")

            if old_snippet and old_snippet in modified:
                modified = modified.replace(old_snippet, new_snippet, 1)
                continue

            had_trailing_newline = modified.endswith("\n")
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
            prefix = "\n".join(orig_lines[:start])
            suffix = "\n".join(orig_lines[end:])
            parts = []
            if prefix:
                parts.append(prefix)
            parts.append(new_snippet.rstrip("\n"))
            if suffix:
                parts.append(suffix)
            modified = "\n".join(parts)
            if had_trailing_newline and not modified.endswith("\n"):
                modified += "\n"

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
    except Exception as exc:
        return {"error": str(exc), "diff": diff_text}


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

        if exists:
            with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
                old_content = f.read()
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
            return {"error": f"File '{file_path}' does not exist."}

        os.remove(file_path)
        try:
            emit_success(f"Deleted file: {file_path}", message_group=message_group)
        except Exception:
            # Deletion already succeeded; UI notification failures should not flip it.
            pass
        return {
            "success": True,
            "path": file_path,
            "message": f"File '{file_path}' deleted successfully.",
            "changed": True,
        }
    except Exception as exc:
        _log_error("Unhandled exception in delete_file", exc)
        return {"error": str(exc)}


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
    def edit_file(
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
        """Safely delete a file and report the deletion.

        Delete operations intentionally do not generate or print diffs of removed content.
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


# Module-level aliases captured before registration functions are defined.
# Inside register_replace_in_file, the @agent.tool decorator creates a local
# function named 'replace_in_file' which shadows the module-level helper of the
# same name for the entire enclosing scope (Python scoping rules).  We capture
# a reference here so the registration function can call the helper.
_replace_in_file_helper = replace_in_file


def register_create_file(agent):
    """Register the create_file tool for creating or overwriting files."""
    # Local alias to avoid shadowing by the @agent.tool decorated function below
    _write_file = write_to_file

    @agent.tool
    def create_file(
        context: RunContext,
        file_path: str = "",
        content: str = "",
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Create a new file or overwrite an existing one with the provided content."""
        group_id = generate_group_id("create_file", file_path)
        result = _write_file(
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


# Inline JSON schema for Replacement objects — avoids $defs/$ref that many
# LLM providers misinterpret, causing frequent validation errors and
# fallback to full-file rewrites.
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


# List type that tolerates JSON-string-encoded arrays coming from the wire.
# BeforeValidator runs prior to type validation, so the advertised JSON schema
# (array of InlineReplacement) is unchanged — only inbound coercion is widened.
RepairableReplacementsList = Annotated[
    List[InlineReplacement],
    BeforeValidator(_coerce_replacements_arg),
]


def register_replace_in_file(agent):
    """Register the replace_in_file tool for targeted text replacements."""

    @agent.tool
    def replace_in_file(
        context: RunContext,
        file_path: str = "",
        replacements: RepairableReplacementsList = [],
    ) -> Dict[str, Any]:
        """Apply targeted text replacements to an existing file.

        Each replacement specifies an old_str to find and a new_str to replace it with.
        Replacements are applied sequentially. Prefer this over full file rewrites.
        """
        group_id = generate_group_id("replace_in_file", file_path)
        try:
            # Validate replacements up front so a malformed payload from the
            # model returns a clean error instead of bubbling a KeyError up
            # through pydantic_ai and tearing down the whole agent run.
            normalized: List[Dict[str, str]] = []
            for idx, raw in enumerate(replacements):
                # Per-item json_repair: some models stringify each replacement
                # individually (e.g. ["{\"old_str\": ...}", ...]). Heal those
                # before strict validation so we don't reject recoverable input.
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

            result = _replace_in_file_helper(
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
    _remove_snippet = delete_snippet_from_file

    @agent.tool
    def delete_snippet(
        context: RunContext,
        file_path: str = "",
        snippet: str = "",
    ) -> Dict[str, Any]:
        """Remove the first occurrence of a text snippet from a file."""
        group_id = generate_group_id("delete_snippet", file_path)
        result = _remove_snippet(context, file_path, snippet, message_group=group_id)
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
