"""Agent tools for file operations, planning, and development workflow, now with smarter modifications!"""

import os
import subprocess
import difflib
import time
import fnmatch
from typing import List, Dict, Any
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Rich imports for console output
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

# Import the agent from agent.py
from code_agent.agent import code_generation_agent

# Import RunContext from pydantic_ai
from pydantic_ai import RunContext

# Initialize console for rich output
console = Console()

# Constants for file operations
IGNORE_PATTERNS = [
    "**/node_modules/**",
    "**/.git/**",
    "**/__pycache__/**",
    "**/.DS_Store",
    "**/.env",
    "**/.venv/**",
    "**/venv/**",
    "**/.idea/**",
    "**/.vscode/**",
    "**/dist/**",
    "**/build/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/*.so",
    "**/*.dll",
    "**/*.exe",
]

def should_ignore_path(path: str) -> bool:
    """Check if the path should be ignored based on patterns."""
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False

@code_generation_agent.tool
def list_files(context: RunContext, directory: str = ".", recursive: bool = True) -> List[Dict[str, Any]]:
    """Recursively list all files in a directory, ignoring common patterns.
    
    Args:
        directory: The directory to list files from. Defaults to current directory.
        recursive: Whether to search recursively. Defaults to True.
        
    Returns:
        A list of dictionaries with file information including path, size, and type.
    """
    results = []
    directory = os.path.abspath(directory)
    
    # Display directory listing header
    console.print("\n[bold white on blue] DIRECTORY LISTING [/bold white on blue]")
    console.print(f"📂 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]")
    console.print("[dim]"+ "-" * 60 + "[/dim]")
    
    if not os.path.exists(directory):
        console.print(f"[bold red]Error:[/bold red] Directory '{directory}' does not exist")
        console.print("[dim]"+ "-" * 60 + "[/dim]\n")
        return [{"error": f"Directory '{directory}' does not exist"}]
    
    if not os.path.isdir(directory):
        console.print(f"[bold red]Error:[/bold red] '{directory}' is not a directory")
        console.print("[dim]"+ "-" * 60 + "[/dim]\n")
        return [{"error": f"'{directory}' is not a directory"}]
    
    # Track folders and files at each level for tree display
    folder_structure = {}
    file_list = []
    
    for root, dirs, files in os.walk(directory):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root, d))]
        
        rel_path = os.path.relpath(root, directory)
        depth = 0 if rel_path == "." else rel_path.count(os.sep) + 1
        
        if rel_path == ".":
            rel_path = ""
        
        # Add directory entry to results
        if rel_path:
            dir_path = os.path.join(directory, rel_path)
            results.append({
                "path": rel_path,
                "type": "directory",
                "size": 0,
                "full_path": dir_path,
                "depth": depth
            })
            
            # Add to folder structure for display
            folder_structure[rel_path] = {
                "path": rel_path,
                "depth": depth,
                "full_path": dir_path
            }
        
        # Add file entries
        for file in files:
            file_path = os.path.join(root, file)
            if should_ignore_path(file_path):
                continue
                
            rel_file_path = os.path.join(rel_path, file) if rel_path else file
            
            try:
                size = os.path.getsize(file_path)
                file_info = {
                    "path": rel_file_path,
                    "type": "file",
                    "size": size,
                    "full_path": file_path,
                    "depth": depth
                }
                results.append(file_info)
                file_list.append(file_info)
            except (FileNotFoundError, PermissionError):
                # Skip files we can't access
                continue
        
        if not recursive:
            break
    
    # Helper function to format file size
    def format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"
    
    # Helper function to get file icon based on extension
    def get_file_icon(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".py", ".pyw"]:
            return "🐍" # Python
        elif ext in [".js", ".jsx", ".ts", ".tsx"]:
            return "📜" # JavaScript/TypeScript
        elif ext in [".html", ".htm", ".xml"]:
            return "🌐" # HTML/XML
        elif ext in [".css", ".scss", ".sass"]:
            return "🎨" # CSS
        elif ext in [".md", ".markdown", ".rst"]:
            return "📝" # Markdown/docs
        elif ext in [".json", ".yaml", ".yml", ".toml"]:
            return "⚙️" # Config files
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]:
            return "🖼️" # Images
        elif ext in [".mp3", ".wav", ".ogg", ".flac"]:
            return "🎵" # Audio
        elif ext in [".mp4", ".avi", ".mov", ".webm"]:
            return "🎬" # Video
        elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
            return "📄" # Documents
        elif ext in [".zip", ".tar", ".gz", ".rar", ".7z"]:
            return "📦" # Archives
        elif ext in [".exe", ".dll", ".so", ".dylib"]:
            return "⚡" # Executables
        else:
            return "📄" # Default file icon
    
    # Display tree structure
    if results:
        # Sort directories and files
        directories = sorted([d for d in results if d["type"] == "directory"], 
                            key=lambda x: x["path"])
        files = sorted([f for f in results if f["type"] == "file"], 
                      key=lambda x: x["path"])
        
        # First show directory itself
        console.print(f"📁 [bold blue]{os.path.basename(directory) or directory}[/bold blue]")
        
        # Display directories first, then files in a tree structure
        all_items = directories + files
        current_depth = 0
        parent_dirs_with_content = set()
        
        for i, item in enumerate(all_items):
            # Skip root directory
            if item["type"] == "directory" and not item["path"]:
                continue
            
            # Get parent directories to track which ones have content
            if os.sep in item["path"]:
                parent_path = os.path.dirname(item["path"])
                parent_dirs_with_content.add(parent_path)
            
            # Calculate depth from path
            depth = item["path"].count(os.sep) + 1 if item["path"] else 0
            
            # Calculate prefix for tree structure
            prefix = ""  
            for d in range(depth):
                if d == depth - 1:
                    prefix += "└── " 
                else:
                    prefix += "    "
            
            # Display item with appropriate icon and color
            name = os.path.basename(item["path"]) or item["path"]
            
            if item["type"] == "directory":
                console.print(f"{prefix}📁 [bold blue]{name}/[/bold blue]")
            else:  # file
                icon = get_file_icon(item["path"])
                size_str = format_size(item["size"])
                console.print(f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]")
    else:
        console.print("[yellow]Directory is empty[/yellow]")
    
    # Display summary
    dir_count = sum(1 for item in results if item["type"] == "directory")
    file_count = sum(1 for item in results if item["type"] == "file")
    total_size = sum(item["size"] for item in results if item["type"] == "file")
    
    console.print("\n[bold cyan]Summary:[/bold cyan]")
    console.print(f"📁 [blue]{dir_count} directories[/blue], 📄 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]")
    console.print("[dim]"+ "-" * 60 + "[/dim]\n")
    
    return results

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
def create_file(context: RunContext, file_path: str, content: str = "") -> Dict[str, Any]:
    console.log(f"✨ Creating new file [bold green]{file_path}[/bold green]")
    """Create a new file with optional content.
    
    Args:
        file_path: Path where the file should be created
        content: Optional content to write to the file
        
    Returns:
        A dictionary with the result of the operation
    """
    file_path = os.path.abspath(file_path)
    
    # Check if file already exists
    if os.path.exists(file_path):
        return {"error": f"File '{file_path}' already exists. Use modify_file to edit it."}
    
    # Create parent directories if they don't exist
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            return {"error": f"Error creating directory '{directory}': {str(e)}"}
    
    # Create the file
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "path": file_path,
            "message": f"File created at '{file_path}'",
            "content_length": len(content)
        }
    except Exception as e:
        return {"error": f"Error creating file '{file_path}': {str(e)}"}

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


@code_generation_agent.tool
def run_shell_command(context: RunContext, command: str, cwd: str = None, timeout: int = 60) -> Dict[str, Any]:
    """Run a shell command and return its output.
    
    Args:
        command: The shell command to execute.
        cwd: The current working directory to run the command in. Defaults to None (current directory).
        timeout: Maximum time in seconds to wait for the command to complete. Defaults to 60.
        
    Returns:
        A dictionary with the command result, including stdout, stderr, and exit code.
    """
    if not command or not command.strip():
        console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return {"error": "Command cannot be empty"}
    
    # Display command execution in a visually distinct way
    console.print("\n[bold white on blue] SHELL COMMAND [/bold white on blue]")
    console.print(f"[bold green]$ {command}[/bold green]")
    if cwd:
        console.print(f"[dim]Working directory: {cwd}[/dim]")
    console.print("[dim]"+ "-" * 60 + "[/dim]")
    
    try:
        start_time = time.time()
        
        # Execute the command with timeout
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
            execution_time = time.time() - start_time
            
            # Display command output
            if stdout.strip():
                console.print("[bold white]STDOUT:[/bold white]")
                console.print(Syntax(stdout.strip(), "bash", theme="monokai", background_color="default"))
            
            if stderr.strip():
                console.print("[bold yellow]STDERR:[/bold yellow]")
                console.print(Syntax(stderr.strip(), "bash", theme="monokai", background_color="default", style="yellow"))
            
            # Show execution summary
            if exit_code == 0:
                console.print(f"[bold green]✓ Command completed successfully[/bold green] [dim](took {execution_time:.2f}s)[/dim]")
            else:
                console.print(f"[bold red]✗ Command failed with exit code {exit_code}[/bold red] [dim](took {execution_time:.2f}s)[/dim]")
            
            console.print("[dim]"+ "-" * 60 + "[/dim]\n")
            
            return {
                "success": exit_code == 0,
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": execution_time,
                "timeout": False
            }
        except subprocess.TimeoutExpired:
            # Kill the process if it times out
            process.kill()
            stdout, stderr = process.communicate()
            execution_time = time.time() - start_time
            
            # Display timeout information
            if stdout.strip():
                console.print("[bold white]STDOUT (incomplete due to timeout):[/bold white]")
                console.print(Syntax(stdout.strip(), "bash", theme="monokai", background_color="default"))
            
            if stderr.strip():
                console.print("[bold yellow]STDERR:[/bold yellow]")
                console.print(Syntax(stderr.strip(), "bash", theme="monokai", background_color="default", style="yellow"))
            
            console.print(f"[bold red]⏱ Command timed out after {timeout} seconds[/bold red] [dim](ran for {execution_time:.2f}s)[/dim]")
            console.print("[dim]"+ "-" * 60 + "[/dim]\n")
            
            return {
                "success": False,
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": None,  # No exit code since the process was killed
                "execution_time": execution_time,
                "timeout": True,
                "error": f"Command timed out after {timeout} seconds"
            }
    except Exception as e:
        # Display error information
        console.print(f"[bold red]Error executing command:[/bold red] {str(e)}")
        console.print("[dim]"+ "-" * 60 + "[/dim]\n")
        
        return {
            "success": False,
            "command": command,
            "error": f"Error executing command: {str(e)}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout": False
        }

@code_generation_agent.tool
def share_your_reasoning(context: RunContext, reasoning: str, next_steps: str = None) -> Dict[str, Any]:
    """Share the agent's current reasoning and planned next steps with the user.
    
    Args:
        reasoning: The agent's current reasoning or thought process.
        next_steps: Optional description of what the agent plans to do next.
        
    Returns:
        A dictionary with the reasoning information.
    """
    console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")
    
    # Display the reasoning with markdown formatting
    console.print("[bold cyan]Current reasoning:[/bold cyan]")
    console.print(Markdown(reasoning))
    
    # Display next steps if provided
    if next_steps and next_steps.strip():
        console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
        console.print(Markdown(next_steps))
    
    console.print("[dim]"+ "-" * 60 + "[/dim]\n")
    
    return {
        "success": True,
        "reasoning": reasoning,
        "next_steps": next_steps
    }

@code_generation_agent.tool
def web_search(context: RunContext, query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Perform a web search and return a list of results with titles and URLs.

    Args:
        query: The search query.
        num_results: Number of results to return. Defaults to 5.

    Returns:
        A list of dictionaries, each containing 'title' and 'url' for a search result.
    """
    search_url = "https://www.google.com/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    params = {"q": query}

    response = requests.get(search_url, headers=headers, params=params)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for g in soup.find_all('div', class_='tF2Cxc')[:num_results]:
        title_element = g.find('h3')
        link_element = g.find('a')
        if title_element and link_element:
            title = title_element.get_text()
            url = link_element['href']
            results.append({"title": title, "url": url})

    return results
