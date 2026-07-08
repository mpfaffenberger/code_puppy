# file_operations.py

import os
import re
import shutil
import subprocess
import tempfile
from typing import List

from pydantic import BaseModel, conint
from pydantic_ai import RunContext

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------
from code_puppy.messaging import (  # New structured messaging types
    FileContentMessage,
    FileEntry,
    FileListingMessage,
    GrepMatch,
    GrepResultMessage,
    get_message_bus,
)
from code_puppy.tools.common import resolve_path
from code_puppy.tools import fs_access


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
    error: str | None = None


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


def would_match_directory(pattern: str, directory: str) -> bool:
    """Check if a glob pattern would match the given directory path.

    This is used to avoid adding ignore patterns that would inadvertently
    exclude the directory we're actually trying to search in.

    Args:
        pattern: A glob pattern like '**/tmp/**' or 'node_modules'
        directory: The directory path to check against

    Returns:
        True if the pattern would match the directory, False otherwise
    """
    import fnmatch

    # Normalize the directory path
    abs_dir = os.path.abspath(directory)
    dir_name = os.path.basename(abs_dir)

    # Strip leading/trailing wildcards and slashes for simpler matching
    clean_pattern = pattern.strip("*").strip("/")

    # Check if the directory name matches the pattern
    if fnmatch.fnmatch(dir_name, clean_pattern):
        return True

    # Check if the full path contains the pattern
    if fnmatch.fnmatch(abs_dir, pattern):
        return True

    # Check if any part of the path matches
    path_parts = abs_dir.split(os.sep)
    for part in path_parts:
        if fnmatch.fnmatch(part, clean_pattern):
            return True

    return False


def _list_entries_via_backend(directory: str, recursive: bool) -> List["ListedFile"]:
    """Build ``ListedFile`` results from the installed filesystem backend.

    Composes the listing from ``fs_access.walk`` / ``list_dir`` so it reflects
    the backend's single coherent filesystem (the same source ``read_file`` and
    ``grep`` see), rather than the local ripgrep path used when no backend is
    installed. Honors the same ignore rules as the local path.
    """
    from code_puppy.tools.common import should_ignore_dir_path, should_ignore_path

    results: List[ListedFile] = []

    def _rel(full: str) -> str:
        if full.startswith(directory):
            return full[len(directory) :].lstrip(os.sep)
        return full

    if recursive:
        for full, entry in fs_access.walk(
            directory,
            skip_dir=should_ignore_dir_path,
            skip_file=should_ignore_path,
        ):
            rel = _rel(full)
            if not rel:
                continue
            results.append(
                ListedFile(
                    path=rel,
                    type="directory" if entry.is_dir else "file",
                    size=0 if entry.is_dir else entry.size,
                    full_path=full,
                    depth=rel.count(os.sep),
                )
            )
    else:
        for entry in sorted(fs_access.list_dir(directory), key=lambda e: e.name):
            # Match the local non-recursive path: hide dot-directories.
            if entry.is_dir and entry.name.startswith("."):
                continue
            results.append(
                ListedFile(
                    path=entry.name,
                    type="directory" if entry.is_dir else "file",
                    size=0 if entry.is_dir else entry.size,
                    full_path=os.path.join(directory, entry.name),
                    depth=0,
                )
            )
    return results


def _list_files(
    context: RunContext, directory: str = ".", recursive: bool = True
) -> ListFileOutput:
    import sys

    results = []
    directory = resolve_path(directory)

    # Plain text output for LLM consumption
    output_lines = []
    output_lines.append(f"DIRECTORY LISTING: {directory} (recursive={recursive})")

    if not fs_access.exists(directory):
        error_msg = f"Error: Directory '{directory}' does not exist"
        return ListFileOutput(content=error_msg, error=error_msg)
    if not fs_access.is_dir(directory):
        error_msg = f"Error: '{directory}' is not a directory"
        return ListFileOutput(content=error_msg, error=error_msg)

    # Smart home directory detection - auto-limit recursion for performance
    # But allow recursion in tests (when context=None) or when explicitly requested
    if context is not None and is_likely_home_directory(directory) and recursive:
        if not is_project_directory(directory):
            output_lines.append(
                "Warning: Detected home directory - limiting to non-recursive listing for performance"
            )
            recursive = False

    # When a filesystem backend is installed it owns the whole FS surface, so
    # we compose the listing from it (fs_access.walk / list_dir) instead of
    # shelling out to the local ripgrep -- keeping every operation coherent.
    from code_puppy.tools.io_backends import get_filesystem_backend

    _use_backend = get_filesystem_backend() is not None
    if _use_backend:
        try:
            results = _list_entries_via_backend(directory, recursive)
        except Exception as e:
            # A backend raising (TOCTOU race, host error) must degrade to a
            # tool error, never crash the tool -- parity with the local path.
            error_msg = f"Error: Error during list files operation: {e}"
            return ListFileOutput(content=error_msg, error=error_msg)

    # Create a temporary ignore file with our ignore patterns (local rg path)
    ignore_file = None
    try:
        # Find ripgrep executable - first check system PATH, then virtual environment
        rg_path = shutil.which("rg")
        if not rg_path:
            # Try to find it in the virtual environment
            # Use sys.executable to determine the Python environment path
            python_dir = os.path.dirname(sys.executable)
            # python_dir is already bin/ (Unix) or Scripts/ (Windows)
            for name in ["rg", "rg.exe"]:
                candidate = os.path.join(python_dir, name)
                if os.path.exists(candidate):
                    rg_path = candidate
                    break

        if not rg_path and recursive and not _use_backend:
            # Only need ripgrep for recursive listings
            error_msg = "Error: ripgrep (rg) not found. Please install ripgrep to use this tool."
            return ListFileOutput(content=error_msg, error=error_msg)

        # Only use ripgrep for recursive listings
        if recursive and not _use_backend:
            # Build command for ripgrep --files
            cmd = [rg_path, "--files"]

            # Add ignore patterns to the command via a temporary file
            from code_puppy.tools.common import (
                DIR_IGNORE_PATTERNS,
            )

            f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ignore")
            ignore_file = f.name
            try:
                for pattern in DIR_IGNORE_PATTERNS:
                    # Skip patterns that would match the search directory itself
                    # For example, if searching in /tmp/test-dir, skip **/tmp/**
                    if would_match_directory(pattern, directory):
                        continue
                    f.write(f"{pattern}\n")
            finally:
                f.close()

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
                    file_path = full_path[len(directory) :].lstrip(os.sep)
                else:
                    file_path = full_path

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
                                            full_path=os.path.join(
                                                directory, partial_path
                                            ),
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

        # In non-recursive mode, we also need to explicitly list immediate entries
        # ripgrep's --files option only returns files; we add directories and files ourselves
        if not recursive and not _use_backend:
            try:
                entries = os.listdir(directory)
                for entry in sorted(entries):
                    full_entry_path = os.path.join(directory, entry)
                    if not os.path.exists(full_entry_path):
                        continue

                    if os.path.isdir(full_entry_path):
                        # In non-recursive mode, only skip obviously system/hidden directories
                        # Don't use the full should_ignore_dir_path which is too aggressive
                        if entry.startswith("."):
                            continue
                        results.append(
                            ListedFile(
                                path=entry,
                                type="directory",
                                size=0,
                                full_path=full_entry_path,
                                depth=0,
                            )
                        )
                    elif os.path.isfile(full_entry_path):
                        # Include top-level files (including binaries)
                        try:
                            size = os.path.getsize(full_entry_path)
                        except OSError:
                            size = 0
                        results.append(
                            ListedFile(
                                path=entry,
                                type="file",
                                size=size,
                                full_path=full_entry_path,
                                depth=0,
                            )
                        )
            except (FileNotFoundError, PermissionError, OSError):
                # Skip entries we can't access
                pass
    except subprocess.TimeoutExpired:
        error_msg = "Error: List files command timed out after 30 seconds"
        return ListFileOutput(content=error_msg, error=error_msg)
    except Exception as e:
        error_msg = f"Error: Error during list files operation: {e}"
        return ListFileOutput(content=error_msg, error=error_msg)
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

    # Build structured FileEntry objects for the UI
    file_entries = []

    def _sort_key(item):
        """Sort by path components to keep children grouped under parents.

        Splitting on os.sep ensures 'src/foo' always sorts right after 'src'
        rather than letting 'src-tauri' (with '-' < '/') slip in between.
        Directories sort before files at the same level.
        """
        parts = item.path.split(os.sep)
        return (parts, item.type != "directory")

    for item in sorted(results, key=_sort_key):
        if item.type == "directory" and not item.path:
            continue
        file_entries.append(
            FileEntry(
                path=item.path,
                type="dir" if item.type == "directory" else "file",
                size=item.size,
                depth=item.depth or 0,
            )
        )

    # Emit structured message for the UI
    file_listing_msg = FileListingMessage(
        directory=directory,
        files=file_entries,
        recursive=recursive,
        total_size=total_size,
        dir_count=dir_count,
        file_count=file_count,
    )
    get_message_bus().emit(file_listing_msg)

    # Build plain text output for LLM consumption
    for item in sorted(results, key=_sort_key):
        if item.type == "directory" and not item.path:
            continue
        name = os.path.basename(item.path) or item.path
        indent = "  " * (item.depth or 0)
        if item.type == "directory":
            output_lines.append(f"{indent}{name}/")
        else:
            size_str = format_size(item.size)
            output_lines.append(f"{indent}{name} ({size_str})")

    # Add summary
    output_lines.append(
        f"\nSummary: {dir_count} directories, {file_count} files ({format_size(total_size)} total)"
    )

    return ListFileOutput(content="\n".join(output_lines))


def _read_file(
    context: RunContext,
    file_path: str,
    start_line: int | None = None,
    num_lines: int | None = None,
) -> ReadFileOutput:
    file_path = resolve_path(file_path)

    # When a filesystem backend is installed (e.g. an editor host), read
    # through it so we see unsaved buffers and the host's view of the file.
    # The backend owns existence/permission semantics, so we skip the local
    # disk checks on this path.
    from code_puppy.tools.io_backends import get_filesystem_backend

    backend = get_filesystem_backend()
    if backend is not None:
        if start_line is not None and start_line < 1:
            error_msg = "start_line must be >= 1 (1-based indexing)"
            return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
        if num_lines is not None and num_lines < 1:
            error_msg = "num_lines must be >= 1"
            return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
        # Push the slice down to the host (ACP fs/read supports line+limit) so a
        # chunked read doesn't drag the whole file across the wire. Matches the
        # local path: only slice when BOTH bounds are given.
        want_slice = start_line is not None and num_lines is not None
        try:
            if want_slice:
                raw = backend.read_text_file(
                    file_path, line=start_line, limit=num_lines
                )
            else:
                raw = backend.read_text_file(file_path)
        except FileNotFoundError:
            error_msg = f"File {file_path} does not exist"
            return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
        except Exception as e:
            message = f"An error occurred trying to read the file: {e}"
            return ReadFileOutput(content=message, num_tokens=0, error=message)
        return _finalize_read_output(file_path, raw, start_line, num_lines)

    if not os.path.exists(file_path):
        error_msg = f"File {file_path} does not exist"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    if not os.path.isfile(file_path):
        error_msg = f"{file_path} is not a file"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    try:
        # Use errors="surrogateescape" to handle files with invalid UTF-8 sequences
        # This is common on Windows when files contain emojis or were created by
        # applications that don't properly encode Unicode
        with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
            if start_line is not None and start_line < 1:
                error_msg = "start_line must be >= 1 (1-based indexing)"
                return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
            if num_lines is not None and num_lines < 1:
                error_msg = "num_lines must be >= 1"
                return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
            if start_line is not None and num_lines is not None:
                # Read only the specified lines efficiently using itertools.islice
                # to avoid loading the entire file into memory
                import itertools

                start_idx = start_line - 1
                selected_lines = list(
                    itertools.islice(f, start_idx, start_idx + num_lines)
                )
                content = "".join(selected_lines)
            else:
                # Read the entire file
                content = f.read()

        return _finalize_read_output(file_path, content, start_line, num_lines)
    except FileNotFoundError:
        error_msg = "FILE NOT FOUND"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    except PermissionError:
        error_msg = "PERMISSION DENIED"
        return ReadFileOutput(content=error_msg, num_tokens=0, error=error_msg)
    except Exception as e:
        message = f"An error occurred trying to read the file: {e}"
        return ReadFileOutput(content=message, num_tokens=0, error=message)


def _finalize_read_output(
    file_path: str,
    content: str,
    start_line: int | None,
    num_lines: int | None,
) -> ReadFileOutput:
    """Sanitize/guard/emit for a just-read file body and build the output.

    Shared by the local (disk) and backend (host) read paths so both apply the
    identical surrogate sanitization, 10k-token guard, and UI emission.
    """
    # Sanitize the content to remove any surrogate characters that could cause
    # issues when the content is later serialized or displayed.
    try:
        content = content.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        content = "".join(
            char if ord(char) < 0xD800 or ord(char) > 0xDFFF else "\ufffd"
            for char in content
        )

    # Simple approximation: ~4 characters per token
    num_tokens = len(content) // 4
    if num_tokens > 10000:
        return ReadFileOutput(
            content=None,
            error="The file is massive, greater than 10,000 tokens which is dangerous to read entirely. Please read this file in chunks.",
            num_tokens=0,
        )

    total_lines = content.count("\n") + (
        1 if content and not content.endswith("\n") else 0
    )
    emit_start_line = start_line if start_line is not None and start_line >= 1 else None
    emit_num_lines = num_lines if num_lines is not None and num_lines >= 1 else None
    get_message_bus().emit(
        FileContentMessage(
            path=file_path,
            content=content,
            start_line=emit_start_line,
            num_lines=emit_num_lines,
            total_lines=total_lines,
            num_tokens=num_tokens,
        )
    )
    return ReadFileOutput(content=content, num_tokens=num_tokens)


def _sanitize_string(text: str) -> str:
    """Sanitize a string to remove invalid Unicode surrogates.

    This handles encoding issues common on Windows with copy-paste operations.
    """
    if not text:
        return text
    try:
        # Try encoding - if it works, string is clean
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        pass

    try:
        # Encode allowing surrogates, then decode replacing them
        return text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Last resort: filter out surrogate characters
        return "".join(
            char if ord(char) < 0xD800 or ord(char) > 0xDFFF else "\ufffd"
            for char in text
        )


# Ripgrep flags that change the output away from per-match JSON events.
# _grep parses `--json` "match" events; with any of these flags ripgrep
# emits none, so the tool would silently report zero matches. Reject them
# loudly instead.
_INCOMPATIBLE_RG_FLAGS = frozenset(
    {
        "-l",
        "--files-with-matches",
        "--files-without-match",
        "-c",
        "--count",
        "--count-matches",
        "--files",
        "-q",
        "--quiet",
        "--json",
        "--type-list",
        "-h",
        "--help",
        "-V",
        "--version",
    }
)


def _strip_quote_pair(token: str) -> str:
    """Remove one matching pair of surrounding quotes, if present.

    Only a single, balanced pair is removed so quote characters that are
    part of the pattern itself survive intact.
    """
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _tokenize_flag_string(search_string: str) -> list[str] | None:
    """Tokenize a flag-mode grep string (non-POSIX). ``None`` on unmatched quote.

    Shared by the local ripgrep arg builder and the backend matcher so both
    interpret ``-i --type py 'class Limits'`` identically. Non-POSIX so regex
    escapes and Windows paths (``\\b``, ``C:\\Users``) are never mangled; one
    surrounding quote pair is stripped per token.
    """
    import shlex

    lexer = shlex.shlex(search_string, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return [_strip_quote_pair(part) for part in lexer]
    except ValueError:
        return None


def _build_grep_args(search_string: str) -> tuple[list[str], str | None]:
    """Convert ``search_string`` into ripgrep arguments, identically on all OSes.

    Two explicit modes:

    - Plain pattern (default): when the string does NOT start with ``-``,
      the entire string is a single regex passed verbatim via ``-e``.
      Spaces, pipes, quotes, and backslashes are preserved exactly on
      every platform -- no tokenization happens at all.
    - Flag mode: when the string starts with ``-``, it is tokenized so
      ripgrep flags can be supplied, e.g. ``-i --type py 'class Limits'``.
      Tokenization is non-POSIX on every platform so regex escapes and
      Windows paths (``\\b``, ``C:\\Users``) are never mangled; quotes
      group words and one surrounding pair is stripped per token.

    Returns ``(args, error)``. ``error`` is set when an unsupported
    output-format flag is requested.
    """
    if not search_string.startswith("-"):
        return ["-e", search_string], None

    tokens = _tokenize_flag_string(search_string)
    if tokens is None:
        # Unmatched quote: refuse to guess at shell-like structure and
        # treat the whole string as a literal pattern.
        return ["-e", search_string], None

    for token in tokens:
        flag = token.split("=", 1)[0]
        if flag in _INCOMPATIBLE_RG_FLAGS:
            return [], (
                f"ripgrep flag '{flag}' is not supported: this tool parses "
                "per-match JSON output, and that flag changes the output "
                "format (it would silently return zero matches). Use a plain "
                "pattern, or content flags like -i, -w, -F, --type instead."
            )
    return tokens, None


# ripgrep --type name -> file extensions, for the backend grep path. Covers the
# common types; unknown types raise a clear error rather than silently matching
# nothing (ripgrep itself owns the full list on the local path).
_RG_TYPE_EXTS: dict[str, set[str]] = {
    "py": {".py", ".pyi", ".pyw"},
    "js": {".js", ".jsx", ".mjs", ".cjs", ".vue"},
    "ts": {".ts", ".tsx", ".mts", ".cts"},
    "rust": {".rs"},
    "go": {".go"},
    "java": {".java"},
    "kotlin": {".kt", ".kts"},
    "c": {".c", ".h"},
    "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"},
    "cs": {".cs"},
    "rb": {".rb"},
    "php": {".php"},
    "swift": {".swift"},
    "html": {".html", ".htm"},
    "css": {".css", ".scss", ".sass", ".less"},
    "json": {".json"},
    "yaml": {".yaml", ".yml"},
    "toml": {".toml"},
    "md": {".md", ".markdown"},
    "sh": {".sh", ".bash", ".zsh"},
    "txt": {".txt"},
    "xml": {".xml"},
    "sql": {".sql"},
}

_BACKEND_GREP_SUPPORTED = "-i, -s, -w, -F, --type/-t, -e, or a plain pattern"


def _build_backend_matcher(
    search_string: str,
) -> tuple["re.Pattern | None", "set[str] | None", str | None]:
    """Parse ``search_string`` into ``(regex, allowed_exts, error)`` for backend grep.

    Mirrors the local ripgrep flag modes as far as Python ``re`` can:

    * plain pattern (no leading ``-``) -> regex, verbatim
    * ``-i`` / ``--ignore-case`` -> ``re.IGNORECASE``
    * ``-s`` / ``--case-sensitive`` -> case-sensitive (default)
    * ``-w`` / ``--word-regexp`` -> wrap in ``\\b(?:...)\\b``
    * ``-F`` / ``--fixed-strings`` -> ``re.escape`` (literal match)
    * ``--type``/``-t`` NAME -> restrict to that type's extensions
    * ``-e``/``--regexp`` PAT -> explicit pattern

    Any other flag returns a clear error instead of the old behavior (compiling
    the flag text as a literal regex, which silently matched nothing).
    ``allowed_exts`` is ``None`` for "all files".
    """
    flags = 0
    fixed = False
    word = False
    exts: set[str] | None = None
    pattern: str | None = None

    if not search_string.startswith("-"):
        pattern = search_string
    else:
        tokens = _tokenize_flag_string(search_string)
        if tokens is None:
            pattern = search_string  # unmatched quote -> treat as literal
        else:
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                key, eq, inline = tok.partition("=")

                def _value() -> str | None:
                    nonlocal i
                    if eq:
                        return inline
                    if i + 1 < len(tokens):
                        i += 1
                        return tokens[i]
                    return None

                if key in _INCOMPATIBLE_RG_FLAGS:
                    return (
                        None,
                        None,
                        (
                            f"ripgrep flag '{key}' changes output format and is not "
                            f"supported by backend grep. Supported: {_BACKEND_GREP_SUPPORTED}."
                        ),
                    )
                if key in ("-i", "--ignore-case"):
                    flags |= re.IGNORECASE
                elif key in ("-s", "--case-sensitive"):
                    flags &= ~re.IGNORECASE
                elif key in ("-w", "--word-regexp"):
                    word = True
                elif key in ("-F", "--fixed-strings"):
                    fixed = True
                elif key in ("-t", "--type"):
                    name = _value()
                    mapped = _RG_TYPE_EXTS.get(name or "")
                    if mapped is None:
                        return (
                            None,
                            None,
                            (
                                f"--type '{name}' is not supported by backend grep "
                                f"(known: {', '.join(sorted(_RG_TYPE_EXTS))})"
                            ),
                        )
                    exts = (exts or set()) | mapped
                elif key in ("-e", "--regexp"):
                    pattern = _value()
                elif key.startswith("-"):
                    return (
                        None,
                        None,
                        (
                            f"grep flag '{key}' is not supported by backend grep. "
                            f"Supported: {_BACKEND_GREP_SUPPORTED}."
                        ),
                    )
                else:
                    pattern = tok  # positional -> the pattern
                i += 1

    if not pattern:
        return None, None, "no search pattern provided"
    if fixed:
        pattern = re.escape(pattern)
    if word:
        pattern = r"\b(?:" + pattern + r")\b"
    try:
        return re.compile(pattern, flags), exts, None
    except re.error as exc:
        return None, None, f"invalid search pattern: {exc}"


def _emit_grep_result(
    search_string: str,
    directory: str,
    matches: List["MatchInfo"],
    error_message: str | None,
) -> "GrepOutput":
    """Emit the structured grep result to the UI and return the tool output.

    Shared by the local (ripgrep) and backend (composed) grep paths so the UI
    behavior is identical regardless of where the search actually ran.
    """
    from code_puppy.config import get_grep_output_verbose

    grep_matches = [
        GrepMatch(
            file_path=m.file_path or "",
            line_number=m.line_number or 1,
            line_content=m.line_content or "",
        )
        for m in matches
    ]
    unique_files = len(set(m.file_path for m in matches)) if matches else 0
    grep_result_msg = GrepResultMessage(
        search_term=search_string,
        directory=directory,
        matches=grep_matches,
        total_matches=len(matches),
        files_searched=unique_files,
        verbose=get_grep_output_verbose(),
    )
    get_message_bus().emit(grep_result_msg)
    return GrepOutput(matches=matches, error=error_message)


def _grep_via_backend(directory: str, search_string: str) -> "GrepOutput":
    """Search through the installed filesystem backend (no local ripgrep).

    Walks the backend's filesystem and matches each file's text, so grep sees
    exactly what ``read_file`` and ``list_files`` see -- including, for an
    editor host, unsaved buffers. Flag mode is honored to the extent Python
    ``re`` allows: ``-i`` (ignore case), ``-s`` (case sensitive), ``-w`` (word),
    ``-F`` (fixed string), ``--type``/``-t`` (restrict extensions), and
    ``-e`` (explicit pattern). Unsupported flags return a clear error rather
    than silently matching nothing. Files larger than the local path's 5 MB
    cap and binary files (NUL in the first chunk) are skipped, matching
    ripgrep's defaults.
    """
    from code_puppy.tools.common import should_ignore_dir_path, should_ignore_path

    # Report a missing/non-directory target as an error, matching the local
    # ripgrep path (rather than silently returning zero matches for a typo'd
    # directory). ``walk`` itself tolerates a bad root by yielding nothing.
    if not fs_access.is_dir(directory):
        error_msg = (
            f"Error: Directory '{directory}' does not exist"
            if not fs_access.exists(directory)
            else f"Error: '{directory}' is not a directory"
        )
        return _emit_grep_result(search_string, directory, [], error_msg)

    pattern, allowed_exts, error = _build_backend_matcher(search_string)
    if error is not None:
        return _emit_grep_result(search_string, directory, [], error)

    max_filesize = 5 * 1024 * 1024  # mirror ripgrep --max-filesize 5M
    matches: List[MatchInfo] = []
    for full, entry in fs_access.walk(
        directory, skip_dir=should_ignore_dir_path, skip_file=should_ignore_path
    ):
        if entry.is_dir:
            continue
        if allowed_exts is not None and os.path.splitext(full)[1] not in allowed_exts:
            continue
        if entry.size and entry.size > max_filesize:
            continue
        try:
            text = fs_access.read_text(full)
        except Exception:
            # Unreadable/hostile file: skip it, never abort the whole search.
            continue
        if "\x00" in text[:8192]:  # cheap binary sniff, like ripgrep
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append(
                    MatchInfo(
                        file_path=full,
                        line_number=line_number,
                        line_content=_sanitize_string(line.strip()),
                    )
                )
                # Cap total matches to mirror the local path's 50-match limit.
                if len(matches) >= 50:
                    return _emit_grep_result(search_string, directory, matches, None)
    return _emit_grep_result(search_string, directory, matches, None)


def _grep(context: RunContext, search_string: str, directory: str = ".") -> GrepOutput:
    import json
    import os
    import shutil
    import subprocess
    import sys

    # Sanitize search string to handle any surrogates from copy-paste
    search_string = _sanitize_string(search_string)

    directory = resolve_path(directory)

    # When a filesystem backend is installed, search through it (walk + read)
    # so grep sees the same coherent filesystem as read_file / list_files.
    from code_puppy.tools.io_backends import get_filesystem_backend

    if get_filesystem_backend() is not None:
        return _grep_via_backend(directory, search_string)

    matches: List[MatchInfo] = []
    error_message: str | None = None

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
            # python_dir is already bin/ (Unix) or Scripts/ (Windows)
            for name in ["rg", "rg.exe"]:
                candidate = os.path.join(python_dir, name)
                if os.path.exists(candidate):
                    rg_path = candidate
                    break

        if not rg_path:
            error_message = (
                "ripgrep (rg) not found. Please install ripgrep to use this tool."
            )
            return GrepOutput(matches=[], error=error_message)

        # Plain patterns are passed verbatim via -e; strings starting with
        # '-' are tokenized as ripgrep flags. See _build_grep_args.
        rg_args, args_error = _build_grep_args(search_string)
        if args_error is not None:
            return GrepOutput(matches=[], error=args_error)

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
        from code_puppy.tools.common import DIR_IGNORE_PATTERNS

        f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ignore")
        ignore_file = f.name
        try:
            for pattern in DIR_IGNORE_PATTERNS:
                f.write(f"{pattern}\n")
        finally:
            f.close()

        cmd.extend(["--ignore-file", ignore_file])
        cmd.extend(rg_args)
        cmd.append(directory)
        # Use encoding with error handling to handle files with invalid UTF-8
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",  # Replace invalid chars instead of crashing
        )

        if result.returncode not in (0, 1):
            stderr = _sanitize_string(result.stderr.strip()) if result.stderr else ""
            error_message = stderr or f"ripgrep exited with code {result.returncode}"
        elif result.returncode == 1 and result.stderr.strip():
            error_message = _sanitize_string(result.stderr.strip())

        if error_message is not None:
            return GrepOutput(matches=[], error=error_message)

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
                        # Sanitize content to handle any remaining encoding issues
                        match_info = MatchInfo(
                            file_path=_sanitize_string(file_path),
                            line_number=line_number,
                            line_content=_sanitize_string(line_content.strip()),
                        )
                        matches.append(match_info)
                        # Limit to 50 matches total, same as original implementation
                        if len(matches) >= 50:
                            break
            except json.JSONDecodeError:
                # Skip lines that aren't valid JSON
                continue

    except subprocess.TimeoutExpired:
        error_message = "Grep command timed out after 30 seconds"
    except FileNotFoundError:
        error_message = (
            "ripgrep (rg) not found. Please install ripgrep to use this tool."
        )
    except Exception as e:
        error_message = f"Error during grep operation: {e}"
    finally:
        # Clean up the temporary ignore file
        if ignore_file and os.path.exists(ignore_file):
            os.unlink(ignore_file)

    # Build structured GrepMatch objects for the UI
    return _emit_grep_result(search_string, directory, matches, error_message)


def register_list_files(agent):
    """Register only the list_files tool."""
    from code_puppy.config import get_allow_recursion

    @agent.tool
    def list_files(
        context: RunContext, directory: str = ".", recursive: bool = True
    ) -> ListFileOutput:
        """List files and directories with intelligent filtering and safety features.

        Automatically ignores build artifacts, caches, and common noise.
        """
        warning = None
        if recursive and not get_allow_recursion():
            warning = "Recursion disabled globally for list_files - returning non-recursive results"
            recursive = False
        result = _list_files(context, directory, recursive)

        # The structured FileListingMessage is already emitted by _list_files
        # No need to emit again here
        if warning:
            result.error = warning

        # Context guard: if the listing is too chonky to dump straight into
        # the agent's context window, spill it to a temp file and hand the
        # agent a pointer instead. Keeps token usage sane on huge repos.
        _LIST_FILES_CONTEXT_LIMIT = 20_000
        if len(result.content) > _LIST_FILES_CONTEXT_LIMIT:
            from tempfile import NamedTemporaryFile, gettempdir

            # Pull the summary footer (last line of _list_files output) so the
            # agent still gets the counts without reading the dump file.
            summary_line = result.content.rstrip().rsplit("\n", 1)[-1]

            spill = NamedTemporaryFile(
                mode="w",
                prefix="code_puppy_listing_",
                suffix=".txt",
                dir=gettempdir(),
                delete=False,
                encoding="utf-8",
            )
            try:
                spill.write(result.content)
            finally:
                spill.close()

            result.content = (
                f"Directory listing for {directory} exceeded "
                f"{_LIST_FILES_CONTEXT_LIMIT} chars ({len(result.content)} total).\n"
                f"Full listing written to: {spill.name}\n"
                f"Use read_file on that path (in chunks if needed) to inspect it, "
                f"or call list_files again with recursive=False / a narrower directory.\n\n"
                f"{summary_line}"
            )
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

        Use start_line/num_lines for large files to avoid overwhelming context.
        """
        return _read_file(context, file_path, start_line, num_lines)


def register_grep(agent):
    """Register only the grep tool."""

    @agent.tool
    def grep(
        context: RunContext, search_string: str = "", directory: str = "."
    ) -> GrepOutput:
        """Recursively search file contents for a regex pattern using ripgrep (rg).

        By default the ENTIRE search_string is treated as one regex pattern --
        spaces, pipes, and backslashes are preserved exactly (e.g. 'class Limits'
        or 'foo|bar baz' work as-is, on every OS).

        To pass ripgrep flags, start the string with a flag and quote the
        pattern, e.g.: -i --type py 'def \\w+_handler'

        Output-format flags (-l, -c, --files, --count, --json, -q) are not
        supported and return an error. To search for a pattern that itself
        starts with '-', use: -e '-pattern'
        """
        return _grep(context, search_string, directory)
