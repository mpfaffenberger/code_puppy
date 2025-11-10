import fnmatch
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

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

# Import our queue-based console system
try:
    from code_puppy.messaging import get_queue_console

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


def format_diff_with_colors(diff_text: str) -> str:
    """Format diff text with Rich markup for colored display.

    This is the canonical diff formatting function used across the codebase.
    It applies consistent color coding to diff lines:
    - Additions (+): bold green
    - Deletions (-): bold red
    - Hunk headers (@@): bold cyan
    - File headers (+++/---): dim white
    - Context lines: no formatting

    Args:
        diff_text: Raw diff text to format

    Returns:
        Formatted diff text with Rich markup
    """
    if not diff_text or not diff_text.strip():
        return "[dim]-- no diff available --[/dim]"

    formatted_lines = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            # Addition line - bold green
            formatted_lines.append(f"[bold green]{line}[/bold green]")
        elif line.startswith("-") and not line.startswith("---"):
            # Deletion line - bold red
            formatted_lines.append(f"[bold red]{line}[/bold red]")
        elif line.startswith("@@"):
            # Hunk header - bold cyan
            formatted_lines.append(f"[bold cyan]{line}[/bold cyan]")
        elif line.startswith("+++") or line.startswith("---"):
            # File header - dim white
            formatted_lines.append(f"[dim white]{line}[/dim white]")
        else:
            # Context line - no formatting
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


async def arrow_select_async(message: str, choices: list[str]) -> str:
    """Async version: Show an arrow-key navigable selector.

    Args:
        message: The prompt message to display
        choices: List of choice strings

    Returns:
        The selected choice string

    Raises:
        KeyboardInterrupt: If user cancels with Ctrl-C
    """

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

    @kb.add("down")
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)

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

    @kb.add("down")
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)

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
    console = Console()
    console.print()
    console.print(panel)
    console.print()

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
            console.print()
            console.print(f"[bold cyan]Tell {puppy_name} what to change:[/bold cyan]")
            user_feedback = Prompt.ask(
                "[bold green]➤[/bold green]",
                default="",
            ).strip()

            if not user_feedback:
                user_feedback = None

    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold red]⊗ Cancelled by user[/bold red]")
        confirmed = False

    finally:
        set_awaiting_user_input(False)
        # Explicitly resume spinners
        try:
            from code_puppy.messaging.spinner import resume_all_spinners

            resume_all_spinners()
        except (ImportError, Exception):
            pass

        # Force Rich console to reset display state to prevent artifacts
        try:
            # Clear Rich's internal display state to prevent artifacts
            console.file.write("\r")  # Return to start of line
            console.file.write("\x1b[K")  # Clear current line
            console.file.flush()
        except Exception:
            pass

        # Ensure streams are flushed
        sys.stdout.flush()
        sys.stderr.flush()
        # Add small delay to let spinner stabilize
        time.sleep(0.1)

    # Show result with explicit cursor reset
    console.print()
    if not confirmed:
        if user_feedback:
            console.print("[bold red]✗ Rejected with feedback![/bold red]")
            console.print(
                f'[bold yellow]📝 Telling {puppy_name}: "{user_feedback}"[/bold yellow]'
            )
        else:
            console.print("[bold red]✗ Rejected.[/bold red]")
    else:
        console.print("[bold green]✓ Approved![/bold green]")

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

    console.log(f"Best span: {best_span}")
    console.log(f"Best window: {best_window}")
    console.log(f"Best score: {best_score}")
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
