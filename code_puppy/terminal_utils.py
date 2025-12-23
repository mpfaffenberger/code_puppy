"""Terminal utilities for cross-platform terminal state management.

Handles Windows console mode resets and Unix terminal sanity restoration.
"""

import platform
import subprocess
import sys


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


def reset_windows_terminal_full() -> None:
    """Perform a full Windows terminal reset (ANSI + console mode).

    Combines both ANSI reset and console mode reset for complete
    terminal state restoration after interrupts.
    """
    if platform.system() != "Windows":
        return

    reset_windows_terminal_ansi()
    reset_windows_console_mode()


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
