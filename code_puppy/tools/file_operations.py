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


def _list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> List[Dict[str, Any]]:
    """Light-weight `list_files` implementation sufficient for unit-tests and agent tooling."""
    console.print(
        f"\n[bold white on blue] LIST FILES [/bold white on blue] \U0001f4c2 [bold cyan]{directory}[/bold cyan]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]")
    directory = os.path.abspath(directory)
    results: List[Dict[str, Any]] = []
    if not os.path.exists(directory) or not os.path.isdir(directory):
        console.print(
            f"[bold red]Directory '{directory}' does not exist or is not a directory[/bold red]"
        )
        return [
            {"error": f"Directory '{directory}' does not exist or is not a directory"}
        ]
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
