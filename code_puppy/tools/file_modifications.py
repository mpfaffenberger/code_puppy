# file_modifications.py
import os
import difflib
import json
from code_puppy.tools.common import console
from typing import Dict, Any, List
from code_puppy.agent import code_generation_agent
from pydantic_ai import RunContext


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
def write_to_file(
    context: RunContext,
    path: str, 
    content: str
) -> Dict[str, Any]:
    """Write content to a file at the specified path.
    
    If the file exists, it will be overwritten with the provided content.
    If the file doesn't exist, it will be created.
    This function will automatically create any directories needed to write the file.
    
    Args:
        path: The path of the file to write to (relative to the current working directory)
        content: The content to write to the file. ALWAYS provide the COMPLETE intended content of the file.
        
    Returns:
        A dictionary with status and message about the operation.
    """
    try:
        # Convert to absolute path if not already
        file_path = os.path.abspath(path)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Display information
        console.print("\n[bold white on blue] FILE WRITE [/bold white on blue]")
        console.print(f"[bold yellow]Writing to:[/bold yellow] {file_path}")
        
        # Check if file exists
        file_exists = os.path.exists(file_path)
        if file_exists:
            console.print(f'[bold red]Refusing to overwrite existing file:[/bold red] {file_path}')
            return {
                'success': False,
                'path': file_path,
                'message': f'Cowardly refusing to overwrite existing file: {file_path}',
                'changed': False,
            }
        
        # Show the content to be written
        trimmed_content = content
        max_preview = 1000
        if len(content) > max_preview:
            trimmed_content = content[:max_preview] + '... [truncated]'
        console.print('[bold magenta]Content to be written:[/bold magenta]')
        console.print(trimmed_content, highlight=False)

        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        action = "updated" if file_exists else "created"
        return {
            "success": True,
            "path": file_path,
            "message": f"File '{file_path}' {action} successfully.",
            "diff": trimmed_content,
            "changed": True,
        }
    
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return {"error": f"Error writing to file '{path}': {str(e)}"}


@code_generation_agent.tool(retries=5)
def replace_in_file(
    context: RunContext,
    path: str, 
    diff: str
) -> Dict[str, Any]:
    """Replace text in a file based on a JSON-formatted replacements object.
    
    Args:
        path: The path of the file to modify
        diff: A JSON string containing replacements, formatted as:
              {"replacements": [{"old_str": "text to find", "new_str": "replacement"}]}
              
    Returns:
        A dictionary with status and message about the operation.
    """
    try:
        # Convert to absolute path if not already
        file_path = os.path.abspath(path)
        
        # Display information
        console.print("\n[bold white on yellow] FILE REPLACEMENTS [/bold white on yellow]")
        console.print(f"[bold yellow]Modifying:[/bold yellow] {file_path}")
        
        # Check if the file exists
        if not os.path.exists(file_path):
            console.print(f"[bold red]Error:[/bold red] File '{file_path}' does not exist")
            return {"error": f"File '{file_path}' does not exist"}
            
        if not os.path.isfile(file_path):
            console.print(f"[bold red]Error:[/bold red] '{file_path}' is not a file")
            return {"error": f"'{file_path}' is not a file."}
        
        # Parse the JSON replacements
        try:
            replacements_data = json.loads(diff)
            replacements = replacements_data.get("replacements", [])
            
            if not replacements:
                console.print("[bold red]Error:[/bold red] No replacements provided in the diff")
                return {"error": "No replacements provided in the diff"}
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error:[/bold red] Invalid JSON in diff: {str(e)}")
            return {"error": f"Invalid JSON in diff: {str(e)}"}
        
        # Read the current file content
        with open(file_path, "r", encoding="utf-8") as f:
            current_content = f.read()
        
        # Apply all replacements
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
            
            # Apply the replacement
            modified_content = modified_content.replace(old_str, new_str)
            applied_replacements.append({"old_str": old_str, "new_str": new_str})
        
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
        
        # Display the diff
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
                "diff": "",
                "changed": False,
            }
        
        # Write the modified content to the file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)
        
        return {
            "success": True,
            "path": file_path,
            "message": f"Applied {len(applied_replacements)} replacements to '{file_path}'",
            "diff": diff_text,
            "changed": True,
            "replacements_applied": len(applied_replacements)
        }
    
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return {"error": f"Error replacing in file '{path}': {str(e)}"}


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
