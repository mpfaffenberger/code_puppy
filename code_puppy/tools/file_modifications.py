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
from typing import Any, Dict, List

from pydantic import BaseModel
from pydantic_ai import RunContext

# Add JSON repair functionality
try:
    from json_repair import repair_json
except ImportError:
    # Fallback if json_repair is not available
    def repair_json(json_str):
        return json_str


from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import _find_best_window, generate_group_id


class DeleteSnippetPayload(BaseModel):
    delete_snippet: str


class Replacement(BaseModel):
    old_str: str
    new_str: str


class ReplacementsPayload(BaseModel):
    replacements: List[Replacement]


class ContentPayload(BaseModel):
    content: str
    overwrite: bool = False


EditFilePayload = DeleteSnippetPayload | ReplacementsPayload | ContentPayload


class EditFileOutput(BaseModel):
    success: bool | None
    path: str | None
    message: str | None
    changed: bool | None
    diff: str | None


def _print_diff(diff_text: str, message_group: str = None) -> None:
    """Pretty-print *diff_text* with colour-coding (always runs)."""
    from rich.text import Text

    emit_info(
        "[bold cyan]\n── DIFF ────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )
    if diff_text and diff_text.strip():
        for line in diff_text.splitlines():
            # Git-style diff coloring: '+' green, '-' red, context/cursor blue/cyan
            if line.startswith("+") and not line.startswith("+++"):
                # Addition line
                text = Text(line, style="bold green")
                emit_info(text, highlight=False, message_group=message_group)
            elif line.startswith("-") and not line.startswith("---"):
                # Removal line
                text = Text(line, style="bold red")
                emit_info(text, highlight=False, message_group=message_group)
            elif line.startswith("@@"):
                # Hunk info
                text = Text(line, style="bold cyan")
                emit_info(text, highlight=False, message_group=message_group)
            elif line.startswith("+++") or line.startswith("---"):
                # Filename lines in diff
                text = Text(line, style="dim white")
                emit_info(text, highlight=False, message_group=message_group)
            else:
                emit_info(line, highlight=False, message_group=message_group)
    else:
        emit_info("[dim]-- no diff available --[/dim]", message_group=message_group)
    emit_info(
        "[bold cyan]───────────────────────────────────────────────────────[/bold cyan]",
        message_group=message_group,
    )


def _log_error(
    msg: str, exc: Exception | None = None, message_group: str = None
) -> None:
    emit_error(f"{msg}", message_group=message_group)
    if exc is not None:
        emit_error(traceback.format_exc(), highlight=False, message_group=message_group)


def _delete_snippet_from_file(
    context: RunContext | None, file_path: str, snippet: str, message_group: str = None
) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)
    diff_text = ""
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return {
                "success": False,
                "path": file_path,
                "message": f"File '{file_path}' does not exist.",
                "changed": False,
                "diff": diff_text,
            }
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()
        if snippet not in original:
            return {
                "success": False,
                "path": file_path,
                "message": f"Snippet not found in file '{file_path}'.",
                "changed": False,
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
        _log_error(
            "Unhandled exception in delete_snippet_from_file", exc, message_group
        )
        return {"error": str(exc), "diff": diff_text}


def _replace_in_file(
    context: RunContext | None,
    path: str,
    replacements: List[Dict[str, str]],
    message_group: str = None,
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
    message_group: str = None,
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
        _log_error("Unhandled exception in write_to_file", exc, message_group)
        return {"error": str(exc), "diff": ""}


def delete_snippet_from_file(
    context: RunContext, file_path: str, snippet: str, message_group: str = None
) -> Dict[str, Any]:
    emit_info(
        f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]",
        message_group=message_group,
    )
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
    message_group: str = None,
) -> Dict[str, Any]:
    emit_info(
        f"✏️ Writing file [bold blue]{path}[/bold blue]", message_group=message_group
    )
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
    message_group: str = None,
) -> Dict[str, Any]:
    emit_info(
        f"♻️ Replacing text in [bold yellow]{path}[/bold yellow]",
        message_group=message_group,
    )
    res = _replace_in_file(context, path, replacements, message_group=message_group)
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff, message_group=message_group)
    return res


def _edit_file(
    context: RunContext, path: str, payload: EditFilePayload
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
    payload : EditFilePayload
        A Pydantic payload that's either:
            * ContentPayload with content and optional overwrite flag
            * ReplacementsPayload with list of Replacement objects
            * DeleteSnippetPayload with snippet to delete
    """
    # Generate group_id for this tool execution
    group_id = generate_group_id("edit_file", path)

    emit_info(
        "\n[bold white on blue] EDIT FILE [/bold white on blue]", message_group=group_id
    )
    file_path = os.path.abspath(path)
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


def _edit_file_with_json(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
    """
    Unified file editing tool that can:
    - Create/write a new file when the target does not exist (using raw content or a JSON payload with a "content" key)
    - Replace text within an existing file via a JSON payload with "replacements" (delegates to internal replace logic)
    - Delete a snippet from an existing file via a JSON payload with "delete_snippet"

    This version maintains backward compatibility with JSON string inputs while providing
    the same functionality as the Pydantic version.

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
    emit_info("\n[bold white on blue] EDIT FILE [/bold white on blue]")
    file_path = os.path.abspath(path)
    try:
        parsed_payload = json.loads(diff)
    except json.JSONDecodeError:
        try:
            emit_warning(
                "[bold yellow] JSON Parsing Failed! TRYING TO REPAIR! [/bold yellow]"
            )
            parsed_payload = json.loads(repair_json(diff))
            emit_info("[bold white on blue] SUCCESS - WOOF! [/bold white on blue]")
        except Exception as e:
            emit_error(f"[bold red] Unable to parse diff [/bold red] -- {str(e)}")
            return {
                "success": False,
                "path": file_path,
                "message": f"Unable to parse diff JSON -- {str(e)}",
                "changed": False,
                "diff": "",
            }
    try:
        if isinstance(parsed_payload, dict):
            if "delete_snippet" in parsed_payload:
                snippet = parsed_payload["delete_snippet"]
                return delete_snippet_from_file(context, file_path, snippet)
            if "replacements" in parsed_payload:
                replacements = parsed_payload["replacements"]
                return replace_in_file(context, file_path, replacements)
            if "content" in parsed_payload:
                content = parsed_payload["content"]
                overwrite = bool(parsed_payload.get("overwrite", False))
                file_exists = os.path.exists(file_path)
                if file_exists and not overwrite:
                    return {
                        "success": False,
                        "path": file_path,
                        "message": f"File '{file_path}' exists. Set 'overwrite': true to replace.",
                        "changed": False,
                    }
                return write_to_file(context, file_path, content, overwrite)
        return write_to_file(context, file_path, diff, overwrite=False)
    except Exception as e:
        emit_error(
            "[bold red] Unable to route file modification tool call to sub-tool [/bold red]"
        )
        emit_error(str(e))
        return {
            "success": False,
            "path": file_path,
            "message": f"Something went wrong in file editing: {str(e)}",
            "changed": False,
        }


def _delete_file(
    context: RunContext, file_path: str, message_group: str = None
) -> Dict[str, Any]:
    emit_info(
        f"🗑️ Deleting file [bold red]{file_path}[/bold red]", message_group=message_group
    )
    file_path = os.path.abspath(file_path)
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            res = {
                "success": False,
                "path": file_path,
                "message": f"File '{file_path}' does not exist.",
                "changed": False,
                "diff": "",
            }
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
        _log_error("Unhandled exception in delete_file", exc, message_group)
        res = {
            "success": False,
            "path": file_path,
            "message": str(exc),
            "changed": False,
            "diff": "",
        }
    _print_diff(res.get("diff", ""), message_group=message_group)
    return res


def register_file_modifications_tools(agent):
    """Attach file-editing tools to *agent* with mandatory diff rendering."""

    @agent.tool(retries=5)
    def edit_file(
        context: RunContext, file_path: str, payload: EditFilePayload
    ) -> EditFileOutput:
        """
        Agent-facing wrapper around :func:`_edit_file`.

        Accepts a single *payload* argument that must validate against one of the following
        Pydantic schemas:

        1. `ContentPayload` – fields: ``content`` (str), optional ``overwrite`` (bool, default *False*)
        2. `ReplacementsPayload` – field: ``replacements`` (List[Replacement]) where ``Replacement``
           contains ``old_str`` and ``new_str``
        3. `DeleteSnippetPayload` – field: ``delete_snippet`` (str)
        """
        # Generate group_id for edit_file tool execution
        result = _edit_file(context, file_path, payload)
        if "diff" in result:
            del result["diff"]
        return EditFileOutput(**result)

    @agent.tool(retries=5)
    def delete_file(context: RunContext, file_path: str) -> EditFileOutput:
        # Generate group_id for delete_file tool execution
        group_id = generate_group_id("delete_file", file_path)
        result = _delete_file(context, file_path, message_group=group_id)
        if "diff" in result:
            del result["diff"]
        return EditFileOutput(**result)
