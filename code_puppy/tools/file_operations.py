# file_operations.py

import os
from typing import List

from pydantic import BaseModel, conint
from pydantic_ai import RunContext

from code_puppy.tools.common import console
from code_puppy.token_utils import estimate_tokens
from code_puppy.tools.token_check import token_guard

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
from code_puppy.tools.common import should_ignore_path


class ListedFile(BaseModel):
    path: str | None
    type: str | None
    size: int = 0
    full_path: str | None
    depth: int | None


class ListFileOutput(BaseModel):
    files: List[ListedFile]
    error: str | None = None


def _list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> ListFileOutput:
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
        return ListFileOutput(
            files=[ListedFile(path=None, type=None, full_path=None, depth=None)]
        )
    if not os.path.isdir(directory):
        console.print(f"[bold red]Error:[/bold red] '{directory}' is not a directory")
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
        return ListFileOutput(
            files=[ListedFile(path=None, type=None, full_path=None, depth=None)]
        )
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
                ListedFile(
                    **{
                        "path": rel_path,
                        "type": "directory",
                        "size": 0,
                        "full_path": dir_path,
                        "depth": depth,
                    }
                )
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
                results.append(ListedFile(**file_info))
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
        files = sorted([f for f in results if f.type == "file"], key=lambda x: x.path)
        console.print(
            f"\U0001f4c1 [bold blue]{os.path.basename(directory) or directory}[/bold blue]"
        )
    all_items = sorted(results, key=lambda x: x.path)
    parent_dirs_with_content = set()
    for i, item in enumerate(all_items):
        if item.type == "directory" and not item.path:
            continue
        if os.sep in item.path:
            parent_path = os.path.dirname(item.path)
            parent_dirs_with_content.add(parent_path)
        depth = item.path.count(os.sep) + 1 if item.path else 0
        prefix = ""
        for d in range(depth):
            if d == depth - 1:
                prefix += "\u2514\u2500\u2500 "
            else:
                prefix += "    "
        name = os.path.basename(item.path) or item.path
        if item.type == "directory":
            console.print(f"{prefix}\U0001f4c1 [bold blue]{name}/[/bold blue]")
        else:
            icon = get_file_icon(item.path)
            size_str = format_size(item.size)
            console.print(
                f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]"
            )
    else:
        console.print("[yellow]Directory is empty[/yellow]")
    dir_count = sum(1 for item in results if item.type == "directory")
    file_count = sum(1 for item in results if item.type == "file")
    total_size = sum(item.size for item in results if item.type == "file")
    console.print("\n[bold cyan]Summary:[/bold cyan]")
    console.print(
        f"\U0001f4c1 [blue]{dir_count} directories[/blue], \U0001f4c4 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]"
    )
    console.print("[dim]" + "-" * 60 + "[/dim]\n")
    return ListFileOutput(files=results)


class ReadFileOutput(BaseModel):
    content: str | None
    num_tokens: conint(lt=10000)
    error: str | None = None


def _read_file(
    context: RunContext,
    file_path: str,
    start_line: int | None = None,
    num_lines: int | None = None,
) -> ReadFileOutput:
    file_path = os.path.abspath(file_path)

    # Build console message with optional parameters
    console_msg = f"\n[bold white on blue] READ FILE [/bold white on blue] \U0001f4c2 [bold cyan]{file_path}[/bold cyan]"
    if start_line is not None and num_lines is not None:
        console_msg += f" [dim](lines {start_line}-{start_line + num_lines - 1})[/dim]"
    console.print(console_msg)

    console.print("[dim]" + "-" * 60 + "[/dim]")
    if not os.path.exists(file_path):
        error_msg = f"File {file_path} does not exist"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    if not os.path.isfile(file_path):
        error_msg = f"{file_path} is not a file"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if start_line is not None and num_lines is not None:
                # Read only the specified lines
                lines = f.readlines()
                # Adjust for 1-based line numbering
                start_idx = start_line - 1
                end_idx = start_idx + num_lines
                # Ensure indices are within bounds
                start_idx = max(0, start_idx)
                end_idx = min(len(lines), end_idx)
                content = "".join(lines[start_idx:end_idx])
            else:
                # Read the entire file
                content = f.read()

            num_tokens = estimate_tokens(content)
            if num_tokens > 10000:
                raise ValueError(
                    "The file is massive, greater than 10,000 tokens which is dangerous to read entirely. Please read this file in chunks."
                )
            token_guard(num_tokens)
        return ReadFileOutput(content=content, num_tokens=num_tokens)
    except (FileNotFoundError, PermissionError):
        # For backward compatibility with tests, return "FILE NOT FOUND" for these specific errors
        error_msg = "FILE NOT FOUND"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    except Exception as e:
        message = f"An error occurred trying to read the file: {e}"
        return ReadFileOutput(content=message, num_tokens=0, error=message)


class MatchInfo(BaseModel):
    file_path: str | None
    line_number: int | None
    line_content: str | None


class GrepOutput(BaseModel):
    matches: List[MatchInfo]


def _grep(context: RunContext, search_string: str, directory: str = ".") -> GrepOutput:
    matches: List[MatchInfo] = []
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
                            match_info = MatchInfo(
                                **{
                                    "file_path": file_path,
                                    "line_number": line_number,
                                    "line_content": line_content.rstrip("\n\r")[512:],
                                }
                            )
                            matches.append(match_info)
                            # console.print(
                            #     f"[green]Match:[/green] {file_path}:{line_number} - {line_content.strip()}"
                            # ) # Optional: for verbose match logging
                            if len(matches) >= 200:
                                console.print(
                                    "[yellow]Limit of 200 matches reached. Stopping search.[/yellow]"
                                )
                                return GrepOutput(matches=matches)
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

    return GrepOutput(matches=matches)


def list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> ListFileOutput:
    list_files_output = _list_files(context, directory, recursive)
    num_tokens = estimate_tokens(list_files_output.model_dump_json())
    if num_tokens > 10000:
        return ListFileOutput(
            files=[],
            error="Too many files - tokens exceeded. Try listing non-recursively",
        )
    return list_files_output


def read_file(
    context: RunContext,
    file_path: str = "",
    start_line: int | None = None,
    num_lines: int | None = None,
) -> ReadFileOutput:
    return _read_file(context, file_path, start_line, num_lines)


def grep(
    context: RunContext, search_string: str = "", directory: str = "."
) -> GrepOutput:
    return _grep(context, search_string, directory)


def register_file_operations_tools(agent):
    agent.tool(list_files)
    agent.tool(read_file)
    agent.tool(grep)
