import fnmatch
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rapidfuzz.distance import JaroWinkler
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

# Syntax highlighting imports for "syntax" diff mode
try:
    from pygments import lex
    from pygments.lexers import TextLexer, get_lexer_by_name
    from pygments.token import Token

    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

# Import our queue-based console system
try:
    from code_puppy.messaging import (
        emit_error,
        emit_info,
        emit_success,
        emit_warning,
        get_queue_console,
    )

    # Use queue console by default, but allow fallback
    NO_COLOR = bool(int(os.environ.get("CODE_PUPPY_NO_COLOR", "0")))
    _rich_console = Console(no_color=NO_COLOR)
    console = get_queue_console()
    # Set the fallback console for compatibility
    console.fallback_console = _rich_console
except ImportError:
    # Fallback to regular Rich console if messaging system not available
    NO_COLOR = bool(int(os.environ.get("CODE_PUPPY_NO_COLOR", "0")))
    console = Console(no_color=NO_COLOR)

    # Provide fallback emit functions
    def emit_error(msg: str) -> None:
        console.print(f"[bold red]{msg}[/bold red]")

    def emit_info(msg: str) -> None:
        console.print(msg)

    def emit_success(msg: str) -> None:
        console.print(f"[bold green]{msg}[/bold green]")

    def emit_warning(msg: str) -> None:
        console.print(f"[bold yellow]{msg}[/bold yellow]")


def should_suppress_browser() -> bool:
    """Check if browsers should be suppressed (headless mode).

    Returns:
        True if browsers should be suppressed, False if they can open normally

    This respects multiple headless mode controls:
    - HEADLESS=true environment variable (suppresses ALL browsers)
    - BROWSER_HEADLESS=true environment variable (for browser automation)
    - CI=true environment variable (continuous integration)
    - PYTEST_CURRENT_TEST environment variable (running under pytest)
    """
    # Explicit headless mode
    if os.getenv("HEADLESS", "").lower() == "true":
        return True

    # Browser-specific headless mode
    if os.getenv("BROWSER_HEADLESS", "").lower() == "true":
        return True

    # Continuous integration environments
    if os.getenv("CI", "").lower() == "true":
        return True

    # Running under pytest
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True

    # Default to allowing browsers
    return False


# -------------------
# Shared ignore patterns/helpers
# Split into directory vs file patterns so tools can choose appropriately
# - list_files should ignore only directories (still show binary files inside non-ignored dirs)
# - grep should ignore both directories and files (avoid grepping binaries)
# -------------------
DIR_IGNORE_PATTERNS = [
    # Version control
    "**/.git/**",
    "**/.git",
    ".git/**",
    ".git",
    "**/.svn/**",
    "**/.hg/**",
    "**/.bzr/**",
    # Node.js / JavaScript / TypeScript
    "**/node_modules/**",
    "**/node_modules/**/*.js",
    "node_modules/**",
    "node_modules",
    "**/npm-debug.log*",
    "**/yarn-debug.log*",
    "**/yarn-error.log*",
    "**/pnpm-debug.log*",
    "**/.npm/**",
    "**/.yarn/**",
    "**/.pnpm-store/**",
    "**/coverage/**",
    "**/.nyc_output/**",
    "**/dist/**",
    "**/dist",
    "**/build/**",
    "**/build",
    "**/.next/**",
    "**/.nuxt/**",
    "**/out/**",
    "**/.cache/**",
    "**/.parcel-cache/**",
    "**/.vite/**",
    "**/storybook-static/**",
    "**/*.tsbuildinfo/**",
    # Python
    "**/__pycache__/**",
    "**/__pycache__",
    "__pycache__/**",
    "__pycache__",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.coverage",
    "**/htmlcov/**",
    "**/.tox/**",
    "**/.nox/**",
    "**/site-packages/**",
    "**/.venv/**",
    "**/.venv",
    "**/venv/**",
    "**/venv",
    "**/env/**",
    "**/ENV/**",
    "**/.env",
    "**/pip-wheel-metadata/**",
    "**/*.egg-info/**",
    "**/dist/**",
    "**/wheels/**",
    "**/pytest-reports/**",
    # Java (Maven, Gradle, SBT)
    "**/target/**",
    "**/target",
    "**/build/**",
    "**/build",
    "**/.gradle/**",
    "**/gradle-app.setting",
    "**/*.class",
    "**/*.jar",
    "**/*.war",
    "**/*.ear",
    "**/*.nar",
    "**/hs_err_pid*",
    "**/.classpath",
    "**/.project",
    "**/.settings/**",
    "**/bin/**",
    "**/project/target/**",
    "**/project/project/**",
    # Go
    "**/vendor/**",
    "**/*.exe",
    "**/*.exe~",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.test",
    "**/*.out",
    "**/go.work",
    "**/go.work.sum",
    # Rust
    "**/target/**",
    "**/Cargo.lock",
    "**/*.pdb",
    # Ruby
    "**/vendor/**",
    "**/.bundle/**",
    "**/Gemfile.lock",
    "**/*.gem",
    "**/.rvm/**",
    "**/.rbenv/**",
    "**/coverage/**",
    "**/.yardoc/**",
    "**/doc/**",
    "**/rdoc/**",
    "**/.sass-cache/**",
    "**/.jekyll-cache/**",
    "**/_site/**",
    # PHP
    "**/vendor/**",
    "**/composer.lock",
    "**/.phpunit.result.cache",
    "**/storage/logs/**",
    "**/storage/framework/cache/**",
    "**/storage/framework/sessions/**",
    "**/storage/framework/testing/**",
    "**/storage/framework/views/**",
    "**/bootstrap/cache/**",
    # .NET / C#
    "**/bin/**",
    "**/obj/**",
    "**/packages/**",
    "**/*.cache",
    "**/*.dll",
    "**/*.exe",
    "**/*.pdb",
    "**/*.user",
    "**/*.suo",
    "**/.vs/**",
    "**/TestResults/**",
    "**/BenchmarkDotNet.Artifacts/**",
    # C/C++
    "**/*.o",
    "**/*.obj",
    "**/*.so",
    "**/*.dll",
    "**/*.a",
    "**/*.lib",
    "**/*.dylib",
    "**/*.exe",
    "**/CMakeFiles/**",
    "**/CMakeCache.txt",
    "**/cmake_install.cmake",
    "**/Makefile",
    "**/compile_commands.json",
    "**/.deps/**",
    "**/.libs/**",
    "**/autom4te.cache/**",
    # Perl
    "**/blib/**",
    "**/_build/**",
    "**/Build",
    "**/Build.bat",
    "**/*.tmp",
    "**/*.bak",
    "**/*.old",
    "**/Makefile.old",
    "**/MANIFEST.bak",
    "**/META.yml",
    "**/META.json",
    "**/MYMETA.*",
    "**/.prove",
    # Scala
    "**/target/**",
    "**/project/target/**",
    "**/project/project/**",
    "**/.bloop/**",
    "**/.metals/**",
    "**/.ammonite/**",
    "**/*.class",
    # Elixir
    "**/_build/**",
    "**/deps/**",
    "**/*.beam",
    "**/.fetch",
    "**/erl_crash.dump",
    "**/*.ez",
    "**/doc/**",
    "**/.elixir_ls/**",
    # Swift
    "**/.build/**",
    "**/Packages/**",
    "**/*.xcodeproj/**",
    "**/*.xcworkspace/**",
    "**/DerivedData/**",
    "**/xcuserdata/**",
    "**/*.dSYM/**",
    # Kotlin
    "**/build/**",
    "**/.gradle/**",
    "**/*.class",
    "**/*.jar",
    "**/*.kotlin_module",
    # Clojure
    "**/target/**",
    "**/.lein-**",
    "**/.nrepl-port",
    "**/pom.xml.asc",
    "**/*.jar",
    "**/*.class",
    # Dart/Flutter
    "**/.dart_tool/**",
    "**/build/**",
    "**/.packages",
    "**/pubspec.lock",
    "**/*.g.dart",
    "**/*.freezed.dart",
    "**/*.gr.dart",
    # Haskell
    "**/dist/**",
    "**/dist-newstyle/**",
    "**/.stack-work/**",
    "**/*.hi",
    "**/*.o",
    "**/*.prof",
    "**/*.aux",
    "**/*.hp",
    "**/*.eventlog",
    "**/*.tix",
    # Erlang
    "**/ebin/**",
    "**/rel/**",
    "**/deps/**",
    "**/*.beam",
    "**/*.boot",
    "**/*.plt",
    "**/erl_crash.dump",
    # Common cache and temp directories
    "**/.cache/**",
    "**/cache/**",
    "**/tmp/**",
    "**/temp/**",
    "**/.tmp/**",
    "**/.temp/**",
    "**/logs/**",
    "**/*.log",
    "**/*.log.*",
    # IDE and editor files
    "**/.idea/**",
    "**/.idea",
    "**/.vscode/**",
    "**/.vscode",
    "**/*.swp",
    "**/*.swo",
    "**/*~",
    "**/.#*",
    "**/#*#",
    "**/.emacs.d/auto-save-list/**",
    "**/.vim/**",
    "**/.netrwhist",
    "**/Session.vim",
    "**/.sublime-project",
    "**/.sublime-workspace",
    # OS-specific files
    "**/.DS_Store",
    ".DS_Store",
    "**/Thumbs.db",
    "**/Desktop.ini",
    "**/.directory",
    "**/*.lnk",
    # Common artifacts
    "**/*.orig",
    "**/*.rej",
    "**/*.patch",
    "**/*.diff",
    "**/.*.orig",
    "**/.*.rej",
    # Backup files
    "**/*~",
    "**/*.bak",
    "**/*.backup",
    "**/*.old",
    "**/*.save",
    # Hidden files (but be careful with this one)
    "**/.*",  # Commented out as it might be too aggressive
    # Directory-only section ends here
]

FILE_IGNORE_PATTERNS = [
    # Binary image formats
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.bmp",
    "**/*.tiff",
    "**/*.tif",
    "**/*.webp",
    "**/*.ico",
    "**/*.svg",
    # Binary document formats
    "**/*.pdf",
    "**/*.doc",
    "**/*.docx",
    "**/*.xls",
    "**/*.xlsx",
    "**/*.ppt",
    "**/*.pptx",
    # Archive formats
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.bz2",
    "**/*.xz",
    "**/*.rar",
    "**/*.7z",
    # Media files
    "**/*.mp3",
    "**/*.mp4",
    "**/*.avi",
    "**/*.mov",
    "**/*.wmv",
    "**/*.flv",
    "**/*.wav",
    "**/*.ogg",
    # Font files
    "**/*.ttf",
    "**/*.otf",
    "**/*.woff",
    "**/*.woff2",
    "**/*.eot",
    # Other binary formats
    "**/*.bin",
    "**/*.dat",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
]

# Backwards compatibility for any imports still referring to IGNORE_PATTERNS
IGNORE_PATTERNS = DIR_IGNORE_PATTERNS + FILE_IGNORE_PATTERNS


def should_ignore_path(path: str) -> bool:
    """Return True if *path* matches any pattern in IGNORE_PATTERNS."""
    # Convert path to Path object for better pattern matching
    path_obj = Path(path)

    for pattern in IGNORE_PATTERNS:
        # Try pathlib's match method which handles ** patterns properly
        try:
            if path_obj.match(pattern):
                return True
        except ValueError:
            # If pathlib can't handle the pattern, fall back to fnmatch
            if fnmatch.fnmatch(path, pattern):
                return True

        # Additional check: if pattern contains **, try matching against
        # different parts of the path to handle edge cases
        if "**" in pattern:
            # Convert pattern to handle different path representations
            simplified_pattern = pattern.replace("**/", "").replace("/**", "")

            # Check if any part of the path matches the simplified pattern
            path_parts = path_obj.parts
            for i in range(len(path_parts)):
                subpath = Path(*path_parts[i:])
                if fnmatch.fnmatch(str(subpath), simplified_pattern):
                    return True
                # Also check individual parts
                if fnmatch.fnmatch(path_parts[i], simplified_pattern):
                    return True

    return False


def should_ignore_dir_path(path: str) -> bool:
    """Return True if path matches any directory ignore pattern (directories only)."""
    path_obj = Path(path)
    for pattern in DIR_IGNORE_PATTERNS:
        try:
            if path_obj.match(pattern):
                return True
        except ValueError:
            if fnmatch.fnmatch(path, pattern):
                return True
        if "**" in pattern:
            simplified = pattern.replace("**/", "").replace("/**", "")
            parts = path_obj.parts
            for i in range(len(parts)):
                subpath = Path(*parts[i:])
                if fnmatch.fnmatch(str(subpath), simplified):
                    return True
                if fnmatch.fnmatch(parts[i], simplified):
                    return True
    return False


# ============================================================================
# SYNTAX HIGHLIGHTING FOR DIFFS ("syntax" mode)
# ============================================================================

# Monokai color scheme - because we have taste 🎨
TOKEN_COLORS = (
    {
        Token.Keyword: "#f92672" if PYGMENTS_AVAILABLE else "magenta",
        Token.Name.Builtin: "#66d9ef" if PYGMENTS_AVAILABLE else "cyan",
        Token.Name.Function: "#a6e22e" if PYGMENTS_AVAILABLE else "green",
        Token.String: "#e6db74" if PYGMENTS_AVAILABLE else "yellow",
        Token.Number: "#ae81ff" if PYGMENTS_AVAILABLE else "magenta",
        Token.Comment: "#75715e" if PYGMENTS_AVAILABLE else "bright_black",
        Token.Operator: "#f92672" if PYGMENTS_AVAILABLE else "magenta",
    }
    if PYGMENTS_AVAILABLE
    else {}
)

EXTENSION_TO_LEXER_NAME = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".txt": "text",
}


def _get_lexer_for_extension(extension: str):
    """Get the appropriate Pygments lexer for a file extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        A Pygments lexer instance or None if Pygments not available
    """
    if not PYGMENTS_AVAILABLE:
        return None

    # Normalize extension to have leading dot and be lowercase
    if not extension.startswith("."):
        extension = f".{extension}"
    extension = extension.lower()

    lexer_name = EXTENSION_TO_LEXER_NAME.get(extension, "text")

    try:
        return get_lexer_by_name(lexer_name)
    except Exception:
        # Fallback to plain text if lexer not found
        return TextLexer()


def _get_token_color(token_type) -> str:
    """Get color for a token type from our Monokai scheme.

    Args:
        token_type: Pygments token type

    Returns:
        Hex color string or color name
    """
    if not PYGMENTS_AVAILABLE:
        return "#cccccc"

    for ttype, color in TOKEN_COLORS.items():
        if token_type in ttype:
            return color
    return "#cccccc"  # Default light-grey for unmatched tokens


def _highlight_code_line(code: str, bg_color: str | None, lexer) -> Text:
    """Highlight a line of code with syntax highlighting and optional background color.

    Args:
        code: The code string to highlight
        bg_color: Background color in hex format, or None for no background
        lexer: Pygments lexer instance to use

    Returns:
        Rich Text object with styling applied
    """
    if not PYGMENTS_AVAILABLE or lexer is None:
        # Fallback: just return text with optional background
        if bg_color:
            return Text(code, style=f"on {bg_color}")
        return Text(code)

    text = Text()

    for token_type, value in lex(code, lexer):
        # Strip trailing newlines that Pygments adds
        # Pygments lexer always adds a \n at the end of the last token
        value = value.rstrip("\n")

        # Skip if the value is now empty (was only whitespace/newlines)
        if not value:
            continue

        fg_color = _get_token_color(token_type)
        # Apply foreground color and optional background
        if bg_color:
            text.append(value, style=f"{fg_color} on {bg_color}")
        else:
            text.append(value, style=fg_color)

    return text


def _extract_file_extension_from_diff(diff_text: str) -> str:
    """Extract file extension from diff headers.

    Args:
        diff_text: Unified diff text

    Returns:
        File extension (e.g., '.py') or '.txt' as fallback
    """
    import re

    # Look for +++ b/filename.ext or --- a/filename.ext headers
    pattern = r"^(?:\+\+\+|---) [ab]/.*?(\.[a-zA-Z0-9]+)$"

    for line in diff_text.split("\n")[:10]:  # Check first 10 lines
        match = re.search(pattern, line)
        if match:
            return match.group(1)

    return ".txt"  # Fallback to plain text


# ============================================================================
# COLOR PAIR OPTIMIZATION (for "highlighted" mode)
# ============================================================================


def brighten_hex(hex_color: str, factor: float) -> str:
    """
    Darken a hex color by multiplying each RGB channel by `factor`.
    factor=1.0 -> no change
    factor=0.0 -> black
    factor=0.18 -> good for diff backgrounds (recommended)
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Expected #RRGGBB, got {hex_color!r}")

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = max(0, min(255, int(r * (1 + factor))))
    g = max(0, min(255, int(g * (1 + factor))))
    b = max(0, min(255, int(b * (1 + factor))))

    return f"#{r:02x}{g:02x}{b:02x}"


def _format_diff_with_syntax_highlighting(
    diff_text: str,
    addition_color: str | None = None,
    deletion_color: str | None = None,
) -> Text:
    """Format diff with full syntax highlighting using Pygments.

    This renders diffs with:
    - Syntax highlighting for code tokens
    - Colored backgrounds for context/added/removed lines
    - Monokai color scheme
    - Optional custom colors for additions/deletions

    Args:
        diff_text: Raw unified diff text
        addition_color: Optional custom color for added lines (default: green)
        deletion_color: Optional custom color for deleted lines (default: red)

    Returns:
        Rich Text object with syntax highlighting (can be passed to emit_info)
    """
    if not PYGMENTS_AVAILABLE:
        return Text(diff_text)

    # Extract file extension from diff headers
    extension = _extract_file_extension_from_diff(diff_text)
    lexer = _get_lexer_for_extension(extension)

    # Generate background colors from foreground colors
    add_fg = brighten_hex(addition_color, 0.6)
    del_fg = brighten_hex(deletion_color, 0.6)

    # Background colors for different line types
    # Context lines have no background (None) for clean, minimal diffs
    bg_colors = {
        "removed": deletion_color,
        "added": addition_color,
        "context": None,  # No background for unchanged lines
    }

    lines = diff_text.split("\n")
    # Remove trailing empty line if it exists (from trailing \n in diff)
    if lines and lines[-1] == "":
        lines = lines[:-1]
    result = Text()

    for i, line in enumerate(lines):
        if not line:
            # Empty line - just add a newline if not the last line
            if i < len(lines) - 1:
                result.append("\n")
            continue

        # Handle diff headers specially
        if line.startswith("---"):
            result.append(line, style="yellow")
        elif line.startswith("+++"):
            result.append(line, style="yellow")
        elif line.startswith("@@"):
            result.append(line, style="cyan")
        elif line.startswith(("diff ", "index ")):
            result.append(line, style="dim")
        else:
            # Determine line type and extract code content
            if line.startswith("-"):
                line_type = "removed"
                code = line[1:]  # Remove the '-' prefix
                marker_style = f"bold {del_fg} on {bg_colors[line_type]}"
                prefix = "- "
            elif line.startswith("+"):
                line_type = "added"
                code = line[1:]  # Remove the '+' prefix
                marker_style = f"bold {add_fg} on {bg_colors[line_type]}"
                prefix = "+ "
            else:
                line_type = "context"
                code = line[1:] if line.startswith(" ") else line
                # Context lines have no background - clean and minimal
                marker_style = ""  # No special styling for context markers
                prefix = "  "

            # Add the marker prefix
            if marker_style:  # Only apply style if we have one
                result.append(prefix, style=marker_style)
            else:
                result.append(prefix)

            # Add syntax-highlighted code
            highlighted = _highlight_code_line(code, bg_colors[line_type], lexer)
            result.append_text(highlighted)

        # Add newline after each line except the last
        if i < len(lines) - 1:
            result.append("\n")

    return result


def format_diff_with_colors(diff_text: str) -> Text:
    """Format diff text with beautiful syntax highlighting.

    This is the canonical diff formatting function used across the codebase.
    It applies user-configurable color coding with full syntax highlighting using Pygments.

    The function respects user preferences from config:
    - get_diff_addition_color(): Color for added lines (markers and backgrounds)
    - get_diff_deletion_color(): Color for deleted lines (markers and backgrounds)

    Args:
        diff_text: Raw diff text to format

    Returns:
        Rich Text object with syntax highlighting
    """
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
    )

    if not diff_text or not diff_text.strip():
        return Text("-- no diff available --", style="dim")

    addition_base_color = get_diff_addition_color()
    deletion_base_color = get_diff_deletion_color()

    # Always use beautiful syntax highlighting!
    if not PYGMENTS_AVAILABLE:
        emit_warning("Pygments not available, diffs will look plain")
        # Return plain text as fallback
        return Text(diff_text)

    # Return Text object with custom colors - emit_info handles this correctly
    return _format_diff_with_syntax_highlighting(
        diff_text,
        addition_color=addition_base_color,
        deletion_color=deletion_base_color,
    )


async def arrow_select_async(
    message: str,
    choices: list[str],
    preview_callback: Optional[Callable[[int], str]] = None,
) -> str:
    """Async version: Show an arrow-key navigable selector with optional preview.

    Args:
        message: The prompt message to display
        choices: List of choice strings
        preview_callback: Optional callback that takes the selected index and returns
                         preview text to display below the choices

    Returns:
        The selected choice string

    Raises:
        KeyboardInterrupt: If user cancels with Ctrl-C
    """
    import html

    selected_index = [0]  # Mutable container for selected index
    result = [None]  # Mutable container for result

    def get_formatted_text():
        """Generate the formatted text for display."""
        # Escape XML special characters to prevent parsing errors
        safe_message = html.escape(message)
        lines = [f"<b>{safe_message}</b>", ""]
        for i, choice in enumerate(choices):
            safe_choice = html.escape(choice)
            if i == selected_index[0]:
                lines.append(f"<ansigreen>❯ {safe_choice}</ansigreen>")
            else:
                lines.append(f"  {safe_choice}")
        lines.append("")

        # Add preview section if callback provided
        if preview_callback is not None:
            preview_text = preview_callback(selected_index[0])
            if preview_text:
                import textwrap

                # Box width (excluding borders and padding)
                box_width = 60
                border_top = (
                    "<ansiyellow>┌─ Preview "
                    + "─" * (box_width - 10)
                    + "┐</ansiyellow>"
                )
                border_bottom = "<ansiyellow>└" + "─" * box_width + "┘</ansiyellow>"

                lines.append(border_top)

                # Wrap text to fit within box width (minus padding)
                wrapped_lines = textwrap.wrap(preview_text, width=box_width - 2)

                # If no wrapped lines (empty text), add empty line
                if not wrapped_lines:
                    wrapped_lines = [""]

                for wrapped_line in wrapped_lines:
                    safe_preview = html.escape(wrapped_line)
                    # Pad line to box width for consistent appearance
                    padded_line = safe_preview.ljust(box_width - 2)
                    lines.append(f"<dim>│ {padded_line} │</dim>")

                lines.append(border_bottom)
                lines.append("")

        lines.append("<ansicyan>(Use ↑↓ arrows to select, Enter to confirm)</ansicyan>")
        return HTML("\n".join(lines))

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("down")
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("enter")
    def accept(event):
        result[0] = choices[selected_index[0]]
        event.app.exit()

    @kb.add("c-c")  # Ctrl-C
    def cancel(event):
        result[0] = None
        event.app.exit()

    # Layout
    control = FormattedTextControl(get_formatted_text)
    layout = Layout(Window(content=control))

    # Application
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
    )

    # Flush output before prompt_toolkit takes control
    sys.stdout.flush()
    sys.stderr.flush()

    # Run the app asynchronously
    await app.run_async()

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]


def arrow_select(message: str, choices: list[str]) -> str:
    """Show an arrow-key navigable selector (synchronous version).

    Args:
        message: The prompt message to display
        choices: List of choice strings

    Returns:
        The selected choice string

    Raises:
        KeyboardInterrupt: If user cancels with Ctrl-C
    """
    import asyncio

    selected_index = [0]  # Mutable container for selected index
    result = [None]  # Mutable container for result

    def get_formatted_text():
        """Generate the formatted text for display."""
        lines = [f"<b>{message}</b>", ""]
        for i, choice in enumerate(choices):
            if i == selected_index[0]:
                lines.append(f"<ansigreen>❯ {choice}</ansigreen>")
            else:
                lines.append(f"  {choice}")
        lines.append("")
        lines.append("<ansicyan>(Use ↑↓ arrows to select, Enter to confirm)</ansicyan>")
        return HTML("\n".join(lines))

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("down")
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("enter")
    def accept(event):
        result[0] = choices[selected_index[0]]
        event.app.exit()

    @kb.add("c-c")  # Ctrl-C
    def cancel(event):
        result[0] = None
        event.app.exit()

    # Layout
    control = FormattedTextControl(get_formatted_text)
    layout = Layout(Window(content=control))

    # Application
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
    )

    # Flush output before prompt_toolkit takes control
    sys.stdout.flush()
    sys.stderr.flush()

    # Check if we're already in an async context
    try:
        asyncio.get_running_loop()
        # We're in an async context - can't use app.run()
        # Caller should use arrow_select_async instead
        raise RuntimeError(
            "arrow_select() called from async context. Use arrow_select_async() instead."
        )
    except RuntimeError as e:
        if "no running event loop" in str(e).lower():
            # No event loop, safe to use app.run()
            app.run()
        else:
            # Re-raise if it's our error message
            raise

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]


def get_user_approval(
    title: str,
    content: Text | str,
    preview: str | None = None,
    border_style: str = "dim white",
    puppy_name: str | None = None,
) -> tuple[bool, str | None]:
    """Show a beautiful approval panel with arrow-key selector.

    Args:
        title: Title for the panel (e.g., "File Operation", "Shell Command")
        content: Main content to display (Rich Text object or string)
        preview: Optional preview content (like a diff)
        border_style: Border color/style for the panel
        puppy_name: Name of the assistant (defaults to config value)

    Returns:
        Tuple of (confirmed: bool, user_feedback: str | None)
        - confirmed: True if approved, False if rejected
        - user_feedback: Optional feedback text if user provided it
    """
    import time

    from code_puppy.tools.command_runner import set_awaiting_user_input

    if puppy_name is None:
        from code_puppy.config import get_puppy_name

        puppy_name = get_puppy_name().title()

    # Build panel content
    if isinstance(content, str):
        panel_content = Text(content)
    else:
        panel_content = content

    # Add preview if provided
    if preview:
        panel_content.append("\n\n", style="")
        panel_content.append("Preview of changes:", style="bold underline")
        panel_content.append("\n", style="")
        formatted_preview = format_diff_with_colors(preview)

        # Handle both string (text mode) and Text object (highlight mode)
        if isinstance(formatted_preview, Text):
            preview_text = formatted_preview
        else:
            preview_text = Text.from_markup(formatted_preview)

        panel_content.append(preview_text)

        # Mark that we showed a diff preview
        try:
            from code_puppy.plugins.file_permission_handler.register_callbacks import (
                set_diff_already_shown,
            )

            set_diff_already_shown(True)
        except ImportError:
            pass

    # Create panel
    panel = Panel(
        panel_content,
        title=f"[bold white]{title}[/bold white]",
        border_style=border_style,
        padding=(1, 2),
    )

    # Pause spinners BEFORE showing panel
    set_awaiting_user_input(True)
    # Also explicitly pause spinners to ensure they're fully stopped
    try:
        from code_puppy.messaging.spinner import pause_all_spinners

        pause_all_spinners()
    except (ImportError, Exception):
        pass

    time.sleep(0.3)  # Let spinners fully stop

    # Display panel
    local_console = Console()
    emit_info("")
    local_console.print(panel)
    emit_info("")

    # Flush and buffer before selector
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(0.1)

    user_feedback = None
    confirmed = False

    try:
        # Final flush
        sys.stdout.flush()

        # Show arrow-key selector
        choice = arrow_select(
            "💭 What would you like to do?",
            [
                "✓ Approve",
                "✗ Reject",
                f"💬 Reject with feedback (tell {puppy_name} what to change)",
            ],
        )

        if choice == "✓ Approve":
            confirmed = True
        elif choice == "✗ Reject":
            confirmed = False
        else:
            # User wants to provide feedback
            confirmed = False
            emit_info("")
            emit_info(f"Tell {puppy_name} what to change:")
            user_feedback = Prompt.ask(
                "[bold green]➤[/bold green]",
                default="",
            ).strip()

            if not user_feedback:
                user_feedback = None

    except (KeyboardInterrupt, EOFError):
        emit_error("Cancelled by user")
        confirmed = False

    finally:
        set_awaiting_user_input(False)

        # Force Rich console to reset display state to prevent artifacts
        try:
            # Clear Rich's internal display state to prevent artifacts
            local_console.file.write("\r")  # Return to start of line
            local_console.file.write("\x1b[K")  # Clear current line
            local_console.file.flush()
        except Exception:
            pass

        # Ensure streams are flushed
        sys.stdout.flush()
        sys.stderr.flush()

    # Show result BEFORE resuming spinners (no puppy litter!)
    emit_info("")
    if not confirmed:
        if user_feedback:
            emit_error("Rejected with feedback!")
            emit_warning(f'Telling {puppy_name}: "{user_feedback}"')
        else:
            emit_error("Rejected.")
    else:
        emit_success("Approved!")

    # NOW resume spinners after showing the result
    try:
        from code_puppy.messaging.spinner import resume_all_spinners

        resume_all_spinners()
    except (ImportError, Exception):
        pass

    return confirmed, user_feedback


async def get_user_approval_async(
    title: str,
    content: Text | str,
    preview: str | None = None,
    border_style: str = "dim white",
    puppy_name: str | None = None,
) -> tuple[bool, str | None]:
    """Async version of get_user_approval - show a beautiful approval panel with arrow-key selector.

    Args:
        title: Title for the panel (e.g., "File Operation", "Shell Command")
        content: Main content to display (Rich Text object or string)
        preview: Optional preview content (like a diff)
        border_style: Border color/style for the panel
        puppy_name: Name of the assistant (defaults to config value)

    Returns:
        Tuple of (confirmed: bool, user_feedback: str | None)
        - confirmed: True if approved, False if rejected
        - user_feedback: Optional feedback text if user provided it
    """
    import asyncio

    from code_puppy.tools.command_runner import set_awaiting_user_input

    if puppy_name is None:
        from code_puppy.config import get_puppy_name

        puppy_name = get_puppy_name().title()

    # Build panel content
    if isinstance(content, str):
        panel_content = Text(content)
    else:
        panel_content = content

    # Add preview if provided
    if preview:
        panel_content.append("\n\n", style="")
        panel_content.append("Preview of changes:", style="bold underline")
        panel_content.append("\n", style="")
        formatted_preview = format_diff_with_colors(preview)

        # Handle both string (text mode) and Text object (highlight mode)
        if isinstance(formatted_preview, Text):
            preview_text = formatted_preview
        else:
            preview_text = Text.from_markup(formatted_preview)

        panel_content.append(preview_text)

        # Mark that we showed a diff preview
        try:
            from code_puppy.plugins.file_permission_handler.register_callbacks import (
                set_diff_already_shown,
            )

            set_diff_already_shown(True)
        except ImportError:
            pass

    # Create panel
    panel = Panel(
        panel_content,
        title=f"[bold white]{title}[/bold white]",
        border_style=border_style,
        padding=(1, 2),
    )

    # Pause spinners BEFORE showing panel
    set_awaiting_user_input(True)
    # Also explicitly pause spinners to ensure they're fully stopped
    try:
        from code_puppy.messaging.spinner import pause_all_spinners

        pause_all_spinners()
    except (ImportError, Exception):
        pass

    await asyncio.sleep(0.3)  # Let spinners fully stop

    # Display panel
    local_console = Console()
    emit_info("")
    local_console.print(panel)
    emit_info("")

    # Flush and buffer before selector
    sys.stdout.flush()
    sys.stderr.flush()
    await asyncio.sleep(0.1)

    user_feedback = None
    confirmed = False

    try:
        # Final flush
        sys.stdout.flush()

        # Show arrow-key selector (ASYNC VERSION)
        choice = await arrow_select_async(
            "💭 What would you like to do?",
            [
                "✓ Approve",
                "✗ Reject",
                f"💬 Reject with feedback (tell {puppy_name} what to change)",
            ],
        )

        if choice == "✓ Approve":
            confirmed = True
        elif choice == "✗ Reject":
            confirmed = False
        else:
            # User wants to provide feedback
            confirmed = False
            emit_info("")
            emit_info(f"Tell {puppy_name} what to change:")
            user_feedback = Prompt.ask(
                "[bold green]➤[/bold green]",
                default="",
            ).strip()

            if not user_feedback:
                user_feedback = None

    except (KeyboardInterrupt, EOFError):
        emit_error("Cancelled by user")
        confirmed = False

    finally:
        set_awaiting_user_input(False)

        # Force Rich console to reset display state to prevent artifacts
        try:
            # Clear Rich's internal display state to prevent artifacts
            local_console.file.write("\r")  # Return to start of line
            local_console.file.write("\x1b[K")  # Clear current line
            local_console.file.flush()
        except Exception:
            pass

        # Ensure streams are flushed
        sys.stdout.flush()
        sys.stderr.flush()

    # Show result BEFORE resuming spinners (no puppy litter!)
    emit_info("")
    if not confirmed:
        if user_feedback:
            emit_error("Rejected with feedback!")
            emit_warning(f'Telling {puppy_name}: "{user_feedback}"')
        else:
            emit_error("Rejected.")
    else:
        emit_success("Approved!")

    # NOW resume spinners after showing the result
    try:
        from code_puppy.messaging.spinner import resume_all_spinners

        resume_all_spinners()
    except (ImportError, Exception):
        pass

    return confirmed, user_feedback


def _find_best_window(
    haystack_lines: list[str],
    needle: str,
) -> Tuple[Optional[Tuple[int, int]], float]:
    """
    Return (start, end) indices of the window with the highest
    Jaro-Winkler similarity to `needle`, along with that score.
    If nothing clears JW_THRESHOLD, return (None, score).
    """
    needle = needle.rstrip("\n")
    needle_lines = needle.splitlines()
    win_size = len(needle_lines)
    best_score = 0.0
    best_span: Optional[Tuple[int, int]] = None
    best_window = ""
    # Pre-join the needle once; join windows on the fly
    for i in range(len(haystack_lines) - win_size + 1):
        window = "\n".join(haystack_lines[i : i + win_size])
        score = JaroWinkler.normalized_similarity(window, needle)
        if score > best_score:
            best_score = score
            best_span = (i, i + win_size)
            best_window = window

    # Debug logging
    console.log(best_span)
    console.log(best_window)
    console.log(best_score)
    return best_span, best_score


def generate_group_id(tool_name: str, extra_context: str = "") -> str:
    """Generate a unique group_id for tool output grouping.

    Args:
        tool_name: Name of the tool (e.g., 'list_files', 'edit_file')
        extra_context: Optional extra context to make group_id more unique

    Returns:
        A string in format: tool_name_hash
    """
    # Create a unique identifier using timestamp, context, and a random component
    import random

    timestamp = str(int(time.time() * 1000000))  # microseconds for more uniqueness
    random_component = random.randint(1000, 9999)  # Add randomness
    context_string = f"{tool_name}_{timestamp}_{random_component}_{extra_context}"

    # Generate a short hash
    hash_obj = hashlib.md5(context_string.encode())
    short_hash = hash_obj.hexdigest()[:8]

    return f"{tool_name}_{short_hash}"
