# file_modifications.py
import os
import difflib
import json
from code_puppy.tools.common import console
from typing import Dict, Any, List
from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests; *not* registered)
# ---------------------------------------------------------------------------

def delete_snippet_from_file(context: RunContext | None, file_path: str, snippet: str) -> Dict[str, Any]:
    """Remove *snippet* from *file_path* if present, returning a diff summary."""
    file_path = os.path.abspath(file_path)
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return {"error": f"File '{file_path}' does not exist."}
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if snippet not in content:
            return {"error": f"Snippet not found in file '{file_path}'."}
        modified_content = content.replace(snippet, "")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)
        return {"success": True, "path": file_path, "message": "Snippet deleted from file."}
    except PermissionError:
        return {"error": f"Permission denied to modify '{file_path}'."}
    except FileNotFoundError:
        return {"error": f"File '{file_path}' does not exist."}
    except Exception as exc:
        return {"error": str(exc)}


def write_to_file(context: RunContext | None, path: str, content: str) -> Dict[str, Any]:
    file_path = os.path.abspath(path)
    if os.path.exists(file_path):
        return {
            "success": False,
            "path": file_path,
            "message": f"Cowardly refusing to overwrite existing file: {file_path}",
            "changed": False,
        }
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "success": True,
        "path": file_path,
        "message": f"File '{file_path}' created successfully.",
        "changed": True,
    }


def replace_in_file(context: RunContext | None, path: str, diff: str) -> Dict[str, Any]:
    file_path = os.path.abspath(path)
    if not os.path.exists(file_path):
        return {"error": f"File '{file_path}' does not exist"}
    try:
        import json, ast, difflib
        preview = (diff[:200] + '...') if len(diff) > 200 else diff
        try:
            replacements_data = json.loads(diff)
        except json.JSONDecodeError as e1:
            try:
                replacements_data = json.loads(diff.replace("'", '"'))
            except Exception as e2:
                return {
                    "error": "Could not parse diff as JSON.",
                    "reason": str(e2),
                    "received": preview,
                }
        # If still not a dict -> maybe python literal
        if not isinstance(replacements_data, dict):
            try:
                replacements_data = ast.literal_eval(diff)
            except Exception as e3:
                return {
                    "error": "Diff is neither valid JSON nor Python literal.",
                    "reason": str(e3),
                    "received": preview,
                }
        replacements = replacements_data.get("replacements", []) if isinstance(replacements_data, dict) else []
        if not replacements:
            return {
                "error": "No valid replacements found in diff.",
                "received": preview,
            }
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()
        modified = original
        for rep in replacements:
            modified = modified.replace(rep.get("old_str", ""), rep.get("new_str", ""))
        if modified == original:
            return {"success": False, "path": file_path, "message": "No changes to apply.", "changed": False}
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified)
        diff_text = "".join(difflib.unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True)))
        return {"success": True, "path": file_path, "message": "Replacements applied.", "diff": diff_text, "changed": True}
    except Exception as exc:
        return {"error": str(exc)}

# ---------------------------------------------------------------------------

def register_file_modifications_tools(agent):
    # @agent.tool
    def delete_snippet_from_file(context: RunContext, file_path: str, snippet: str) -> Dict[str, Any]:
        console.log(f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]")
        file_path = os.path.abspath(file_path)
        console.print("\n[bold white on red] SNIPPET DELETION [/bold white on red]")
        console.print(f"[bold yellow]From file:[/bold yellow] {file_path}")
        try:
            if not os.path.exists(file_path):
                console.print(f"[bold red]Error:[/bold red] File '{file_path}' does not exist")
                return {"error": f"File '{file_path}' does not exist."}
            if not os.path.isfile(file_path):
                return {"error": f"'{file_path}' is not a file. Use rmdir for directories."}
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if snippet not in content:
                console.print(f"[bold red]Error:[/bold red] Snippet not found in file '{file_path}'")
                return {"error": f"Snippet not found in file '{file_path}'."}
            modified_content = content.replace(snippet, "")
            diff_lines = list(difflib.unified_diff(content.splitlines(keepends=True), modified_content.splitlines(keepends=True), fromfile=f"a/{os.path.basename(file_path)}", tofile=f"b/{os.path.basename(file_path)}", n=3))
            diff_text = "".join(diff_lines)
            console.print("[bold cyan]Changes to be applied:[/bold cyan]")
            if diff_text.strip():
                formatted_diff = ""
                for line in diff_lines:
                    if line.startswith("+") and not line.startswith("+++"):
                        formatted_diff += f"[bold green]{line}[/bold green]"
                    elif line.startswith("-") and not line.startswith("---"):
                        formatted_diff += f"[bold red]{line}[/bold red]"
                    elif line.startswith("@"):
                        formatted_diff += f"[bold cyan]{line}[/bold cyan]"
                    else:
                        formatted_diff += line
                console.print(formatted_diff)
            else:
                console.print("[dim]No changes detected[/dim]")
                return {"success": False, "path": file_path, "message": "No changes needed.", "diff": ""}
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
            return {"success": True, "path": file_path, "message": f"Snippet deleted from file '{file_path}'.", "diff": diff_text}
        except PermissionError:
            return {"error": f"Permission denied to delete '{file_path}'."}
        except FileNotFoundError:
            return {"error": f"File '{file_path}' does not exist."}
        except Exception as e:
            return {"error": f"Error deleting file '{file_path}': {str(e)}"}

    # @agent.tool
    def write_to_file(context: RunContext, path: str, content: str) -> Dict[str, Any]:
        try:
            file_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            console.print("\n[bold white on blue] FILE WRITE [/bold white on blue]")
            console.print(f"[bold yellow]Writing to:[/bold yellow] {file_path}")
            file_exists = os.path.exists(file_path)
            if file_exists:
                console.print(f'[bold red]Refusing to overwrite existing file:[/bold red] {file_path}')
                return {'success': False,'path': file_path,'message': f'Cowardly refusing to overwrite existing file: {file_path}','changed': False,}
            trimmed_content = content
            max_preview = 1000
            if len(content) > max_preview:
                trimmed_content = content[:max_preview] + '... [truncated]'
            console.print('[bold magenta]Content to be written:[/bold magenta]')
            console.print(trimmed_content, highlight=False)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            action = "updated" if file_exists else "created"
            return {"success": True,"path": file_path,"message": f"File '{file_path}' {action} successfully.","diff": trimmed_content,"changed": True,}
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            return {"error": f"Error writing to file '{path}': {str(e)}"}

    # @agent.tool(retries=5)
    def replace_in_file(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
        try:
            file_path = os.path.abspath(path)
            console.print("\n[bold white on yellow] FILE REPLACEMENTS [/bold white on yellow]")
            console.print(f"[bold yellow]Modifying:[/bold yellow] {file_path}")
            if not os.path.exists(file_path):
                console.print(f"[bold red]Error:[/bold red] File '{file_path}' does not exist")
                return {"error": f"File '{file_path}' does not exist"}
            if not os.path.isfile(file_path):
                return {"error": f"'{file_path}' is not a file."}
            # ------------------------------------------------------------------
            # Robust parsing of the diff argument
            # The agent sometimes sends single-quoted or otherwise invalid JSON.
            # Attempt to recover by trying several strategies before giving up.
            # ------------------------------------------------------------------
            preview = (diff[:200] + '...') if len(diff) > 200 else diff
            try:
                replacements_data = json.loads(diff)
            except json.JSONDecodeError as e1:
                try:
                    replacements_data = json.loads(diff.replace("'", '"'))
                except Exception as e2:
                    return {
                        "error": "Could not parse diff as JSON.",
                        "reason": str(e2),
                        "received": preview,
                    }
            # If still not a dict -> maybe python literal
            if not isinstance(replacements_data, dict):
                try:
                    replacements_data = ast.literal_eval(diff)
                except Exception as e3:
                    return {
                        "error": "Diff is neither valid JSON nor Python literal.",
                        "reason": str(e3),
                        "received": preview,
                    }
            replacements = replacements_data.get("replacements", []) if isinstance(replacements_data, dict) else []
            if not replacements:
                return {
                    "error": "No valid replacements found in diff.",
                    "received": preview,
                }
            with open(file_path, "r", encoding="utf-8") as f:
                current_content = f.read()
            modified_content = current_content
            applied_replacements = []
            for i, replacement in enumerate(replacements, 1):
                old_str = replacement.get("old_str", "")
                new_str = replacement.get("new_str", "")
                if not old_str:
                    console.print(f"[bold yellow]Warning:[/bold yellow] Replacement #{i} has empty old_str")
                    continue
                if old_str not in modified_content:
                    console.print(f"[bold red]Error:[/bold red] Text not found in file: {old_str[:50]}...")
                    return {"error": f"Text to replace not found in file (replacement #{i})"}
                modified_content = modified_content.replace(old_str, new_str)
                applied_replacements.append({"old_str": old_str, "new_str": new_str})
            diff_lines = list(difflib.unified_diff(current_content.splitlines(keepends=True), modified_content.splitlines(keepends=True), fromfile=f"a/{os.path.basename(file_path)}", tofile=f"b/{os.path.basename(file_path)}", n=3))
            diff_text = "".join(diff_lines)
            console.print("[bold cyan]Changes to be applied:[/bold cyan]")
            if diff_text.strip():
                formatted_diff = ""
                for line in diff_lines:
                    if line.startswith("+") and not line.startswith("+++"):
                        formatted_diff += f"[bold green]{line}[/bold green]"
                    elif line.startswith("-") and not line.startswith("---"):
                        formatted_diff += f"[bold red]{line}[/bold red]"
                    elif line.startswith("@"):
                        formatted_diff += f"[bold cyan]{line}[/bold cyan]"
                    else:
                        formatted_diff += line
                console.print(formatted_diff)
            else:
                console.print("[dim]No changes detected - file content is identical[/dim]")
                return {"success": False,"path": file_path,"message": "No changes to apply.","diff": "","changed": False,}
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
            return {"success": True,"path": file_path,"message": f"Applied {len(applied_replacements)} replacements to '{file_path}'","diff": diff_text,"changed": True,"replacements_applied": len(applied_replacements)}
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            return {"error": f"Error replacing in file '{path}': {str(e)}"}

    @agent.tool
    def delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        console.log(f"🗑️ Deleting file [bold red]{file_path}[/bold red]")
        file_path = os.path.abspath(file_path)
        try:
            if not os.path.exists(file_path):
                return {"error": f"File '{file_path}' does not exist."}
            if not os.path.isfile(file_path):
                return {"error": f"'{file_path}' is not a file. Use rmdir for directories."}
            os.remove(file_path)
            return {"success": True,"path": file_path,"message": f"File '{file_path}' deleted successfully."}
        except PermissionError:
            return {"error": f"Permission denied to delete '{file_path}'."}
        except FileNotFoundError:
            return {"error": f"File '{file_path}' does not exist."}
        except Exception as e:
            return {"error": f"Error deleting file '{file_path}': {str(e)}"}

    @agent.tool(retries=5)
    def edit_file(context: RunContext, path: str, diff: str) -> Dict[str, Any]:
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
        file_path = os.path.abspath(path)

        # 1. Attempt to parse the incoming `diff` as JSON (robustly, allowing single quotes)
        parsed_payload: Dict[str, Any] | None = None
        try:
            parsed_payload = json.loads(diff)
        except json.JSONDecodeError:
            # Fallback: try to sanitise single quotes
            try:
                parsed_payload = json.loads(diff.replace("'", '"'))
            except Exception:
                parsed_payload = None

        # ------------------------------------------------------------------
        # Case A: JSON payload recognised
        # ------------------------------------------------------------------
        if isinstance(parsed_payload, dict):
            # Delete-snippet mode
            if "delete_snippet" in parsed_payload:
                snippet = parsed_payload["delete_snippet"]
                return delete_snippet_from_file(context, file_path, snippet)

            # Replacement mode
            if "replacements" in parsed_payload:
                # Forward the ORIGINAL diff string (not parsed) so that the existing logic
                # which handles various JSON quirks can run unchanged.
                return replace_in_file(context, file_path, diff)

            # Write / create mode via content field
            if "content" in parsed_payload:
                content = parsed_payload["content"]
                overwrite = bool(parsed_payload.get("overwrite", False))
                file_exists = os.path.exists(file_path)
                if file_exists and not overwrite:
                    return {"success": False, "path": file_path, "message": f"File '{file_path}' exists. Set 'overwrite': true to replace.", "changed": False}
                if file_exists and overwrite:
                    # Overwrite directly
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        return {"success": True, "path": file_path, "message": f"File '{file_path}' overwritten successfully.", "changed": True}
                    except Exception as e:
                        return {"error": f"Error overwriting file '{file_path}': {str(e)}"}
                # File does not exist -> create
                return write_to_file(context, file_path, content)

        # ------------------------------------------------------------------
        # Case B: Not JSON or unrecognised structure.
        # Treat `diff` as raw content for file creation OR as replacement diff.
        # ------------------------------------------------------------------
        if not os.path.exists(file_path):
            # Create new file with provided raw content
            return write_to_file(context, file_path, diff)

        # If file exists, attempt to treat the raw input as a replacement diff spec.
        replacement_result = replace_in_file(context, file_path, diff)
        if replacement_result.get("error"):
            # Fallback: refuse to overwrite blindly
            return {"success": False, "path": file_path, "message": "Unrecognised payload and cannot derive edit instructions.", "changed": False}
        return replacement_result
