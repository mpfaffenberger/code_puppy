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

from json_repair import repair_json
from pydantic_ai import RunContext

from code_puppy.tools.common import _find_best_window, console


def _print_diff(diff_text: str) -> None:
    """Pretty-print *diff_text* with colour-coding (always runs)."""
    console.print(
        "[bold cyan]\n── DIFF ────────────────────────────────────────────────[/bold cyan]"
    )
    if diff_text and diff_text.strip():
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[bold green]{line}[/bold green]", highlight=False)
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[bold red]{line}[/bold red]", highlight=False)
            elif line.startswith("@"):
                console.print(f"[bold cyan]{line}[/bold cyan]", highlight=False)
            else:
                console.print(line, highlight=False)
    else:
        console.print("[dim]-- no diff available --[/dim]")
    console.print(
        "[bold cyan]───────────────────────────────────────────────────────[/bold cyan]"
    )


def _log_error(msg: str, exc: Exception | None = None) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")
    if exc is not None:
        console.print(traceback.format_exc(), highlight=False)


def _delete_snippet_from_file(
    context: RunContext | None, file_path: str, snippet: str
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
    except Exception as exc:  # noqa: BLE001
        _log_error("Unhandled exception in delete_snippet_from_file", exc)
        return {"error": str(exc), "diff": diff_text}


def _replace_in_file(
    context: RunContext | None, path: str, replacements: List[Dict[str, str]]
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

        if score < 0.95 or loc == None:
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
        console.print(
            "[bold yellow]No changes to apply – proposed content is identical.[/bold yellow]"
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
    context: RunContext, file_path: str, snippet: str
) -> Dict[str, Any]:
    console.log(f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]")
    res = _delete_snippet_from_file(context, file_path, snippet)
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff)
    return res


def write_to_file(
    context: RunContext, path: str, content: str, overwrite: bool
) -> Dict[str, Any]:
    console.log(f"✏️ Writing file [bold blue]{path}[/bold blue]")
    res = _write_to_file(context, path, content, overwrite=overwrite)
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff)
    return res


def replace_in_file(
    context: RunContext, path: str, replacements: List[Dict[str, str]]
) -> Dict[str, Any]:
    console.log(f"♻️ Replacing text in [bold yellow]{path}[/bold yellow]")
    res = _replace_in_file(context, path, replacements)
    diff = res.get("diff", "")
    if diff:
        _print_diff(diff)
    return res


def _edit_file(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
    """
    Unified file editing tool that can:
    - Create/write a new file when the target does not exist (using raw content or a JSON payload with a "content" key)
    - Replace text within an existing file via a JSON payload with "replacements" (delegates to internal replace logic)
    - Delete a snippet from an existing file via a JSON payload with "delete_snippet"
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
    console.print("\n[bold white on blue] EDIT FILE [/bold white on blue]")
    file_path = os.path.abspath(path)
    try:
        parsed_payload = json.loads(diff)
    except json.JSONDecodeError:
        try:
            console.print(
                "[bold yellow] JSON Parsing Failed! TRYING TO REPAIR! [/bold yellow]"
            )
            parsed_payload = json.loads(repair_json(diff))
            console.print("[bold white on blue] SUCCESS - WOOF! [/bold white on blue]")
        except Exception as e:
            console.print(f"[bold red] Unable to parse diff [/bold red] -- {str(e)}")
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
        console.print(
            "[bold red] Unable to route file modification tool call to sub-tool [/bold red]"
        )
        console.print(str(e))
        return {
            "success": False,
            "path": file_path,
            "message": f"Something went wrong in file editing: {str(e)}",
            "changed": False,
        }


def _delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
    console.log(f"🗑️ Deleting file [bold red]{file_path}[/bold red]")
    file_path = os.path.abspath(file_path)
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
    _print_diff(res.get("diff", ""))
    return res


def register_file_modifications_tools(agent):
    """Attach file-editing tools to *agent* with mandatory diff rendering."""

    @agent.tool(retries=5)
    def edit_file(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
        return _edit_file(context, path, diff)

    @agent.tool(retries=5)
    def delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        return _delete_file(context, file_path)
