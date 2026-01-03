"""Terminal utilities for cross-platform terminal state management.

Handles Windows console mode resets and Unix terminal sanity restoration.
"""

import os
import platform
import subprocess
import sys
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from rich.console import Console

# Store the original console ctrl handler so we can restore it if needed
_original_ctrl_handler: Optional[Callable] = None


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

    Checks multiple indicators:
    1. COLORTERM environment variable (most reliable)
    2. TERM environment variable patterns
    3. Rich's Console color_system detection as fallback

    Returns:
        True if truecolor is supported, False otherwise.
    """
    # Check COLORTERM - this is the most reliable indicator
    colorterm = os.environ.get("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return True

    # Check TERM for known truecolor-capable terminals
    term = os.environ.get("TERM", "").lower()
    truecolor_terms = (
        "xterm-direct",
        "xterm-truecolor",
        "iterm2",
        "vte-256color",  # Many modern terminals set this
    )
    if any(t in term for t in truecolor_terms):
        return True

    # Some terminals like iTerm2, Kitty, Alacritty set specific env vars
    if os.environ.get("ITERM_SESSION_ID"):
        return True
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    if os.environ.get("ALACRITTY_SOCKET"):
        return True
    if os.environ.get("WT_SESSION"):  # Windows Terminal
        return True

    # Use Rich's detection as a fallback
    try:
        from rich.console import Console

        console = Console(force_terminal=True)
        color_system = console.color_system
        return color_system == "truecolor"
    except Exception:
        pass

    return False


def print_truecolor_warning(console: Optional["Console"] = None) -> None:
    """Print a big fat red warning if truecolor is not supported.

    Args:
        console: Optional Rich Console instance. If None, creates a new one.
    """
    if detect_truecolor_support():
        return  # All good, no warning needed

    if console is None:
        try:
            from rich.console import Console

            console = Console()
        except ImportError:
            # Rich not available, fall back to plain print
            print("\n" + "=" * 70)
            print("⚠️  WARNING: TERMINAL DOES NOT SUPPORT TRUECOLOR (24-BIT COLOR)")
            print("=" * 70)
            print("Code Puppy looks best with truecolor support.")
            print("Consider using a modern terminal like:")
            print("  • iTerm2 (macOS)")
            print("  • Windows Terminal (Windows)")
            print("  • Kitty, Alacritty, or any modern terminal emulator")
            print("")
            print("You can also try setting: export COLORTERM=truecolor")
            print("")
            print("Note: The built-in macOS Terminal.app does not support truecolor")
            print("(Sequoia and earlier). You'll need a different terminal app.")
            print("=" * 70 + "\n")
            return

    # Get detected color system for diagnostic info
    color_system = console.color_system or "unknown"

    # Build the warning box
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
        f"[yellow]Detected color system:[/] [bold]{color_system}[/]",
        "",
        "[bold white]Code Puppy uses rich colors and will look degraded without truecolor.[/]",
        "",
        "[cyan]Consider using a modern terminal emulator:[/]",
        "  [green]•[/] [bold]iTerm2[/] (macOS) - https://iterm2.com",
        "  [green]•[/] [bold]Windows Terminal[/] (Windows) - Built into Windows 11",
        "  [green]•[/] [bold]Kitty[/] - https://sw.kovidgoyal.net/kitty",
        "  [green]•[/] [bold]Alacritty[/] - https://alacritty.org",
        "  [green]•[/] [bold]Warp[/] (macOS) - https://warp.dev",
        "",
        "[cyan]Or try setting the COLORTERM environment variable:[/]",
        "  [dim]export COLORTERM=truecolor[/]",
        "",
        "[dim italic]Note: The built-in macOS Terminal.app does not support truecolor (Sequoia and earlier).[/]",
        "[dim italic]Setting COLORTERM=truecolor won't help - you'll need a different terminal app.[/]",
        "",
        "[bold bright_red]" + "─" * 72 + "[/]",
        "",
    ]

    for line in warning_lines:
        console.print(line)
