# file_modifications.py
import os
import difflib
from code_agent.tools.common import console
from typing import Dict, Any, Optional
from code_agent.agent import code_generation_agent
from pydantic_ai import RunContext


@code_generation_agent.tool
def modify_file(
    context: RunContext,
    file_path: str,
    proposed_changes: str,
    target_content: Optional[str] = None,
) -> Dict[str, Any]:
    """Modify a file with proposed changes, generating a diff and applying the changes.

    Args:
        file_path: Path of the file to modify.
        proposed_changes: The new content to replace the targeted section or entire file content.
        target_content: Optional content to replace. If None, the proposed changes will be appended.

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

        # Check if it's a file (not a directory)
        if not os.path.isdir(file_path):
            # Read the current file content
            with open(file_path, "r", encoding="utf-8") as f:
                current_content = f.read()

            # Determine if we're doing a targeted replacement or appending changes
            if target_content is not None:
                # Targeted replacement
                if target_content not in current_content:
                    console.print(
                        f"[bold red]Error:[/bold red] Target content not found in '{file_path}'"
                    )
                    return {"error": f"Target content not found in '{file_path}'"}

                # Replace only the targeted section
                modified_content = current_content.replace(
                    target_content, proposed_changes
                )

                console.print(f"[cyan]Replacing targeted content in '{file_path}'[/cyan]")
            else:
                # Append the changes to the end of the file
                # Check if the current content already ends with a newline
                if current_content and not current_content.endswith("\n"):
                    # If it doesn't end with a newline, add one before appending
                    modified_content = current_content + "\n" + proposed_changes
                else:
                    # If it already ends with a newline, just append
                    modified_content = current_content + proposed_changes
                
                console.print(f"[cyan]Appending content to the end of '{file_path}'[/cyan]")

            # Generate a diff between current and modified content
            diff_lines = list(
                difflib.unified_diff(
                    current_content.splitlines(keepends=True),
                    modified_content.splitlines(keepends=True),
                    fromfile=f"a/{os.path.basename(file_path)}",
                    tofile=f"b/{os.path.basename(file_path)}",
                    n=3,  # Context lines
                )
            )

            diff_text = "".join(diff_lines)

            # Always display the diff
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
                console.print(
                    "[dim]No changes detected - file content is identical[/dim]"
                )
                return {  # Avoid overwriting if no changes actually exist
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
        else:
            return {
                "success": True,
                "path": file_path,
                "message": f"No changes needed for '{file_path}'",
                "diff": "",
                "changed": False,
            }
    except UnicodeDecodeError:
        return {"error": f"Cannot modify '{file_path}' - it may be a binary file"}
    except Exception as e:
        return {"error": f"Error modifying file '{file_path}': {str(e)}"}


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
