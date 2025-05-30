# file_operations.py
import os
import fnmatch
from typing import List, Dict, Any
from code_puppy.tools.common import console
from pydantic_ai import RunContext
from code_puppy.agent import code_generation_agent


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
def list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> List[Dict[str, Any]]:
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
    console.print(
        f"📂 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]")

    if not os.path.exists(directory):
        console.print(
            f"[bold red]Error:[/bold red] Directory '{directory}' does not exist"
        )
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
        return [{"error": f"Directory '{directory}' does not exist"}]

    if not os.path.isdir(directory):
        console.print(f"[bold red]Error:[/bold red] '{directory}' is not a directory")
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
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
            results.append(
                {
                    "path": rel_path,
                    "type": "directory",
                    "size": 0,
                    "full_path": dir_path,
                    "depth": depth,
                }
            )

            # Add to folder structure for display
            folder_structure[rel_path] = {
                "path": rel_path,
                "depth": depth,
                "full_path": dir_path,
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
                    "depth": depth,
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
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    # Helper function to get file icon based on extension
    def get_file_icon(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".py", ".pyw"]:
            return "🐍"  # Python
        elif ext in [".js", ".jsx", ".ts", ".tsx"]:
            return "📜"  # JavaScript/TypeScript
        elif ext in [".html", ".htm", ".xml"]:
            return "🌐"  # HTML/XML
        elif ext in [".css", ".scss", ".sass"]:
            return "🎨"  # CSS
        elif ext in [".md", ".markdown", ".rst"]:
            return "📝"  # Markdown/docs
        elif ext in [".json", ".yaml", ".yml", ".toml"]:
            return "⚙️"  # Config files
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]:
            return "🖼️"  # Images
        elif ext in [".mp3", ".wav", ".ogg", ".flac"]:
            return "🎵"  # Audio
        elif ext in [".mp4", ".avi", ".mov", ".webm"]:
            return "🎬"  # Video
        elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
            return "📄"  # Documents
        elif ext in [".zip", ".tar", ".gz", ".rar", ".7z"]:
            return "📦"  # Archives
        elif ext in [".exe", ".dll", ".so", ".dylib"]:
            return "⚡"  # Executables
        else:
            return "📄"  # Default file icon

    # Display tree structure
    if results:
        # Sort directories and files

        files = sorted(
            [f for f in results if f["type"] == "file"], key=lambda x: x["path"]
        )

        # First show directory itself
        console.print(
            f"📁 [bold blue]{os.path.basename(directory) or directory}[/bold blue]"
        )

    # After gathering all results
    # Combine both directories and files, then sort
    all_items = sorted(results, key=lambda x: x["path"])

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
            console.print(
                f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]"
            )
    else:
        console.print("[yellow]Directory is empty[/yellow]")

    # Display summary
    dir_count = sum(1 for item in results if item["type"] == "directory")
    file_count = sum(1 for item in results if item["type"] == "file")
    total_size = sum(item["size"] for item in results if item["type"] == "file")

    console.print("\n[bold cyan]Summary:[/bold cyan]")
    console.print(
        f"📁 [blue]{dir_count} directories[/blue], 📄 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]\n")

    return results


@code_generation_agent.tool
def create_file(
    context: RunContext, file_path: str, content: str = ""
) -> Dict[str, Any]:
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
        return {
            "error": f"File '{file_path}' already exists. Use modify_file to edit it."
        }

    # Create parent directories if they don't exist
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            return {"error": f"Error creating directory '{directory}': {str(e)}"}

    # Create the file
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            console.print("[yellow]Writing to file:[/yellow]")
            console.print(content)
            f.write(content)

        return {
            "success": True,
            "path": file_path,
            "message": f"File created at '{file_path}'",
            "content_length": len(content),
        }
    except Exception as e:
        return {"error": f"Error creating file '{file_path}': {str(e)}"}


@code_generation_agent.tool
def read_file(context: RunContext, file_path: str) -> Dict[str, Any]:
    console.log(f"📄 Reading [bold cyan]{file_path}[/bold cyan]")
    """Read the contents of a file.
    
    Args:
        file_path: Path to the file to read
        
    Returns:
        A dictionary with the file contents and metadata.
    """
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return {"error": f"File '{file_path}' does not exist"}

    if not os.path.isfile(file_path):
        return {"error": f"'{file_path}' is not a file"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Get file extension
        _, ext = os.path.splitext(file_path)

        return {
            "content": content,
            "path": file_path,
            "extension": ext.lstrip("."),
            "total_lines": len(content.splitlines()),
        }
    except UnicodeDecodeError:
        # For binary files, return an error
        return {"error": f"Cannot read '{file_path}' as text - it may be a binary file"}
    except Exception as e:
        return {"error": f"Error reading file '{file_path}': {str(e)}"}


@code_generation_agent.tool
def grep(
    context: RunContext, search_string: str, directory: str = "."
) -> List[Dict[str, Any]]:
    """Recursively search for a string in files starting from a given directory.

    Args:
        search_string: The string to search for.
        directory: The directory to start the search from.

    Returns:
        A list of dictionaries containing file paths and line numbers where matches occur.
    """
    matches = []
    max_matches = 200
    directory = os.path.abspath(directory)

    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if should_ignore_path(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if search_string in line:
                            matches.append({"file_path": file_path, "line_number": line_number})
                            if len(matches) >= max_matches:
                                return matches
            except (FileNotFoundError, PermissionError, UnicodeDecodeError):
                # Skip files that can't be accessed or are not text files
                continue

    return matches
