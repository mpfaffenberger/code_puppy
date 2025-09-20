# file_operations.py

import os
import tempfile
from typing import List

from pydantic import BaseModel, conint
from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
from code_puppy.messaging import (
    emit_divider,
    emit_error,
    emit_info,
    emit_success,
    emit_system_message,
    emit_warning,
)
from code_puppy.tools.common import generate_group_id


# Pydantic models for tool return types
class ListedFile(BaseModel):
    path: str | None
    type: str | None
    size: int = 0
    full_path: str | None
    depth: int | None


class ListFileOutput(BaseModel):
    content: str
    error: str | None = None


class ReadFileOutput(BaseModel):
    content: str | None
    num_tokens: conint(lt=10000)
    error: str | None = None


class MatchInfo(BaseModel):
    file_path: str | None
    line_number: int | None
    line_content: str | None


class GrepOutput(BaseModel):
    matches: List[MatchInfo]


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
) -> ListFileOutput:
    import subprocess
    import shutil
    import sys

    results = []
    directory = os.path.abspath(directory)

    # Build string representation
    output_lines = []

    directory_listing_header = (
        "\n[bold white on blue] DIRECTORY LISTING [/bold white on blue]"
    )
    output_lines.append(directory_listing_header)

    directory_info = f"\U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim](recursive={recursive})[/dim]\n"
    output_lines.append(directory_info)

    divider = "[dim]" + "─" * 100 + "\n" + "[/dim]"
    output_lines.append(divider)

    if not os.path.exists(directory):
        error_msg = (
            f"[red bold]Error:[/red bold] Directory '{directory}' does not exist"
        )
        output_lines.append(error_msg)

        output_lines.append(divider)
        return ListFileOutput(content="\n".join(output_lines))
    if not os.path.isdir(directory):
        error_msg = f"[red bold]Error:[/red bold] '{directory}' is not a directory"
        output_lines.append(error_msg)

        output_lines.append(divider)
        return ListFileOutput(content="\n".join(output_lines))

    # Smart home directory detection - auto-limit recursion for performance
    # But allow recursion in tests (when context=None) or when explicitly requested
    if context is not None and is_likely_home_directory(directory) and recursive:
        if not is_project_directory(directory):
            warning_msg = "[yellow bold]Warning:[/yellow bold] 🏠 Detected home directory - limiting to non-recursive listing for performance"
            output_lines.append(warning_msg)

            info_msg = f"[dim]💡 To force recursive listing in home directory, use list_files('{directory}', recursive=True) explicitly[/dim]"
            output_lines.append(info_msg)
            recursive = False

    # Create a temporary ignore file with our ignore patterns
    ignore_file = None
    try:
        # Find ripgrep executable - first check system PATH, then virtual environment
        rg_path = shutil.which("rg")
        if not rg_path:
            # Try to find it in the virtual environment
            # Use sys.executable to determine the Python environment path
            python_dir = os.path.dirname(sys.executable)
            # Check both 'bin' (Unix) and 'Scripts' (Windows) directories
            for rg_dir in ["bin", "Scripts"]:
                venv_rg_path = os.path.join(python_dir, "rg")
                if os.path.exists(venv_rg_path):
                    rg_path = venv_rg_path
                    break
                # Also check with .exe extension for Windows
                venv_rg_exe_path = os.path.join(python_dir, "rg.exe")
                if os.path.exists(venv_rg_exe_path):
                    rg_path = venv_rg_exe_path
                    break

        if not rg_path:
            error_msg = "[red bold]Error:[/red bold] ripgrep (rg) not found. Please install ripgrep to use this tool."
            output_lines.append(error_msg)
            return ListFileOutput(content="\n".join(output_lines))

        # Build command for ripgrep --files
        cmd = [rg_path, "--files"]

        # For non-recursive mode, we'll limit depth after getting results
        if not recursive:
            cmd.extend(["--max-depth", "1"])

        # Add ignore patterns to the command via a temporary file
        from code_puppy.tools.common import IGNORE_PATTERNS

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ignore") as f:
            ignore_file = f.name
            for pattern in IGNORE_PATTERNS:
                f.write(f"{pattern}\n")

        cmd.extend(["--ignore-file", ignore_file])
        cmd.append(directory)

        # Run ripgrep to get file listing
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Process the output lines
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Create ListedFile objects with metadata
        for full_path in files:
            if not full_path:  # Skip empty lines
                continue

            # Skip if file doesn't exist (though it should)
            if not os.path.exists(full_path):
                continue

            # Extract relative path from the full path
            if full_path.startswith(directory):
                file_path = full_path[len(directory):].lstrip(os.sep)
            else:
                file_path = full_path

            # For non-recursive mode, skip files in subdirectories
            # Only check the relative path, not the full path
            if not recursive and os.sep in file_path:
                continue

            # Check if path is a file or directory
            if os.path.isfile(full_path):
                entry_type = "file"
                size = os.path.getsize(full_path)
            elif os.path.isdir(full_path):
                entry_type = "directory"
                size = 0
            else:
                # Skip if it's neither a file nor directory
                continue

            try:
                # Get stats for the entry
                stat_info = os.stat(full_path)
                actual_size = stat_info.st_size

                # For files, we use the actual size; for directories, we keep size=0
                if entry_type == "file":
                    size = actual_size

                # Calculate depth based on the relative path
                depth = file_path.count(os.sep)

                # Add directory entries if needed for files
                if entry_type == "file":
                    dir_path = os.path.dirname(file_path)
                    if dir_path:
                        # Add directory path components if they don't exist
                        path_parts = dir_path.split(os.sep)
                        for i in range(len(path_parts)):
                            partial_path = os.sep.join(path_parts[: i + 1])
                            # Check if we already added this directory
                            if not any(
                                f.path == partial_path and f.type == "directory"
                                for f in results
                            ):
                                results.append(
                                    ListedFile(
                                        path=partial_path,
                                        type="directory",
                                        size=0,
                                        full_path=os.path.join(directory, partial_path),
                                        depth=partial_path.count(os.sep),
                                    )
                                )

                # Add the entry (file or directory)
                results.append(
                    ListedFile(
                        path=file_path,
                        type=entry_type,
                        size=size,
                        full_path=full_path,
                        depth=depth,
                    )
                )
            except (FileNotFoundError, PermissionError, OSError):
                # Skip files we can't access
                continue

        # In non-recursive mode, we also need to explicitly list directories in the target directory
        # ripgrep's --files option only returns files, not directories
        if not recursive:
            try:
                entries = os.listdir(directory)
                for entry in entries:
                    full_entry_path = os.path.join(directory, entry)
                    # Skip if it doesn't exist or if it's a file (since files are already listed by ripgrep)
                    if not os.path.exists(full_entry_path) or os.path.isfile(full_entry_path):
                        continue
                    
                    # For non-recursive mode, only include directories that are directly in the target directory
                    if os.path.isdir(full_entry_path):
                        # Create a ListedFile for the directory
                        results.append(
                            ListedFile(
                                path=entry,
                                type="directory",
                                size=0,
                                full_path=full_entry_path,
                                depth=0,
                            )
                        )
            except (FileNotFoundError, PermissionError, OSError):
                # Skip directories we can't access
                pass
    except subprocess.TimeoutExpired:
        error_msg = (
            "[red bold]Error:[/red bold] List files command timed out after 30 seconds"
        )
        output_lines.append(error_msg)
        return ListFileOutput(content="\n".join(output_lines))
    except Exception as e:
        error_msg = (
            f"[red bold]Error:[/red bold] Error during list files operation: {e}"
        )
        output_lines.append(error_msg)
        return ListFileOutput(content="\n".join(output_lines))
    finally:
        # Clean up the temporary ignore file
        if ignore_file and os.path.exists(ignore_file):
            os.unlink(ignore_file)

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

    # Count items in results
    dir_count = sum(1 for item in results if item.type == "directory")
    file_count = sum(1 for item in results if item.type == "file")
    total_size = sum(item.size for item in results if item.type == "file")
    


    # Build the directory header section
    dir_name = os.path.basename(directory) or directory
    dir_header = f"\U0001f4c1 [bold blue]{dir_name}[/bold blue]"
    output_lines.append(dir_header)

    # Sort all items by path for consistent display
    all_items = sorted(results, key=lambda x: x.path)

    # Build file and directory tree representation
    parent_dirs_with_content = set()
    for item in all_items:
        # Skip root directory entries with no path
        if item.type == "directory" and not item.path:
            continue

        # Track parent directories that contain files/dirs
        if os.sep in item.path:
            parent_path = os.path.dirname(item.path)
            parent_dirs_with_content.add(parent_path)

        # Calculate indentation depth based on path separators
        depth = item.path.count(os.sep) + 1 if item.path else 0
        prefix = ""
        for d in range(depth):
            if d == depth - 1:
                prefix += "\u2514\u2500\u2500 "
            else:
                prefix += "    "

        # Get the display name (basename) of the item
        name = os.path.basename(item.path) or item.path

        # Add directory or file line with appropriate formatting
        if item.type == "directory":
            dir_line = f"{prefix}\U0001f4c1 [bold blue]{name}/[/bold blue]"
            output_lines.append(dir_line)
        else:
            icon = get_file_icon(item.path)
            size_str = format_size(item.size)
            file_line = f"{prefix}{icon} [green]{name}[/green] [dim]({size_str})[/dim]"
            output_lines.append(file_line)

    # Add summary information
    summary_header = "\n[bold cyan]Summary:[/bold cyan]"
    output_lines.append(summary_header)

    summary_line = f"\U0001f4c1 [blue]{dir_count} directories[/blue], \U0001f4c4 [green]{file_count} files[/green] [dim]({format_size(total_size)} total)[/dim]"
    output_lines.append(summary_line)

    final_divider = "[dim]" + "─" * 100 + "\n" + "[/dim]"
    output_lines.append(final_divider)

    # Return the content string
    return ListFileOutput(content="\n".join(output_lines))


def _read_file(
    context: RunContext,
    file_path: str,
    start_line: int | None = None,
    num_lines: int | None = None,
) -> ReadFileOutput:
    file_path = os.path.abspath(file_path)

    # Generate group_id for this tool execution
    group_id = generate_group_id("read_file", file_path)

    # Build console message with optional parameters
    console_msg = f"\n[bold white on blue] READ FILE [/bold white on blue] \U0001f4c2 [bold cyan]{file_path}[/bold cyan]"
    if start_line is not None and num_lines is not None:
        console_msg += f" [dim](lines {start_line}-{start_line + num_lines - 1})[/dim]"
    emit_info(console_msg, message_group=group_id)

    emit_divider(message_group=group_id)
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

            # Simple approximation: ~4 characters per token
            num_tokens = len(content) // 4
            if num_tokens > 10000:
                return ReadFileOutput(
                    content=None,
                    error="The file is massive, greater than 10,000 tokens which is dangerous to read entirely. Please read this file in chunks.",
                    num_tokens=0,
                )
        return ReadFileOutput(content=content, num_tokens=num_tokens)
    except (FileNotFoundError, PermissionError):
        # For backward compatibility with tests, return "FILE NOT FOUND" for these specific errors
        error_msg = "FILE NOT FOUND"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    except Exception as e:
        message = f"An error occurred trying to read the file: {e}"
        return ReadFileOutput(content=message, num_tokens=0, error=message)


def _grep(context: RunContext, search_string: str, directory: str = ".") -> GrepOutput:
    import subprocess
    import json
    import os
    import shutil
    import sys

    directory = os.path.abspath(directory)
    matches: List[MatchInfo] = []

    # Generate group_id for this tool execution
    group_id = generate_group_id("grep", f"{directory}_{search_string}")

    emit_info(
        f"\n[bold white on blue] GREP [/bold white on blue] \U0001f4c2 [bold cyan]{directory}[/bold cyan] [dim]for '{search_string}'[/dim]",
        message_group=group_id,
    )
    emit_divider(message_group=group_id)

    # Create a temporary ignore file with our ignore patterns
    ignore_file = None
    try:
        # Use ripgrep to search for the string
        # Use absolute path to ensure it works from any directory
        # --json for structured output
        # --max-count 50 to limit results
        # --max-filesize 5M to avoid huge files (increased from 1M)
        # --type=all to search across all recognized text file types
        # --ignore-file to obey our ignore list

        # Find ripgrep executable - first check system PATH, then virtual environment
        rg_path = shutil.which("rg")
        if not rg_path:
            # Try to find it in the virtual environment
            # Use sys.executable to determine the Python environment path
            python_dir = os.path.dirname(sys.executable)
            # Check both 'bin' (Unix) and 'Scripts' (Windows) directories
            for rg_dir in ["bin", "Scripts"]:
                venv_rg_path = os.path.join(python_dir, "rg")
                if os.path.exists(venv_rg_path):
                    rg_path = venv_rg_path
                    break
                # Also check with .exe extension for Windows
                venv_rg_exe_path = os.path.join(python_dir, "rg.exe")
                if os.path.exists(venv_rg_exe_path):
                    rg_path = venv_rg_exe_path
                    break

        if not rg_path:
            emit_error(
                "ripgrep (rg) not found. Please install ripgrep to use this tool.",
                message_group=group_id,
            )
            return GrepOutput(matches=[])

        cmd = [
            rg_path,
            "--json",
            "--max-count",
            "50",
            "--max-filesize",
            "5M",
            "--type=all",
        ]

        # Add ignore patterns to the command via a temporary file
        from code_puppy.tools.common import IGNORE_PATTERNS

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ignore") as f:
            ignore_file = f.name
            for pattern in IGNORE_PATTERNS:
                f.write(f"{pattern}\n")

        cmd.extend(["--ignore-file", ignore_file])
        cmd.extend([search_string, directory])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Parse the JSON output from ripgrep
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                match_data = json.loads(line)
                # Only process match events, not context or summary
                if match_data.get("type") == "match":
                    data = match_data.get("data", {})
                    path_data = data.get("path", {})
                    file_path = (
                        path_data.get("text", "") if path_data.get("text") else ""
                    )
                    line_number = data.get("line_number", None)
                    line_content = (
                        data.get("lines", {}).get("text", "")
                        if data.get("lines", {}).get("text")
                        else ""
                    )
                    if len(line_content.strip()) > 512:
                        line_content = line_content.strip()[0:512]
                    if file_path and line_number:
                        match_info = MatchInfo(
                            file_path=file_path,
                            line_number=line_number,
                            line_content=line_content.strip(),
                        )
                        matches.append(match_info)
                        # Limit to 50 matches total, same as original implementation
                        if len(matches) >= 50:
                            break
                        emit_system_message(
                            f"[green]Match:[/green] {file_path}:{line_number} - {line_content.strip()}",
                            message_group=group_id,
                        )
            except json.JSONDecodeError:
                # Skip lines that aren't valid JSON
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

    except subprocess.TimeoutExpired:
        emit_error("Grep command timed out after 30 seconds", message_group=group_id)
    except FileNotFoundError:
        emit_error(
            "ripgrep (rg) not found. Please install ripgrep to use this tool.",
            message_group=group_id,
        )
    except Exception as e:
        emit_error(f"Error during grep operation: {e}", message_group=group_id)
    finally:
        # Clean up the temporary ignore file
        if ignore_file and os.path.exists(ignore_file):
            os.unlink(ignore_file)

    return GrepOutput(matches=matches)


def register_list_files(agent):
    """Register only the list_files tool."""
    from code_puppy.config import get_allow_recursion

    @agent.tool
    def list_files(
        context: RunContext, directory: str = ".", recursive: bool = True
    ) -> ListFileOutput:
        """List files and directories with intelligent filtering and safety features.

        This function will only allow recursive listing when the allow_recursion
        configuration is set to true via the /set allow_recursion=true command.

        This tool provides comprehensive directory listing with smart home directory
        detection, project-aware recursion, and token-safe output. It automatically
        ignores common build artifacts, cache directories, and other noise while
        providing rich file metadata and visual formatting.

        Args:
            context (RunContext): The PydanticAI runtime context for the agent.
            directory (str, optional): Path to the directory to list. Can be relative
                or absolute. Defaults to "." (current directory).
            recursive (bool, optional): Whether to recursively list subdirectories.
                Automatically disabled for home directories unless they contain
                project indicators. Also requires allow_recursion=true in config.
                Defaults to True.

        Returns:
            ListFileOutput: A response containing:
                - content (str): String representation of the directory listing
                - error (str | None): Error message if listing failed

        Examples:
            >>> # List current directory
            >>> result = list_files(ctx)
            >>> print(result.content)

            >>> # List specific directory non-recursively
            >>> result = list_files(ctx, "/path/to/project", recursive=False)
            >>> print(result.content)

            >>> # Handle potential errors
            >>> result = list_files(ctx, "/nonexistent/path")
            >>> if result.error:
            ...     print(f"Error: {result.error}")

        Best Practices:
            - Always use this before reading/modifying files
            - Use non-recursive for quick directory overviews
            - Check for errors in the response
            - Combine with grep to find specific file patterns
        """
        warning = None
        if recursive and not get_allow_recursion():
            warning = "Recursion disabled globally for list_files - returning non-recursive results"
            recursive = False
        result = _list_files(context, directory, recursive)

        # Emit the content directly to ensure it's displayed to the user
        emit_info(
            result.content, message_group=generate_group_id("list_files", directory)
        )
        if warning:
            result.error = warning
        if (len(result.content)) > 200000:
            result.content = result.content[0:200000]
            result.error = "Results truncated. This is a massive directory tree, recommend non-recursive calls to list_files"
        return result


def register_read_file(agent):
    """Register only the read_file tool."""

    @agent.tool
    def read_file(
        context: RunContext,
        file_path: str = "",
        start_line: int | None = None,
        num_lines: int | None = None,
    ) -> ReadFileOutput:
        """Read file contents with optional line-range selection and token safety.

        This tool provides safe file reading with automatic token counting and
        optional line-range selection for handling large files efficiently.
        It protects against reading excessively large files that could overwhelm
        the agent's context window.

        Args:
            context (RunContext): The PydanticAI runtime context for the agent.
            file_path (str): Path to the file to read. Can be relative or absolute.
                Cannot be empty.
            start_line (int | None, optional): Starting line number for partial reads
                (1-based indexing). If specified, num_lines must also be provided.
                Defaults to None (read entire file).
            num_lines (int | None, optional): Number of lines to read starting from
                start_line. Must be specified if start_line is provided.
                Defaults to None (read to end of file).

        Returns:
            ReadFileOutput: A structured response containing:
                - content (str | None): The file contents or error message
                - num_tokens (int): Estimated token count (constrained to < 10,000)
                - error (str | None): Error message if reading failed

        Examples:
            >>> # Read entire file
            >>> result = read_file(ctx, "example.py")
            >>> print(f"Read {result.num_tokens} tokens")
            >>> print(result.content)

            >>> # Read specific line range
            >>> result = read_file(ctx, "large_file.py", start_line=10, num_lines=20)
            >>> print("Lines 10-29:", result.content)

            >>> # Handle errors
            >>> result = read_file(ctx, "missing.txt")
            >>> if result.error:
            ...     print(f"Error: {result.error}")

        Best Practices:
            - Always check for errors before using content
            - Use line ranges for large files to avoid token limits
            - Monitor num_tokens to stay within context limits
            - Combine with list_files to find files first
        """
        return _read_file(context, file_path, start_line, num_lines)


def register_grep(agent):
    """Register only the grep tool."""

    @agent.tool
    def grep(
        context: RunContext, search_string: str = "", directory: str = "."
    ) -> GrepOutput:
        """Recursively search for text patterns across files using ripgrep (rg).

        This tool leverages the high-performance ripgrep utility for fast text
        searching across directory trees. It searches across all recognized text file
        types (Python, JavaScript, HTML, CSS, Markdown, etc.) while automatically
        filtering binary files and limiting results for performance.

        The search_string parameter supports ripgrep's full flag syntax, allowing
        advanced searches including regex patterns, case-insensitive matching,
        and other ripgrep features.

        Args:
            context (RunContext): The PydanticAI runtime context for the agent.
            search_string (str): The text pattern to search for. Can include ripgrep
                flags like '--ignore-case', '-w' (word boundaries), etc.
                Cannot be empty.
            directory (str, optional): Root directory to start the recursive search.
                Can be relative or absolute. Defaults to "." (current directory).

        Returns:
            GrepOutput: A structured response containing:
                - matches (List[MatchInfo]): List of matches found, where each
                  MatchInfo contains:
                  - file_path (str | None): Absolute path to the file containing the match
                  - line_number (int | None): Line number where match was found (1-based)
                  - line_content (str | None): Full line content containing the match

        Examples:
            >>> # Simple text search
            >>> result = grep(ctx, "def my_function")
            >>> for match in result.matches:
            ...     print(f"{match.file_path}:{match.line_number}: {match.line_content}")

            >>> # Case-insensitive search
            >>> result = grep(ctx, "--ignore-case TODO", "/path/to/project/src")
            >>> print(f"Found {len(result.matches)} TODO items")

            >>> # Word boundary search (regex)
            >>> result = grep(ctx, "-w \\w+State\\b")
            >>> files_with_state = {match.file_path for match in result.matches}

        Best Practices:
            - Use specific search terms to avoid too many results
            - Leverage ripgrep's powerful regex and flag features for advanced searches
            - ripgrep is much faster than naive implementations
            - Results are capped at 50 matches for performance
        """
        return _grep(context, search_string, directory)
