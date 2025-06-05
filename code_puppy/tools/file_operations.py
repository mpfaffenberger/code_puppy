# file_operations.py
import os
import fnmatch
from typing import List, Dict, Any
from code_puppy.tools.common import console
from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
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
    """Return True if *path* matches any pattern in IGNORE_PATTERNS."""
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False

def list_files(context: RunContext | None, directory: str = ".", recursive: bool = True) -> List[Dict[str, Any]]:
    """Light-weight `list_files` implementation sufficient for unit-tests and agent tooling."""
    directory = os.path.abspath(directory)
    results: List[Dict[str, Any]] = []
    if not os.path.exists(directory) or not os.path.isdir(directory):
        return [{"error": f"Directory '{directory}' does not exist or is not a directory"}]
    for root, dirs, files in os.walk(directory):
        rel_root = os.path.relpath(root, directory)
        if rel_root == ".":
            rel_root = ""
        for f in files:
            fp = os.path.join(rel_root, f) if rel_root else f
            results.append({"path": fp, "type": "file"})
        if not recursive:
            break
    return results

def read_file(context: RunContext | None, file_path: str) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        return {"error": f"File '{file_path}' does not exist"}
    if not os.path.isfile(file_path):
        return {"error": f"'{file_path}' is not a file"}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "path": file_path, "total_lines": len(content.splitlines())}
    except Exception as exc:
        return {"error": str(exc)}

def grep(context: RunContext | None, search_string: str, directory: str = ".") -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    directory = os.path.abspath(directory)
    for root, dirs, files in os.walk(directory):
        for f in files:
            file_path = os.path.join(root, f)
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    for ln, line in enumerate(fh, 1):
                        if search_string in line:
                            matches.append({"file_path": file_path, "line_number": ln})
                            if len(matches) >= 200:
                                return matches
            except Exception:
                continue
    return matches

def register_file_operations_tools(agent):
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
        for pattern in IGNORE_PATTERNS:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    @agent.tool
    def list_files(context: RunContext, directory: str = ".", recursive: bool = True) -> List[Dict[str, Any]]:
        results = []
        directory = os.path.abspath(directory)
        console.print("\n[bold white on blue] DIRECTORY LISTING [/bold white on blue]")
        console.print(f"\U0001F4C2 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]")
        console.print("[dim]" + "-" * 60 + "[/dim]")
        if not os.path.exists(directory):
            console.print(f"[bold red]Error:[/bold red] Directory '{directory}' does not exist")
            console.print("[dim]" + "-" * 60 + "[/dim]\n")
            return [{"error": f"Directory '{directory}' does not exist"}]
        if not os.path.isdir(directory):
            console.print(f"[bold red]Error:[/bold red] '{directory}' is not a directory")
            console.print("[dim]" + "-" * 60 + "[/dim]\n")
            return [{"error": f"'{directory}' is not a directory"}]
        folder_structure = {}
        file_list = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root, d))]
            rel_path = os.path.relpath(root, directory)
            depth = 0 if rel_path == "." else rel_path.count(os.sep) + 1
            if rel_path == ".":
                rel_path = ""
            if rel_path:
                dir_path = os.path.join(directory, rel_path)
                results.append({"path": rel_path, "type": "directory", "size": 0, "full_path": dir_path, "depth": depth})
                folder_structure[rel_path] = {"path": rel_path, "depth": depth, "full_path": dir_path}
            for file in files:
                file_path = os.path.join(root, file)
                if should_ignore_path(file_path):
                    continue
                rel_file_path = os.path.join(rel_path, file) if rel_path else file
                try:
                    size = os.path.getsize(file_path)
                    file_info = {"path": rel_file_path, "type": "file", "size": size, "full_path": file_path, "depth": depth}
                    results.append(file_info)
                    file_list.append(file_info)
                except (FileNotFoundError, PermissionError):
                    continue
            if not recursive:
                break
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024*1024:
                return f"{size_bytes/1024:.1f} KB"
            elif size_bytes < 1024*1024*1024:
                return f"{size_bytes/(1024*1024):.1f} MB"
            else:
                return f"{size_bytes/(1024*1024*1024):.1f} GB"
        def get_file_icon(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".py", ".pyw"]:
                return "\U0001F40D"
            elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                return "\U0001F4DC"
            elif ext in [".html", ".htm", ".xml"]:
                return "\U0001F310"
            elif ext in [".css", ".scss", ".sass"]:
                return "\U0001F3A8"
            elif ext in [".md", ".markdown", ".rst"]:
                return "\U0001F4DD"
            elif ext in [".json", ".yaml", ".yml", ".toml"]:
                return "\u2699\ufe0f"
            elif ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]:
                return "\U0001F5BC\ufe0f"
            elif ext in [".mp3", ".wav", ".ogg", ".flac"]:
                return "\U0001F3B5"
            elif ext in [".mp4", ".avi", ".mov", ".webm"]:
                return "\U0001F3AC"
            elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
                return "\U0001F4C4"
            elif ext in [".zip", ".tar", ".gz", ".rar", ".7z"]:
                return "\U0001F4E6"
            elif ext in [".exe", ".dll", ".so", ".dylib"]:
                return "\u26A1"
            else:
                return "\U0001F4C4"
        if results:
            files = sorted([f for f in results if f["type"] == "file"], key=lambda x: x["path"])
            console.print(f"\U0001F4C1 [bold blue]{os.path.basename(directory) or directory}[/bold blue]")
        all_items = sorted(results, key=lambda x: x["path"])
        parent_dirs_with_content = set()
        for i, item in enumerate(all_items):
            if item["type"] == "directory" and not item["path"]:
                continue
            if os.sep in item["path"]:
                parent_path = os.path.dirname(item["path"])
                parent_dirs_with_content.add(parent_path)
            depth = item["path"].count(os.sep) + 1 if item["path"] else 0
            prefix = ""
            for d in range(depth):
                if d == depth - 1:
                    prefix += "\u2514\u2500\u2500 "
                else:
                    prefix += "    "
            name = os.path.basename(item["path"]) or item["path"]
            if item["type"] == "directory":
                console.print(f"{prefix}\U0001F4C1 [bold blue]{name}/[/bold blue]")
            else:
                icon = get_file_icon(item["path"])
                size_str = format_size(item["size"])
                console.print(f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]")
        else:
            console.print("[yellow]Directory is empty[/yellow]")
        dir_count = sum(1 for item in results if item["type"] == "directory")
        file_count = sum(1 for item in results if item["type"] == "file")
        total_size = sum(item["size"] for item in results if item["type"] == "file")
        console.print("\n[bold cyan]Summary:[/bold cyan]")
        console.print(f"\U0001F4C1 [blue]{dir_count} directories[/blue], \U0001F4C4 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]")
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
        return results

    @agent.tool
    def read_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return {"error": f"File '{file_path}' does not exist"}
        if not os.path.isfile(file_path):
            return {"error": f"'{file_path}' is not a file"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            _, ext = os.path.splitext(file_path)
            return {"content": content, "path": file_path, "extension": ext.lstrip("."), "total_lines": len(content.splitlines())}
        except UnicodeDecodeError:
            return {"error": f"Cannot read '{file_path}' as text - it may be a binary file"}
        except Exception as e:
            return {"error": f"Error reading file '{file_path}': {str(e)}"}

    @agent.tool
    def grep(context: RunContext, search_string: str, directory: str = ".") -> List[Dict[str, Any]]:
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
                    continue
        return matches
