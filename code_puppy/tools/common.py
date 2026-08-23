import asyncio
import contextvars
import fnmatch
import hashlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rapidfuzz.distance import JaroWinkler
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

# Diff rendering is owned by termflow; this module only adapts it to
# Code Puppy's config colors, theme hooks, and Rich consoles.
from termflow.diff import DiffRenderer, DiffStream, DiffTheme
from termflow.diff import brighten_hex as brighten_hex  # re-export (public API)
from termflow.syntax import Highlighter as TermflowHighlighter

from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.tools.file_permission_state import set_diff_already_shown

# =============================================================================
# Approval queueing locks
# =============================================================================
# Parallel tool calls must serialize approval prompts (one answer at a time;
# prompt_toolkit owns stdin once). These locks queue callers; the async lock
# is created lazily to bind to the running event loop.

_APPROVAL_SYNC_LOCK = threading.Lock()
_APPROVAL_ASYNC_LOCK: Optional[asyncio.Lock] = None
_APPROVAL_ASYNC_LOCK_INIT_LOCK = threading.Lock()


def _get_approval_async_lock() -> asyncio.Lock:
    """Lazily create the global async approval lock.

    Python 3.10+ ``asyncio.Lock()`` no longer binds to a loop at
    construction time, so we can safely cache a single instance.
    """
    global _APPROVAL_ASYNC_LOCK
    if _APPROVAL_ASYNC_LOCK is None:
        with _APPROVAL_ASYNC_LOCK_INIT_LOCK:
            if _APPROVAL_ASYNC_LOCK is None:
                _APPROVAL_ASYNC_LOCK = asyncio.Lock()
    return _APPROVAL_ASYNC_LOCK


def _stdin_supports_interactive_approval() -> bool:
    """Return True only when stdin can accept interactive approval input."""
    stdin = getattr(sys, "stdin", None)
    if stdin is None:
        return False

    isatty = getattr(stdin, "isatty", None)
    if isatty is None:
        return False

    try:
        return bool(isatty())
    except Exception:
        return False


def _deny_noninteractive_approval(title: str) -> tuple[bool, None]:
    """Fail closed when approval is requested without an interactive stdin."""
    emit_warning(f"Approval for '{title}' rejected: stdin is not interactive.")
    return False, None


# =============================================================================
# Pluggable approval backend
# =============================================================================
# Frontends without stdin (GUI/web/ACP editor) would otherwise fail closed.
# An embedder registers a sync ``ApprovalBackend`` callable, which takes
# precedence over stdin in BOTH sync and async paths (async runs it in a
# worker thread to avoid bridging event loops).

ApprovalBackend = Callable[[str, str, Optional[str]], Tuple[bool, Optional[str]]]
_APPROVAL_BACKEND: Optional[ApprovalBackend] = None


def set_approval_backend(backend: Optional[ApprovalBackend]) -> None:
    """Install (or clear, with ``None``) the approval backend.

    ``backend(title, message, preview) -> (approved, feedback)``. When set, it
    replaces the interactive stdin prompt for every approval request, so a
    non-terminal frontend can gate file/shell operations in its own UI.
    """
    global _APPROVAL_BACKEND
    _APPROVAL_BACKEND = backend


def get_approval_backend() -> Optional[ApprovalBackend]:
    """Return the installed approval backend, or ``None`` for stdin prompting."""
    return _APPROVAL_BACKEND


def _approval_message_text(content) -> str:
    """Flatten Rich ``Text``/``str`` approval content to plain text."""
    plain = getattr(content, "plain", None)
    return plain if isinstance(plain, str) else str(content)


# =============================================================================
# Active working directory (async-safe base for relative path resolution)
# =============================================================================
# Default base is os.getcwd(); embedders (ACP editor sessions carry their own
# cwd) can override WITHOUT os.chdir (would corrupt SDK I/O + concurrent
# sessions). ContextVar isolates per task and propagates to to_thread workers.

_WORKING_DIR: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "code_puppy_working_dir", default=None
)


def set_working_directory(path: Optional[str]) -> contextvars.Token:
    """Override the base dir for relative path resolution in this context.

    Returns a token; pass it to :func:`reset_working_directory` to restore.
    """
    return _WORKING_DIR.set(path)


def reset_working_directory(token: contextvars.Token) -> None:
    """Restore the working directory to its value before ``set``."""
    _WORKING_DIR.reset(token)


def get_working_directory() -> str:
    """The active base dir for relative paths (override, else process CWD)."""
    return _WORKING_DIR.get() or os.getcwd()


def resolve_path(file_path: str) -> str:
    """Absolutize ``file_path`` against the active working directory.

    Expands ``~`` and joins relative paths onto :func:`get_working_directory`
    (absolute inputs pass through unchanged). Use this instead of
    ``os.path.abspath(os.path.expanduser(...))`` in tools so an embedder's
    per-session cwd is honored without a process-global ``os.chdir``.
    """
    expanded = os.path.expanduser(file_path)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(get_working_directory(), expanded))


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
# Directory vs file patterns: list_files ignores dirs only; grep ignores both
# (to avoid binary files).
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
# DIFF RENDERING (owned and operated by termflow; adapters only)
# ============================================================================


def _termflow_diff_renderer(
    addition_color: str | None = None,
    deletion_color: str | None = None,
) -> DiffRenderer:
    """Build termflow's diff renderer wired to Code Puppy's theming.

    The highlighter flows through the ``termflow_highlighter`` callback so
    themed highlighters (including their ``diff_line_tints``) keep working;
    colors default to the user's configured diff preferences.
    """
    from code_puppy.callbacks import on_termflow_highlighter
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
    )

    theme = DiffTheme(
        addition=addition_color or get_diff_addition_color(),
        deletion=deletion_color or get_diff_deletion_color(),
    )
    highlighter = on_termflow_highlighter(TermflowHighlighter())
    return DiffRenderer(highlighter=highlighter, theme=theme)


def stream_diff_ansi_lines(
    diff_text: str,
    addition_color: str | None = None,
    deletion_color: str | None = None,
) -> Iterator[str]:
    """Yield rendered ANSI diff lines incrementally via termflow's DiffStream.

    Consumers can paint large diffs progressively instead of blocking on a
    fully rendered block. Yielded lines carry no trailing newline; headers
    are skipped (the banner already names the file).
    """
    stream = DiffStream(_termflow_diff_renderer(addition_color, deletion_color))
    for raw_line in diff_text.splitlines(keepends=True):
        rendered = stream.feed(raw_line)
        if rendered:
            yield rendered.rstrip("\n")
    tail = stream.close()
    if tail:
        yield tail


def format_diff_with_colors(
    diff_text: str,
    addition_color: str | None = None,
    deletion_color: str | None = None,
) -> Text:
    """Format diff text with termflow's theme-aware diff renderer.

    This is the canonical block-mode diff formatting function used across
    the codebase. Parsing, syntax highlighting, backgrounds, and theme
    tints are all termflow's job; this adapter only supplies Code Puppy's
    configured colors and converts the ANSI result to Rich Text.

    Colors default to the effective theme-aware/user-configured preferences.
    Callers rendering a preview may pass colors directly, avoiding config
    mutations just to draw transient UI.

    Args:
        diff_text: Raw diff text to format
        addition_color: Optional addition background override.
        deletion_color: Optional deletion background override.

    Returns:
        Rich Text object with syntax highlighting
    """
    if not diff_text or not diff_text.strip():
        return Text("-- no diff available --", style="dim")

    renderer = _termflow_diff_renderer(addition_color, deletion_color)
    return Text.from_ansi(renderer.render(diff_text))


def _format_selector(
    message: str,
    choices: list[str],
    selected_index: int,
    preview_callback: Optional[Callable[[int], str]] = None,
) -> FormattedText:
    """Build shared selector content from semantic, literal-text fragments."""
    import textwrap

    fragments: list[tuple[str, str]] = [
        ("class:tui.header", message),
        ("", "\n\n"),
    ]
    for index, choice in enumerate(choices):
        style = "class:tui.selected" if index == selected_index else "class:tui.body"
        marker = "\u276f " if index == selected_index else "  "
        fragments.extend([(style, marker + choice), ("", "\n")])
    fragments.append(("", "\n"))

    preview_text = preview_callback(selected_index) if preview_callback else ""
    if preview_text:
        box_width = 60
        fragments.extend(
            [
                (
                    "class:tui.border",
                    "┌─ Preview " + "─" * (box_width - 10) + "┐\n",
                )
            ]
        )
        wrapped_lines = textwrap.wrap(preview_text, width=box_width - 2) or [""]
        for wrapped_line in wrapped_lines:
            fragments.append(
                ("class:tui.muted", f"│ {wrapped_line.ljust(box_width - 2)} │\n")
            )
        fragments.extend(
            [
                ("class:tui.border", "└" + "─" * box_width + "┘\n"),
                ("", "\n"),
            ]
        )

    fragments.extend(
        [
            ("class:tui.help", "("),
            ("class:tui.help-key", "↑↓ or Ctrl+P/N"),
            ("class:tui.help", " to select, "),
            ("class:tui.help-key", "Enter"),
            ("class:tui.help", " to confirm)"),
        ]
    )
    return FormattedText(fragments)


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
    selected_index = [0]  # Mutable container for selected index
    result = [None]  # Mutable container for result

    def get_formatted_text() -> FormattedText:
        """Generate semantic formatted text for display."""
        return _format_selector(
            message, choices, selected_index[0], preview_callback=preview_callback
        )

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")  # Ctrl+P = previous (Emacs-style)
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("down")
    @kb.add("c-n")  # Ctrl+N = next (Emacs-style)
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
        style=on_prompt_toolkit_style(),
    )

    # Flush output before prompt_toolkit takes control
    sys.stdout.flush()
    sys.stderr.flush()

    # Suspend the key listener so prompt_toolkit owns stdin exclusively —
    # otherwise CPR replies get eaten and arrow keys behave erratically.
    from code_puppy.agents._key_listeners import suspended_key_listener

    with suspended_key_listener():
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

    selected_index = [0]  # Mutable container for selected index
    result = [None]  # Mutable container for result

    def get_formatted_text() -> FormattedText:
        """Generate semantic formatted text for display."""
        return _format_selector(message, choices, selected_index[0])

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")  # Ctrl+P = previous (Emacs-style)
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        event.app.invalidate()  # Force redraw to update preview

    @kb.add("down")
    @kb.add("c-n")  # Ctrl+N = next (Emacs-style)
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
        style=on_prompt_toolkit_style(),
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
            # No event loop, safe to use app.run() -- but first suspend
            # the background key listener so prompt_toolkit owns stdin.
            from code_puppy.agents._key_listeners import suspended_key_listener

            with suspended_key_listener():
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

    Wraps the implementation in a global threading lock so that parallel
    callers (e.g. file operations from multiple tool threads) **queue**
    their prompts rather than colliding on stdin.

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
    with _APPROVAL_SYNC_LOCK:
        return _get_user_approval_impl(
            title=title,
            content=content,
            preview=preview,
            border_style=border_style,
            puppy_name=puppy_name,
        )


def _get_user_approval_impl(
    title: str,
    content: Text | str,
    preview: str | None = None,
    border_style: str = "dim white",
    puppy_name: str | None = None,
) -> tuple[bool, str | None]:
    """Inner implementation of get_user_approval (lock-free)."""
    import time

    from code_puppy.tools.command_runner import set_awaiting_user_input

    backend = get_approval_backend()
    if backend is not None:
        return backend(title, _approval_message_text(content), preview)

    if not _stdin_supports_interactive_approval():
        return _deny_noninteractive_approval(title)

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

        # Mark that we showed a diff preview (no-op when no permission
        # provider is registered, i.e. the file-permission plugin is absent).
        set_diff_already_shown(True)

    # Create panel
    panel = Panel(
        panel_content,
        title=f"[bold white]{title}[/bold white]",
        border_style=border_style,
        padding=(1, 2),
    )

    # Approval prompt takes over the terminal: suspend the run UI (scroll
    # region + stdin ownership) so the panel renders full-height. Exception-safe.
    from code_puppy.messaging.run_ui import suspended_run_ui

    set_awaiting_user_input(True)
    _ui_suspension = suspended_run_ui()
    _ui_suspension.__enter__()

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
            # Rich's Prompt.ask reads stdin -- suspend the key listener
            # so it doesn't fight us for keystrokes.
            from code_puppy.agents._key_listeners import suspended_key_listener

            with suspended_key_listener():
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
        try:
            _ui_suspension.__exit__(None, None, None)
        except Exception:
            pass

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

    # Show the result (the run UI is already restored by the finally above;
    # these lines scroll normally inside the bottom bar's region).
    emit_info("")
    if not confirmed:
        if user_feedback:
            emit_error("Rejected with feedback!")
            emit_warning(f'Telling {puppy_name}: "{user_feedback}"')
        else:
            emit_error("Rejected.")
    else:
        emit_success("Approved!")

    return confirmed, user_feedback


async def get_user_approval_async(
    title: str,
    content: Text | str,
    preview: str | None = None,
    border_style: str = "dim white",
    puppy_name: str | None = None,
) -> tuple[bool, str | None]:
    """Async version of get_user_approval - show a beautiful approval panel with arrow-key selector.

    Wraps the implementation in a global async lock so that parallel
    tool calls (e.g. several destructive shell commands fired in one
    turn) **queue** their approval prompts instead of being silently
    auto-rejected. The user gets one prompt at a time, in arrival order.

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
    async with _get_approval_async_lock():
        return await _get_user_approval_async_impl(
            title=title,
            content=content,
            preview=preview,
            border_style=border_style,
            puppy_name=puppy_name,
        )


async def _get_user_approval_async_impl(
    title: str,
    content: Text | str,
    preview: str | None = None,
    border_style: str = "dim white",
    puppy_name: str | None = None,
) -> tuple[bool, str | None]:
    """Inner implementation of get_user_approval_async (lock-free)."""
    from code_puppy.tools.command_runner import set_awaiting_user_input

    backend = get_approval_backend()
    if backend is not None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, backend, title, _approval_message_text(content), preview
        )

    if not _stdin_supports_interactive_approval():
        return _deny_noninteractive_approval(title)

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

        # Mark that we showed a diff preview (no-op when no permission
        # provider is registered, i.e. the file-permission plugin is absent).
        set_diff_already_shown(True)

    # Create panel
    panel = Panel(
        panel_content,
        title=f"[bold white]{title}[/bold white]",
        border_style=border_style,
        padding=(1, 2),
    )

    # Approval prompt takes over the terminal: suspend the run UI (scroll
    # region + stdin ownership) so the panel renders full-height. Exception-safe.
    from code_puppy.messaging.run_ui import suspended_run_ui

    set_awaiting_user_input(True)
    _ui_suspension = suspended_run_ui()
    _ui_suspension.__enter__()

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
            # Prompt.ask reads stdin — suspend the key listener or it eats
            # roughly half the keystrokes (feedback box looks "broken").
            from code_puppy.agents._key_listeners import suspended_key_listener

            with suspended_key_listener():
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
        try:
            _ui_suspension.__exit__(None, None, None)
        except Exception:
            pass

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

    # Show the result (the run UI is already restored by the finally above;
    # these lines scroll normally inside the bottom bar's region).
    emit_info("")
    if not confirmed:
        if user_feedback:
            emit_error("Rejected with feedback!")
            emit_warning(f'Telling {puppy_name}: "{user_feedback}"')
        else:
            emit_error("Rejected.")
    else:
        emit_success("Approved!")

    return confirmed, user_feedback


def atomic_write_text(
    file_path: str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Atomically write text to file_path (write-temp + os.replace).

    A crash / Ctrl-C / SIGKILL mid-write can never truncate the target:
    the original is untouched until the atomic rename. Preserves the
    target's permission bits when it already exists, resolves symlinks so
    the link itself isn't clobbered, and keeps the temp file in the SAME
    directory so os.replace stays on one filesystem (atomic).

    Always fsyncs the file (and best-effort fsyncs the containing directory)
    so the write is durable across power loss; the directory fsync is
    silently skipped where unsupported (e.g. Windows).

    Behavior notes / caveats:
    - On POSIX a read-only (0o444) target CAN be overwritten as long as its
      directory is writable, because rename depends on directory perms, not
      the file's mode (vim ``:w!`` semantics); the original mode is preserved.
      This differs from Windows, where os.replace over a read-only target
      raises PermissionError.
    - Each write replaces the inode, so any HARDLINKS are broken: other
      hardlinked names keep the OLD content (they are not updated in place).
    """
    # Resolve symlinks so we update the real file and keep the link intact.
    target = os.path.realpath(file_path)

    dir_name = os.path.dirname(target) or "."
    os.makedirs(dir_name, exist_ok=True)

    # Preserve the original permission bits if the target already exists.
    mode = None
    try:
        mode = os.stat(target).st_mode
    except OSError:
        mode = None

    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # Best-effort: fsync the directory so the rename is durable too.
    # Unsupported on some platforms (e.g. Windows) -- swallow gracefully.
    try:
        dir_fd = os.open(dir_name, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except (OSError, AttributeError):
        pass  # directory fsync unsupported -- file content is still durable


def write_project_file(
    file_path: str, content: str, *, encoding: str = "utf-8"
) -> None:
    """Write a *workspace* file the agent is editing, honoring the I/O backend.

    Use this (not ``atomic_write_text``) for files the agent creates or edits on
    the user's behalf. When a ``FileSystemBackend`` is installed (e.g. an editor
    host), the write is delegated to it so the change lands in the host's diff
    UI; otherwise it falls back to the local atomic write.

    ``encoding`` applies only to the local path -- a backend host owns its own
    on-disk encoding (the Agent Client Protocol, for instance, is UTF-8 only),
    so a non-default encoding cannot be honored through a backend.

    Internal writes (config, session state, agent metadata) intentionally keep
    calling ``atomic_write_text`` directly -- they are machine-local and must
    never be rerouted to an editor workspace.
    """
    from code_puppy.tools.io_backends import get_filesystem_backend

    backend = get_filesystem_backend()
    if backend is not None:
        if encoding.lower() not in ("utf-8", "utf8"):
            raise ValueError(
                f"filesystem backend writes are UTF-8 only; got encoding={encoding!r}"
            )
        backend.write_text_file(resolve_path(file_path), content)
        return
    atomic_write_text(file_path, content, encoding=encoding)


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
    # Pre-join the needle once; join windows on the fly
    for i in range(len(haystack_lines) - win_size + 1):
        window = "\n".join(haystack_lines[i : i + win_size])
        score = JaroWinkler.normalized_similarity(window, needle)
        if score > best_score:
            best_score = score
            best_span = (i, i + win_size)

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
