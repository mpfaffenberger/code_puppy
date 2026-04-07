"""Terminal utilities for cross-platform terminal state management.

Handles Windows console mode resets and Unix terminal sanity restoration.
"""

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from rich.console import Console

# Store the original console ctrl handler so we can restore it if needed
_original_ctrl_handler: Optional[Callable] = None

_TRUECOLOR_TERM_MARKERS = (
    "xterm-direct",
    "xterm-ghostty",
    "xterm-truecolor",
    "iterm2",
    "vte-256color",
)


@dataclass(frozen=True)
class TerminalProfile:
    terminal_family: str
    supports_truecolor: bool
    live_updates_safe: bool


def _get_terminal_stream(console: Optional["Console"] = None):
    if console is not None and getattr(console, "file", None) is not None:
        return console.file
    return getattr(sys, "__stdout__", None) or sys.stdout


def _stream_is_tty(stream) -> bool:
    try:
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())
    except Exception:
        return False


def _detect_terminal_family() -> str:
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()

    if os.environ.get("WT_SESSION"):
        return "windows_terminal"
    if term_program == "apple_terminal":
        return "terminal_app"
    if (
        term_program == "ghostty"
        or "xterm-ghostty" in term
        or os.environ.get("GHOSTTY_RESOURCES_DIR")
    ):
        return "ghostty"
    if (
        os.environ.get("ITERM_SESSION_ID")
        or term_program == "iterm.app"
        or "iterm2" in term
    ):
        return "iterm2"
    if os.environ.get("KITTY_WINDOW_ID"):
        return "kitty"
    if os.environ.get("ALACRITTY_SOCKET"):
        return "alacritty"
    return "unknown"


def _detect_rich_truecolor(console: Optional["Console"] = None) -> bool:
    stream = _get_terminal_stream(console)
    if not _stream_is_tty(stream):
        return False

    try:
        if console is None:
            from rich.console import Console

            console = Console(file=stream)
    except Exception:
        return False

    return (console.color_system or "").lower() == "truecolor"


def get_terminal_profile(console: Optional["Console"] = None) -> TerminalProfile:
    """Return the best-effort terminal profile for the active session."""
    terminal_family = _detect_terminal_family()
    stream = _get_terminal_stream(console)
    is_interactive = _stream_is_tty(stream)

    colorterm = os.environ.get("COLORTERM", "").lower()
    term = os.environ.get("TERM", "").lower()

    supports_truecolor = False
    if colorterm in ("truecolor", "24bit"):
        supports_truecolor = True
    elif any(marker in term for marker in _TRUECOLOR_TERM_MARKERS):
        supports_truecolor = True
    elif terminal_family in {"ghostty", "iterm2"}:
        supports_truecolor = True
    elif any(
        os.environ.get(var)
        for var in (
            "ITERM_SESSION_ID",
            "KITTY_WINDOW_ID",
            "ALACRITTY_SOCKET",
            "WT_SESSION",
        )
    ):
        supports_truecolor = True
    else:
        supports_truecolor = _detect_rich_truecolor(console)

    live_updates_safe = is_interactive and os.environ.get("CI", "").lower() not in {
        "1",
        "true",
        "yes",
    }
    if platform.system() == "Windows":
        live_updates_safe = live_updates_safe and terminal_family == "windows_terminal"

    return TerminalProfile(
        terminal_family=terminal_family,
        supports_truecolor=supports_truecolor,
        live_updates_safe=live_updates_safe,
    )


def supports_live_terminal_updates(console: Optional["Console"] = None) -> bool:
    """Return whether live CR/ANSI redraws are safe for the active terminal."""
    return get_terminal_profile(console).live_updates_safe


def clear_live_terminal_line(
    stream=None, console: Optional["Console"] = None
) -> bool:
    """Clear the current live terminal line when CR-based redraw is supported."""
    target = stream or _get_terminal_stream(console)
    if not supports_live_terminal_updates(console) or not _stream_is_tty(target):
        return False

    try:
        target.write("\r")
        target.write("\x1b[K")
        target.flush()
        return True
    except Exception:
        return False


def reset_windows_terminal_ansi() -> None:
    """Reset ANSI formatting on Windows stdout/stderr.

    This is a lightweight reset that just clears ANSI escape sequences.
    Use this for quick resets after output operations.
    """
    if platform.system() != "Windows":
        return

    try:
        sys.stdout.write("\x1b[0m")  # Reset ANSI formatting
        sys.stdout.flush()
        sys.stderr.write("\x1b[0m")
        sys.stderr.flush()
    except Exception:
        pass  # Silently ignore errors - best effort reset


def reset_windows_console_mode() -> None:
    """Full Windows console mode reset using ctypes.

    This resets both stdout and stdin console modes to restore proper
    terminal behavior after interrupts (Ctrl+C, Ctrl+D). Without this,
    the terminal can become unresponsive (can't type characters).
    """
    if platform.system() != "Windows":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        # Reset stdout
        STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)

        # Enable virtual terminal processing and line input
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))

        # Console mode flags for stdout
        ENABLE_PROCESSED_OUTPUT = 0x0001
        ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        new_mode = (
            mode.value
            | ENABLE_PROCESSED_OUTPUT
            | ENABLE_WRAP_AT_EOL_OUTPUT
            | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        )
        kernel32.SetConsoleMode(handle, new_mode)

        # Reset stdin
        STD_INPUT_HANDLE = -10
        stdin_handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        # Console mode flags for stdin
        ENABLE_LINE_INPUT = 0x0002
        ENABLE_ECHO_INPUT = 0x0004
        ENABLE_PROCESSED_INPUT = 0x0001

        stdin_mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(stdin_handle, ctypes.byref(stdin_mode))

        new_stdin_mode = (
            stdin_mode.value
            | ENABLE_LINE_INPUT
            | ENABLE_ECHO_INPUT
            | ENABLE_PROCESSED_INPUT
        )
        kernel32.SetConsoleMode(stdin_handle, new_stdin_mode)

    except Exception:
        pass  # Silently ignore errors - best effort reset


def flush_windows_keyboard_buffer() -> None:
    """Flush the Windows keyboard buffer.

    Clears any pending keyboard input that could interfere with
    subsequent input operations after an interrupt.
    """
    if platform.system() != "Windows":
        return

    try:
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getch()
    except Exception:
        pass  # Silently ignore errors - best effort flush


def reset_windows_terminal_full() -> None:
    """Perform a full Windows terminal reset (ANSI + console mode + keyboard buffer).

    Combines ANSI reset, console mode reset, and keyboard buffer flush
    for complete terminal state restoration after interrupts.
    """
    if platform.system() != "Windows":
        return

    reset_windows_terminal_ansi()
    reset_windows_console_mode()
    flush_windows_keyboard_buffer()


def reset_unix_terminal() -> None:
    """Reset Unix/Linux/macOS terminal to sane state.

    Uses the `reset` command to restore terminal sanity.
    Silently fails if the command isn't available.
    """
    if platform.system() == "Windows":
        return

    try:
        subprocess.run(["reset"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Silently fail if reset command isn't available


def reset_terminal() -> None:
    """Cross-platform terminal reset.

    Automatically detects the platform and performs the appropriate
    terminal reset operation.
    """
    if platform.system() == "Windows":
        reset_windows_terminal_full()
    else:
        reset_unix_terminal()


def disable_windows_ctrl_c() -> bool:
    """Disable Ctrl+C processing at the Windows console input level.

    This removes ENABLE_PROCESSED_INPUT from stdin, which prevents
    Ctrl+C from being interpreted as a signal at all. Instead, it
    becomes just a regular character (^C) that gets ignored.

    This is more reliable than SetConsoleCtrlHandler because it
    prevents Ctrl+C from being processed before it reaches any handler.

    Returns:
        True if successfully disabled, False otherwise.
    """
    global _original_ctrl_handler

    if platform.system() != "Windows":
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        # Get stdin handle
        STD_INPUT_HANDLE = -10
        stdin_handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        # Get current console mode
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(stdin_handle, ctypes.byref(mode)):
            return False

        # Save original mode for potential restoration
        _original_ctrl_handler = mode.value

        # Console mode flags
        ENABLE_PROCESSED_INPUT = 0x0001  # This makes Ctrl+C generate signals

        # Remove ENABLE_PROCESSED_INPUT to disable Ctrl+C signal generation
        new_mode = mode.value & ~ENABLE_PROCESSED_INPUT

        if kernel32.SetConsoleMode(stdin_handle, new_mode):
            return True
        return False

    except Exception:
        return False


def enable_windows_ctrl_c() -> bool:
    """Re-enable Ctrl+C at the Windows console level.

    Restores the original console mode saved by disable_windows_ctrl_c().

    Returns:
        True if successfully re-enabled, False otherwise.
    """
    global _original_ctrl_handler

    if platform.system() != "Windows":
        return False

    if _original_ctrl_handler is None:
        return True  # Nothing to restore

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        # Get stdin handle
        STD_INPUT_HANDLE = -10
        stdin_handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        # Restore original mode
        if kernel32.SetConsoleMode(stdin_handle, _original_ctrl_handler):
            _original_ctrl_handler = None
            return True
        return False

    except Exception:
        return False


# Flag to track if we should keep Ctrl+C disabled
_keep_ctrl_c_disabled: bool = False


def set_keep_ctrl_c_disabled(value: bool) -> None:
    """Set whether Ctrl+C should be kept disabled.

    When True, ensure_ctrl_c_disabled() will re-disable Ctrl+C
    even if something else (like prompt_toolkit) re-enables it.
    """
    global _keep_ctrl_c_disabled
    _keep_ctrl_c_disabled = value


def ensure_ctrl_c_disabled() -> bool:
    """Ensure Ctrl+C is disabled if it should be.

    Call this after operations that might restore console mode
    (like prompt_toolkit input).

    Returns:
        True if Ctrl+C is now disabled (or wasn't needed), False on error.
    """
    if not _keep_ctrl_c_disabled:
        return True

    if platform.system() != "Windows":
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        # Get stdin handle
        STD_INPUT_HANDLE = -10
        stdin_handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        # Get current console mode
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(stdin_handle, ctypes.byref(mode)):
            return False

        # Console mode flags
        ENABLE_PROCESSED_INPUT = 0x0001

        # Check if Ctrl+C processing is enabled
        if mode.value & ENABLE_PROCESSED_INPUT:
            # Disable it
            new_mode = mode.value & ~ENABLE_PROCESSED_INPUT
            return bool(kernel32.SetConsoleMode(stdin_handle, new_mode))

        return True  # Already disabled

    except Exception:
        return False


def detect_truecolor_support() -> bool:
    """Detect if the terminal supports truecolor (24-bit color).

    Returns:
        True if truecolor is supported, False otherwise.
    """
    return get_terminal_profile().supports_truecolor


def _terminal_display_name(terminal_family: str) -> str:
    return {
        "ghostty": "Ghostty",
        "iterm2": "iTerm2",
        "terminal_app": "Terminal.app",
        "windows_terminal": "Windows Terminal",
    }.get(terminal_family, terminal_family)


def print_truecolor_warning(console: Optional["Console"] = None) -> None:
    """Print a big fat red warning if truecolor is not supported.

    Args:
        console: Optional Rich Console instance. If None, creates a new one.
    """
    if detect_truecolor_support():
        return  # All good, no warning needed
    profile = get_terminal_profile(console)

    if console is None:
        try:
            from rich.console import Console

            console = Console(file=_get_terminal_stream())
        except ImportError:
            # Rich not available, fall back to plain print
            print("\n" + "=" * 70)
            if profile.terminal_family == "terminal_app":
                print("NOTICE: Terminal.app works, but colors will be reduced.")
                print("=" * 70)
                print("Consider iTerm2 or Ghostty for full color fidelity on macOS.")
            else:
                print("⚠️  WARNING: TERMINAL DOES NOT SUPPORT TRUECOLOR (24-BIT COLOR)")
                print("=" * 70)
                print("Code Puppy looks best with truecolor support.")
                print("Consider using a modern terminal like:")
                print("  • iTerm2 (macOS)")
                print("  • Ghostty (macOS)")
                print("  • Windows Terminal (Windows)")
                print("  • Kitty, Alacritty, or Warp")
                print("")
                print("You can also try setting: export COLORTERM=truecolor")
            print("=" * 70 + "\n")
            return

    # Get detected color system for diagnostic info
    color_system = console.color_system or "unknown"

    if profile.terminal_family == "terminal_app":
        warning_lines = [
            "",
            "[bold yellow]" + "━" * 72 + "[/]",
            "[bold yellow]NOTICE: TERMINAL.APP COLORS WILL BE REDUCED[/]",
            "",
            f"[yellow]Detected terminal:[/] [bold]{_terminal_display_name(profile.terminal_family)}[/]",
            f"[yellow]Detected color system:[/] [bold]{color_system}[/]",
            "",
            "[bold white]Code Puppy should work normally here, but Terminal.app does not advertise truecolor.[/]",
            "",
            "[cyan]For full color fidelity on macOS, consider iTerm2 or Ghostty.[/]",
            "",
            "[bold yellow]" + "─" * 72 + "[/]",
            "",
        ]
    else:
        warning_lines = [
            "",
            "[bold bright_red on red]" + "━" * 72 + "[/]",
            "[bold bright_red on red]┃[/][bold bright_white on red]"
            + " " * 70
            + "[/][bold bright_red on red]┃[/]",
            "[bold bright_red on red]┃[/][bold bright_white on red]  ⚠️   WARNING: TERMINAL DOES NOT SUPPORT TRUECOLOR (24-BIT COLOR)  ⚠️   [/][bold bright_red on red]┃[/]",
            "[bold bright_red on red]┃[/][bold bright_white on red]"
            + " " * 70
            + "[/][bold bright_red on red]┃[/]",
            "[bold bright_red on red]" + "━" * 72 + "[/]",
            "",
            f"[yellow]Detected terminal:[/] [bold]{_terminal_display_name(profile.terminal_family)}[/]",
            f"[yellow]Detected color system:[/] [bold]{color_system}[/]",
            "",
            "[bold white]Code Puppy uses rich colors and will look degraded without truecolor.[/]",
            "",
            "[cyan]Consider using a modern terminal emulator:[/]",
            "  [green]•[/] [bold]iTerm2[/] (macOS) - https://iterm2.com",
            "  [green]•[/] [bold]Ghostty[/] (macOS) - https://ghostty.org",
            "  [green]•[/] [bold]Windows Terminal[/] (Windows) - Built into Windows 11",
            "  [green]•[/] [bold]Kitty[/] - https://sw.kovidgoyal.net/kitty",
            "  [green]•[/] [bold]Alacritty[/] - https://alacritty.org",
            "  [green]•[/] [bold]Warp[/] (macOS) - https://warp.dev",
            "",
            "[cyan]Or try setting the COLORTERM environment variable:[/]",
            "  [dim]export COLORTERM=truecolor[/]",
            "",
            "[bold bright_red]" + "─" * 72 + "[/]",
            "",
        ]

    for line in warning_lines:
        console.print(line)
