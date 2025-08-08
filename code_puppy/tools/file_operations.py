# file_operations.py

import os
from typing import Any, Dict, List

from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
from code_puppy.messaging import (
    emit_divider,
    emit_error,
    emit_info,
    emit_success,
    emit_warning,
)
from code_puppy.tools.common import generate_group_id, should_ignore_path


def is_likely_home_directory(directory):
    """Detect if directory is likely a user's home directory or common home subdirectory"""
    abs_dir = os.path.abspath(directory)
    home_dir = os.path.expanduser("~")

    # Exact home directory match
    if abs_dir == home_dir:
        return True

    # Check for common home directory subdirectories
    common_home_subdirs = {
        "Documents",
        "Desktop",
        "Downloads",
        "Pictures",
        "Music",
        "Videos",
        "Movies",
        "Public",
        "Library",
        "Applications",  # Cover macOS/Linux
    }
    if (
        os.path.basename(abs_dir) in common_home_subdirs
        and os.path.dirname(abs_dir) == home_dir
    ):
        return True

    return False


def is_project_directory(directory):
    """Quick heuristic to detect if this looks like a project directory"""
    project_indicators = {
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "CMakeLists.txt",
        ".git",
        "requirements.txt",
        "composer.json",
        "Gemfile",
        "go.mod",
        "Makefile",
        "setup.py",
    }

    try:
        contents = os.listdir(directory)
        return any(indicator in contents for indicator in project_indicators)
    except (OSError, PermissionError):
        return False


def _list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> List[Dict[str, Any]]:
    results = []
    directory = os.path.abspath(directory)

    # Generate group_id for this tool execution
    group_id = generate_group_id("list_files", directory)

    emit_info(
        "\n[bold white on blue] DIRECTORY LISTING [/bold white on blue]",
        message_group=group_id,
    )
    emit_info(
        f"\U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]\n",
        message_group=group_id,
    )
    emit_divider(message_group=group_id)
    if not os.path.exists(directory):
        emit_error(f"Directory '{directory}' does not exist", message_group=group_id)
        emit_divider(message_group=group_id)
        return [{"error": f"Directory '{directory}' does not exist"}]
    if not os.path.isdir(directory):
        emit_error(f"'{directory}' is not a directory", message_group=group_id)
        emit_divider(message_group=group_id)
        return [{"error": f"'{directory}' is not a directory"}]

    # Smart home directory detection - auto-limit recursion for performance
    if is_likely_home_directory(directory) and recursive:
        if not is_project_directory(directory):
            emit_warning(
                "🏠 Detected home directory - limiting to non-recursive listing for performance",
                message_group=group_id,
            )
            emit_info(
                f"💡 To force recursive listing in home directory, use list_files('{directory}', recursive=True) explicitly",
                message_group=group_id,
            )
            recursive = False
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
            results.append(
                {
                    "path": rel_path,
                    "type": "directory",
                    "size": 0,
                    "full_path": dir_path,
                    "depth": depth,
                }
            )
            folder_structure[rel_path] = {
                "path": rel_path,
                "depth": depth,
                "full_path": dir_path,
            }
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
                continue
        if not recursive:
            break

    def format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def get_file_icon(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".py", ".pyw"]:
            return "\U0001f40d"
        elif ext in [".js", ".jsx", ".ts", ".tsx"]:
            return "\U0001f4dc"
        elif ext in [".html", ".htm", ".xml"]:
            return "\U0001f310"
        elif ext in [".css", ".scss", ".sass"]:
            return "\U0001f3a8"
        elif ext in [".md", ".markdown", ".rst"]:
            return "\U0001f4dd"
        elif ext in [".json", ".yaml", ".yml", ".toml"]:
            return "\u2699\ufe0f"
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]:
            return "\U0001f5bc\ufe0f"
        elif ext in [".mp3", ".wav", ".ogg", ".flac"]:
            return "\U0001f3b5"
        elif ext in [".mp4", ".avi", ".mov", ".webm"]:
            return "\U0001f3ac"
        elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
            return "\U0001f4c4"
        elif ext in [".zip", ".tar", ".gz", ".rar", ".7z"]:
            return "\U0001f4e6"
        elif ext in [".exe", ".dll", ".so", ".dylib"]:
            return "\u26a1"
        else:
            return "\U0001f4c4"

    if results:
        files = sorted(
            [f for f in results if f["type"] == "file"], key=lambda x: x["path"]
        )
        emit_info(
            f"\U0001f4c1 [bold blue]{os.path.basename(directory) or directory}[/bold blue]",
            message_group=group_id,
        )
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
            emit_info(
                f"{prefix}\U0001f4c1 [bold blue]{name}/[/bold blue]",
                message_group=group_id,
            )
        else:
            icon = get_file_icon(item["path"])
            size_str = format_size(item["size"])
            emit_info(
                f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]",
                message_group=group_id,
            )
    else:
        emit_warning("Directory is empty", message_group=group_id)
    dir_count = sum(1 for item in results if item["type"] == "directory")
    file_count = sum(1 for item in results if item["type"] == "file")
    total_size = sum(item["size"] for item in results if item["type"] == "file")
    emit_info("\n[bold cyan]Summary:[/bold cyan]", message_group=group_id)
    emit_info(
        f"\U0001f4c1 [blue]{dir_count} directories[/blue], \U0001f4c4 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]",
        message_group=group_id,
    )
    emit_divider(message_group=group_id)
    return results


def _read_file(context: RunContext, file_path: str) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)

    # Generate group_id for this tool execution
    group_id = generate_group_id("read_file", file_path)

    emit_info(
        f"\n[bold white on blue] READ FILE [/bold white on blue] \U0001f4c2 [bold cyan]{file_path}[/bold cyan]",
        message_group=group_id,
    )
    emit_divider(message_group=group_id)
    if not os.path.exists(file_path):
        return {"error": f"File '{file_path}' does not exist"}
    if not os.path.isfile(file_path):
        return {"error": f"'{file_path}' is not a file"}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "content": content,
            "path": file_path,
            "total_lines": len(content.splitlines()),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _grep(
    context: RunContext, search_string: str, directory: str = "."
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    directory = os.path.abspath(directory)

    # Generate group_id for this tool execution
    group_id = generate_group_id("grep", f"{directory}_{search_string}")

    emit_info(
        f"\n[bold white on blue] GREP [/bold white on blue] \U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim]for '{search_string}'[/dim]",
        message_group=group_id,
    )
    emit_divider(message_group=group_id)

    for root, dirs, files in os.walk(directory, topdown=True):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root, d))]

        for f_name in files:
            file_path = os.path.join(root, f_name)

            if should_ignore_path(file_path):
                # emit_system_message(f"[dim]Ignoring: {file_path}[/dim]") # Optional: for debugging ignored files
                continue

            try:
                # emit_system_message(f"\U0001f4c2 [bold cyan]Searching: {file_path}[/bold cyan]") # Optional: for verbose searching log
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line_number, line_content in enumerate(fh, 1):
                        if search_string in line_content:
                            match_info = {
                                "file_path": file_path,
                                "line_number": line_number,
                                "line_content": line_content.strip(),
                            }
                            matches.append(match_info)
                            # emit_system_message(
                            #     f"[green]Match:[/green] {file_path}:{line_number} - {line_content.strip()}"
                            # ) # Optional: for verbose match logging
                            if len(matches) >= 200:
                                emit_warning(
                                    "Limit of 200 matches reached. Stopping search.",
                                    message_group=group_id,
                                )
                                return matches
            except FileNotFoundError:
                emit_warning(
                    f"File not found (possibly a broken symlink): {file_path}",
                    message_group=group_id,
                )
                continue
            except UnicodeDecodeError:
                emit_warning(
                    f"Cannot decode file (likely binary): {file_path}",
                    message_group=group_id,
                )
                continue
            except Exception as e:
                emit_error(
                    f"Error processing file {file_path}: {e}", message_group=group_id
                )
                continue

    if not matches:
        emit_warning(
            f"No matches found for '{search_string}' in {directory}",
            message_group=group_id,
        )
    else:
        emit_success(
            f"Found {len(matches)} match(es) for '{search_string}' in {directory}",
            message_group=group_id,
        )

    return matches


# Exported top-level functions for direct import by tests and other code


def list_files(context, directory=".", recursive=True):
    return _list_files(context, directory, recursive)


def read_file(context, file_path):
    return _read_file(context, file_path)


def grep(context, search_string, directory="."):
    return _grep(context, search_string, directory)


def register_file_operations_tools(agent):
    @agent.tool
    def list_files(
        context: RunContext, directory: str = ".", recursive: bool = True
    ) -> List[Dict[str, Any]]:
        return _list_files(context, directory, recursive)

    @agent.tool
    def read_file(context: RunContext, file_path: str) -> Dict[str, Any]:
        return _read_file(context, file_path)

    @agent.tool
    def grep(
        context: RunContext, search_string: str, directory: str = "."
    ) -> List[Dict[str, Any]]:
        return _grep(context, search_string, directory)

    @agent.tool
    def code_map(context: RunContext, directory: str = ".") -> str:
        """Generate a code map for the specified directory.
           This will have a list of all function / class names and nested structure
        Args:
            context: The context object.
            directory: The directory to generate the code map for.

        Returns:
            A string containing the code map.
        """
        # Generate group_id for this tool execution
        group_id = generate_group_id("code_map", directory)

        emit_info(
            "[bold white on blue] CODE MAP [/bold white on blue]",
            message_group=group_id,
        )
        from code_puppy.tools.ts_code_map import make_code_map

        result = make_code_map(directory, ignore_tests=True)
        return result
