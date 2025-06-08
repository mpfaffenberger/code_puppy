# file_operations.py

import os
from typing import Any, Dict, List

from pydantic_ai import RunContext

from code_puppy.tools.common import console

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
from code_puppy.tools.common import should_ignore_path


def _list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> List[Dict[str, Any]]:
    results = []
    directory = os.path.abspath(directory)
    console.print("\n[bold white on blue] DIRECTORY LISTING [/bold white on blue]")
    console.print(
        f"\U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]"
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
        console.print(
            f"\U0001f4c1 [bold blue]{os.path.basename(directory) or directory}[/bold blue]"
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
            console.print(f"{prefix}\U0001f4c1 [bold blue]{name}/[/bold blue]")
        else:
            icon = get_file_icon(item["path"])
            size_str = format_size(item["size"])
            console.print(
                f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]"
            )
    else:
        console.print("[yellow]Directory is empty[/yellow]")
    dir_count = sum(1 for item in results if item["type"] == "directory")
    file_count = sum(1 for item in results if item["type"] == "file")
    total_size = sum(item["size"] for item in results if item["type"] == "file")
    console.print("\n[bold cyan]Summary:[/bold cyan]")
    console.print(
        f"\U0001f4c1 [blue]{dir_count} directories[/blue], \U0001f4c4 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]\n")
    return results


def _read_file(context: RunContext, file_path: str) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)
    console.print(
        f"\n[bold white on blue] READ FILE [/bold white on blue] \U0001f4c2 [bold cyan]{file_path}[/bold cyan]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]")
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
    console.print(
        f"\n[bold white on blue] GREP [/bold white on blue] \U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim]for '{search_string}'[/dim]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]")

    for root, dirs, files in os.walk(directory, topdown=True):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root, d))]

        for f_name in files:
            file_path = os.path.join(root, f_name)

            if should_ignore_path(file_path):
                # console.print(f"[dim]Ignoring: {file_path}[/dim]") # Optional: for debugging ignored files
                continue

            try:
                # console.print(f"\U0001f4c2 [bold cyan]Searching: {file_path}[/bold cyan]") # Optional: for verbose searching log
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line_number, line_content in enumerate(fh, 1):
                        if search_string in line_content:
                            match_info = {
                                "file_path": file_path,
                                "line_number": line_number,
                                "line_content": line_content.strip(),
                            }
                            matches.append(match_info)
                            # console.print(
                            #     f"[green]Match:[/green] {file_path}:{line_number} - {line_content.strip()}"
                            # ) # Optional: for verbose match logging
                            if len(matches) >= 200:
                                console.print(
                                    "[yellow]Limit of 200 matches reached. Stopping search.[/yellow]"
                                )
                                return matches
            except FileNotFoundError:
                console.print(
                    f"[yellow]File not found (possibly a broken symlink): {file_path}[/yellow]"
                )
                continue
            except UnicodeDecodeError:
                console.print(
                    f"[yellow]Cannot decode file (likely binary): {file_path}[/yellow]"
                )
                continue
            except Exception as e:
                console.print(f"[red]Error processing file {file_path}: {e}[/red]")
                continue

    if not matches:
        console.print(
            f"[yellow]No matches found for '{search_string}' in {directory}[/yellow]"
        )
    else:
        console.print(
            f"[green]Found {len(matches)} match(es) for '{search_string}' in {directory}[/green]"
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
        console.print("[bold white on blue] CODE MAP [/bold white on blue]")
        from code_puppy.tools.ts_code_map import make_code_map

        result = make_code_map(directory, ignore_tests=True)
        return result
