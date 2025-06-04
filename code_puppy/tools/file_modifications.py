# file_modifications.py
import os
import difflib
import json
from code_puppy.tools.common import console
from typing import Dict, Any, List
from pydantic_ai import RunContext

def register_file_modifications_tools(agent):
    @agent.tool
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

    @agent.tool
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

    @agent.tool(retries=5)
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
            parsed_successfully = False
            replacements: List[Dict[str, str]] = []
            try:
                replacements_data = json.loads(diff)
                replacements = replacements_data.get("replacements", [])
                parsed_successfully = True
            except json.JSONDecodeError:
                # Fallback 1: convert single quotes to double quotes and retry
                try:
                    sanitized = diff.replace("'", '"')
                    replacements_data = json.loads(sanitized)
                    replacements = replacements_data.get("replacements", [])
                    parsed_successfully = True
                except json.JSONDecodeError:
                    # Fallback 2: attempt Python literal eval
                    try:
                        import ast
                        replacements_data = ast.literal_eval(diff)
                        if isinstance(replacements_data, dict):
                            replacements = replacements_data.get("replacements", []) if "replacements" in replacements_data else []
                            # If dict keys look like a single replacement, wrap it
                            if not replacements:
                                # maybe it's already {"old_str": ..., "new_str": ...}
                                if all(k in replacements_data for k in ("old_str", "new_str")):
                                    replacements = [
                                        {
                                            "old_str": replacements_data["old_str"],
                                            "new_str": replacements_data["new_str"],
                                        }
                                    ]
                            parsed_successfully = True
                    except Exception as e2:
                        console.print(
                            f"[bold red]Error:[/bold red] Could not parse diff as JSON or Python literal. Reason: {e2}"
                        )
            if not parsed_successfully or not replacements:
                console.print("[bold red]Error:[/bold red] No valid replacements found in the diff after all parsing attempts")
                return {"error": "No valid replacements found in the diff"}
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
