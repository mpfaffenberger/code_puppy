# file_modifications.py
import os
import difflib
from code_agent.tools.common import console
from typing import Dict, Any
from code_agent.agent import code_generation_agent
from pydantic_ai import RunContext

@code_generation_agent.tool
def read_file(context: RunContext, file_path: str, start_line: int = 0, end_line: int = None) -> Dict[str, Any]:
    console.log(f"📄 Reading [bold cyan]{file_path}[/bold cyan] (lines {start_line} to {end_line or 'end'})")
    """Read the contents of a file, optionally within a line range.
    
    Args:
        file_path: Path to the file to read
        start_line: Starting line number (0-indexed). Defaults to 0.
        end_line: Ending line number (inclusive, 0-indexed). Defaults to None (read to end).
        
    Returns:
        A dictionary with the file contents and metadata.
    """
    file_path = os.path.abspath(file_path)
    
    if not os.path.exists(file_path):
        return {"error": f"File '{file_path}' does not exist"}
    
    if not os.path.isfile(file_path):
        return {"error": f"'{file_path}' is not a file"}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Handle line range
        if end_line is None:
            end_line = len(lines) - 1
        
        # Ensure valid range
        start_line = max(0, min(start_line, len(lines) - 1))
        end_line = max(start_line, min(end_line, len(lines) - 1))
        
        selected_lines = lines[start_line:end_line + 1]
        content = ''.join(selected_lines)
        
        # Get file extension
        _, ext = os.path.splitext(file_path)
        
        return {
            "content": content,
            "path": file_path,
            "extension": ext.lstrip('.'),
            "total_lines": len(lines),
            "read_lines": end_line - start_line + 1,
            "start_line": start_line,
            "end_line": end_line
        }
    except UnicodeDecodeError:
        # For binary files, return an error
        return {"error": f"Cannot read '{file_path}' as text - it may be a binary file"}
    except Exception as e:
        return {"error": f"Error reading file '{file_path}': {str(e)}"}


@code_generation_agent.tool
def modify_file(context: RunContext, file_path: str, proposed_changes: str) -> Dict[str, Any]:
    """Modify a file with proposed changes, generating a diff and applying the changes.
    
    Args:
        file_path: Path of the file to modify.
        proposed_changes: The new content to replace the existing file content.
        
    Returns:
        A dictionary with the operation result, including success status, message, and diff.
    """
    file_path = os.path.abspath(file_path)
    
    console.print("\n[bold white on yellow] FILE MODIFICATION [/bold white on yellow]")
    console.print(f"[bold yellow]Modifying:[/bold yellow] {file_path}")
    
    try:
        # Check if the file exists
        if not os.path.exists(file_path):
            console.print(f"[bold red]Error:[/bold red] File '{file_path}' does not exist")
            return {"error": f"File '{file_path}' does not exist"}
        
        # Check if it's a file (not a directory)
        if not os.path.isdir(file_path):
            # Read the current file content
            with open(file_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Generate a diff
            diff_lines = list(difflib.unified_diff(
                current_content.splitlines(keepends=True),
                proposed_changes.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
                n=3  # Context lines
            ))
            
            diff_text = ''.join(diff_lines)
            
            # Always display the diff
            console.print("[bold cyan]Changes to be applied:[/bold cyan]")
            
            if diff_text.strip():
                # Format the diff for display
                formatted_diff = ""
                for line in diff_lines:
                    if line.startswith('+') and not line.startswith('+++'):
                        formatted_diff += f"[bold green]{line}[/bold green]"
                    elif line.startswith('-') and not line.startswith('---'):
                        formatted_diff += f"[bold red]{line}[/bold red]"
                    elif line.startswith('@'):
                        formatted_diff += f"[bold cyan]{line}[/bold cyan]"
                    else:
                        formatted_diff += line
                
                console.print(formatted_diff)
            else:
                console.print("[dim]No changes detected - file content is identical[/dim]")
                return {  # Avoid overwriting if no changes actually exist
                    "success": False,
                    "path": file_path,
                    "message": "No changes to apply.",
                    "diff": diff_text,
                    "changed": False
                }
            
            # Write the proposed changes to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(proposed_changes)
            
            return {
                "success": True,
                "path": file_path,
                "message": f"File modified at '{file_path}'",
                "diff": diff_text,
                "changed": True
            }
        else:
            return {
                "success": True,
                "path": file_path,
                "message": f"No changes needed for '{file_path}'",
                "diff": "",
                "changed": False
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
            "message": f"File '{file_path}' deleted successfully."
        }
    except PermissionError:
        return {"error": f"Permission denied to delete '{file_path}'."}
    except FileNotFoundError:
        # This should be caught by the initial check, but just in case
        return {"error": f"File '{file_path}' does not exist."}
    except Exception as e:
        return {"error": f"Error deleting file '{file_path}': {str(e)}"}
