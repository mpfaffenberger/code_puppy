# file_modifications.py
"""Robust, always-diff-logging file-modification helpers + agent tools.

Key guarantees
--------------
1. **A diff is printed _inline_ on every path** (success, no-op, or error) – no decorator magic.
2. **Full traceback logging** for unexpected errors via `_log_error`.
3. Helper functions stay print-free and return a `diff` key, while agent-tool wrappers handle
   all console output.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import traceback
from typing import Any, Dict, List

from code_puppy.tools.common import console
from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Console helpers – shared across tools
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pure helpers – no console output
# ---------------------------------------------------------------------------


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
    context: RunContext | None, path: str, diff: str
) -> Dict[str, Any]:
    """Robust replacement engine with explicit edge‑case reporting."""
    file_path = os.path.abspath(path)
    preview = (diff[:400] + "…") if len(diff) > 400 else diff  # for logs / errors
    diff_text = ""
    try:
        if not os.path.exists(file_path):
            return {"error": f"File '{file_path}' does not exist", "diff": preview}

        # ── Parse diff payload (tolerate single quotes) ──────────────────
        try:
            payload = json.loads(diff)
        except json.JSONDecodeError:
            try:
                payload = json.loads(diff.replace("'", '"'))
            except Exception as exc:
                return {
                    "error": "Could not parse diff as JSON.",
                    "reason": str(exc),
                    "received": preview,
                    "diff": preview,
                }
        if not isinstance(payload, dict):
            try:
                payload = ast.literal_eval(diff)
            except Exception as exc:
                return {
                    "error": "Diff is neither valid JSON nor Python literal.",
                    "reason": str(exc),
                    "received": preview,
                    "diff": preview,
                }

        replacements: List[Dict[str, str]] = payload.get("replacements", [])
        if not replacements:
            return {
                "error": "No valid replacements found in diff.",
                "received": preview,
                "diff": preview,
            }

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original
        for rep in replacements:
            modified = modified.replace(rep.get("old_str", ""), rep.get("new_str", ""))

        if modified == original:
            # ── Explicit no‑op edge case ────────────────────────────────
            console.print(
                "[bold yellow]No changes to apply – proposed content is identical.[/bold yellow]"
            )
            return {
                "success": False,
                "path": file_path,
                "message": "No changes to apply.",
                "changed": False,
                "diff": "",  # empty so _print_diff prints placeholder
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

    except Exception as exc:  # noqa: BLE001
        # ── Explicit error edge case ────────────────────────────────────
        _log_error("Unhandled exception in replace_in_file", exc)
        return {
            "error": str(exc),
            "path": file_path,
            "diff": preview,  # show the exact diff input that blew up
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

        # --- NEW: build diff before writing ---
        diff_lines = difflib.unified_diff(
            [] if not exists else [""],  # empty “old” file
            content.splitlines(keepends=True),  # new file lines
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

    except Exception as exc:  # noqa: BLE001
        _log_error("Unhandled exception in write_to_file", exc)
        return {"error": str(exc), "diff": ""}


def _replace_in_file(
    context: RunContext | None, path: str, diff: str
) -> Dict[str, Any]:
    """Robust replacement engine with explicit edge‑case reporting."""
    file_path = os.path.abspath(path)
    preview = (diff[:400] + "…") if len(diff) > 400 else diff  # for logs / errors
    diff_text = ""
    try:
        if not os.path.exists(file_path):
            return {"error": f"File '{file_path}' does not exist", "diff": preview}

        # ── Parse diff payload (tolerate single quotes) ──────────────────
        try:
            payload = json.loads(diff)
        except json.JSONDecodeError:
            try:
                payload = json.loads(diff.replace("'", '"'))
            except Exception as exc:
                return {
                    "error": "Could not parse diff as JSON.",
                    "reason": str(exc),
                    "received": preview,
                    "diff": preview,
                }
        if not isinstance(payload, dict):
            try:
                payload = ast.literal_eval(diff)
            except Exception as exc:
                return {
                    "error": "Diff is neither valid JSON nor Python literal.",
                    "reason": str(exc),
                    "received": preview,
                    "diff": preview,
                }

        replacements: List[Dict[str, str]] = payload.get("replacements", [])
        if not replacements:
            return {
                "error": "No valid replacements found in diff.",
                "received": preview,
                "diff": preview,
            }

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original
        for rep in replacements:
            modified = modified.replace(rep.get("old_str", ""), rep.get("new_str", ""))

        if modified == original:
            # ── Explicit no‑op edge case ────────────────────────────────
            console.print(
                "[bold yellow]No changes to apply – proposed content is identical.[/bold yellow]"
            )
            return {
                "success": False,
                "path": file_path,
                "message": "No changes to apply.",
                "changed": False,
                "diff": "",  # empty so _print_diff prints placeholder
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

    except Exception as exc:  # noqa: BLE001
        # ── Explicit error edge case ────────────────────────────────────
        _log_error("Unhandled exception in replace_in_file", exc)
        return {
            "error": str(exc),
            "path": file_path,
            "diff": preview,  # show the exact diff input that blew up
        }


# ---------------------------------------------------------------------------
# Agent-tool registration
# ---------------------------------------------------------------------------


def register_file_modifications_tools(agent):  # noqa: C901 – a bit long but clear
    """Attach file-editing tools to *agent* with mandatory diff rendering."""

    # ------------------------------------------------------------------
    # Delete snippet
    # ------------------------------------------------------------------
    @agent.tool
    def delete_snippet_from_file(
        context: RunContext, file_path: str, snippet: str
    ) -> Dict[str, Any]:
        console.log(f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]")
        res = _delete_snippet_from_file(context, file_path, snippet)
        _print_diff(res.get("diff", ""))
        return res

    # ------------------------------------------------------------------
    # Write / create file
    # ------------------------------------------------------------------
    @agent.tool
    def write_to_file(context: RunContext, path: str, content: str) -> Dict[str, Any]:
        console.log(f"✏️ Writing file [bold blue]{path}[/bold blue]")
        res = _write_to_file(context, path, content, overwrite=False)
        _print_diff(res.get("diff", content))
        return res

    # ------------------------------------------------------------------
    # Replace text in file
    # ------------------------------------------------------------------
    @agent.tool
    def replace_in_file(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
        console.log(f"♻️ Replacing text in [bold yellow]{path}[/bold yellow]")
        res = _replace_in_file(context, path, diff)
        _print_diff(res.get("diff", diff))
        return res

    # ------------------------------------------------------------------
    # Delete entire file
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Delete entire file (with full diff)
    # ------------------------------------------------------------------
    @agent.tool
    def delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        console.log(f"🗑️ Deleting file [bold red]{file_path}[/bold red]")
        file_path = os.path.abspath(file_path)
        try:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                res = {"error": f"File '{file_path}' does not exist.", "diff": ""}
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    original = f.read()
                # Diff: original lines → empty file
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
        except Exception as exc:  # noqa: BLE001
            _log_error("Unhandled exception in delete_file", exc)
            res = {"error": str(exc), "diff": ""}
        _print_diff(res.get("diff", ""))
        return res
