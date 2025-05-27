# file_modifications.py
import os
import difflib
from code_puppy.tools.common import console
from typing import Dict, Any
from code_puppy.agent import code_generation_agent
from pydantic_ai import RunContext




@code_generation_agent.tool
def modify_file(
    context: RunContext,
    file_path: str,
    proposed_changes: str,
    replace_content: str,
    overwrite_entire_file: bool = False,
) -> Dict[str, Any]:
    """Modify a file with proposed changes, generating a diff and applying the changes.

    Args:
        file_path: Path of the file to modify.
        proposed_changes: The new content to replace the targeted section or entire file content.
        replace_content: The content to replace. If blank or not present in the file, the whole file will be replaced ONLY if overwrite_entire_file is True.
        overwrite_entire_file: Explicitly allow replacing the entire file content (default False). You MUST supply True to allow this.

    Returns:
        A dictionary with the operation result, including success status, message, and diff.
    """
    file_path = os.path.abspath(file_path)

    console.print("\n[bold white on yellow] FILE MODIFICATION [/bold white on yellow]")
    console.print(f"[bold yellow]Modifying:[/bold yellow] {file_path}")

    try:
        # Check if the file exists
        if not os.path.exists(file_path):
            console.print(
                f"[bold red]Error:[/bold red] File '{file_path}' does not exist"
            )
            return {"error": f"File '{file_path}' does not exist"}

        if not os.path.isfile(file_path):
            console.print(f"[bold red]Error:[/bold red] '{file_path}' is not a file")
            return {"error": f"'{file_path}' is not a file."}

        with open(file_path, "r", encoding="utf-8") as f:
            current_content = f.read()

        # Decide how to modify
        targeted_replacement = bool(replace_content) and (
            replace_content in current_content
        )
        replace_content_provided = bool(replace_content)

        if targeted_replacement:
            modified_content = current_content.replace(
                replace_content, proposed_changes
            )
            console.print(f"[cyan]Replacing targeted content in '{file_path}'[/cyan]")
        elif not targeted_replacement:
            # Only allow full replacement if explicitly authorized
            if overwrite_entire_file:
                modified_content = proposed_changes
                if replace_content_provided:
                    console.print(
                        "[bold yellow]Target content not found—replacing the entire file by explicit request (overwrite_entire_file=True).[/bold yellow]"
                    )
                else:
                    console.print(
                        "[bold yellow]No target provided—replacing the entire file by explicit request (overwrite_entire_file=True).[/bold yellow]"
                    )
            else:
                if not replace_content_provided:
                    msg = "Refusing to replace the entire file: No replace_content provided and overwrite_entire_file=False."
                else:
                    msg = "Refusing to replace the entire file: Target content not found in file and overwrite_entire_file=False."
                console.print(f"[bold red]Error:[/bold red] {msg}")
                return {
                    "success": False,
                    "path": file_path,
                    "message": msg,
                    "diff": "",
                    "changed": False,
                }

        # Generate a diff for display
        diff_lines = list(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                modified_content.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3,
            )
        )
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
            return {
                "success": False,
                "path": file_path,
                "message": "No changes to apply.",
                "diff": diff_text,
                "changed": False,
            }

        # Write the modified content to the file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)

        return {
            "success": True,
            "path": file_path,
            "message": f"File modified at '{file_path}'",
            "diff": diff_text,
            "changed": True,
        }
    except Exception as e:
        return {"error": f"Error modifying file '{file_path}': {str(e)}"}


@code_generation_agent.tool
def delete_snippet_from_file(
    context: RunContext, file_path: str, snippet: str
) -> Dict[str, Any]:
    console.log(f"🗑️ Deleting snippet from file [bold red]{file_path}[/bold red]")
    """Delete a snippet from a file at the given file path.
    
    Args:
        file_path: Path to the file to delete.
        snippet: The snippet to delete.
        
    Returns:
        A dictionary with status and message about the operation.
    """
    file_path = os.path.abspath(file_path)

    console.print("\n[bold white on red] SNIPPET DELETION [/bold white on red]")
    console.print(f"[bold yellow]From file:[/bold yellow] {file_path}")

    try:
        # Check if the file exists
        if not os.path.exists(file_path):
            console.print(
                f"[bold red]Error:[/bold red] File '{file_path}' does not exist"
            )
            return {"error": f"File '{file_path}' does not exist."}

        # Check if it's a file (not a directory)
        if not os.path.isfile(file_path):
            console.print(f"[bold red]Error:[/bold red] '{file_path}' is not a file")
            return {"error": f"'{file_path}' is not a file. Use rmdir for directories."}

        # Read the file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check if the snippet exists in the file
        if snippet not in content:
            console.print(
                f"[bold red]Error:[/bold red] Snippet not found in file '{file_path}'"
            )
            return {"error": f"Snippet not found in file '{file_path}'."}

        # Remove the snippet from the file content
        modified_content = content.replace(snippet, "")

        # Generate a diff
        diff_lines = list(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                modified_content.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3,  # Context lines
            )
        )

        diff_text = "".join(diff_lines)

        # Display the diff
        console.print("[bold cyan]Changes to be applied:[/bold cyan]")

        if diff_text.strip():
            # Format the diff for display with colorization
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
            return {
                "success": False,
                "path": file_path,
                "message": "No changes needed.",
                "diff": "",
            }

        # Write the modified content back to the file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)

        return {
            "success": True,
            "path": file_path,
            "message": f"Snippet deleted from file '{file_path}'.",
            "diff": diff_text,
        }
    except PermissionError:
        return {"error": f"Permission denied to delete '{file_path}'."}
    except FileNotFoundError:
        # This should be caught by the initial check, but just in case
        return {"error": f"File '{file_path}' does not exist."}
    except Exception as e:
        return {"error": f"Error deleting file '{file_path}': {str(e)}"}


@code_generation_agent.tool
def delete_file(context: RunContext, file_path: str) -> Dict[str, Any]:
    console.log(f"🗑️ Deleting file [bold red]{file_path}[/bold red]")
    """Delete a file at the given file path.
    
    Args:
        file_path: Path to the file to delete.
        
    Returns:
        A dictionary with status and message about the operation.
    """
    file_path = os.path.abspath(file_path)

    try:
        # Check if the file exists
        if not os.path.exists(file_path):
            return {"error": f"File '{file_path}' does not exist."}

        # Check if it's a file (not a directory)
        if not os.path.isfile(file_path):
            return {"error": f"'{file_path}' is not a file. Use rmdir for directories."}

        # Attempt to delete the file
        os.remove(file_path)

        return {
            "success": True,
            "path": file_path,
            "message": f"File '{file_path}' deleted successfully.",
        }
    except PermissionError:
        return {"error": f"Permission denied to delete '{file_path}'."}
    except FileNotFoundError:
        # This should be caught by the initial check, but just in case
        return {"error": f"File '{file_path}' does not exist."}
    except Exception as e:
        return {"error": f"Error deleting file '{file_path}': {str(e)}"}
