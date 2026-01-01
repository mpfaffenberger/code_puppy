"""Terminal utilities for cross-platform terminal state management.

Handles Windows console mode resets and Unix terminal sanity restoration.
"""

import platform
import subprocess
import sys
from typing import Callable, Optional

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
