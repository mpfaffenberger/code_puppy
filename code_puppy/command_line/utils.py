import os
from typing import List, Tuple

from rich.table import Table


def list_directory(path: str = None) -> Tuple[List[str], List[str]]:
    """
    Returns (dirs, files) for the specified path, splitting out directories and files.
    """
    if path is None:
        path = os.getcwd()
    entries = []
    try:
        entries = [e for e in os.listdir(path)]
    except Exception as e:
        raise RuntimeError(f"Error listing directory: {e}") from e
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]
    return dirs, files


def make_directory_table(path: str = None) -> Table:
    """
    Returns a rich.Table object containing the directory listing.
    """
    if path is None:
        path = os.getcwd()
    dirs, files = list_directory(path)
    table = Table(
        title=f"\U0001f4c1 [bold blue]Current directory:[/bold blue] [cyan]{path}[/cyan]"
    )
    table.add_column("Type", style="dim", width=8)
    table.add_column("Name", style="bold")
    for d in sorted(dirs):
        table.add_row("[green]dir[/green]", f"[cyan]{d}[/cyan]")
    for f in sorted(files):
        table.add_row("[yellow]file[/yellow]", f"{f}")
    return table


def _reset_windows_console() -> None:
    """Reset Windows console to normal input mode.

    After a prompt_toolkit Application exits on Windows, the console can be
    left in a weird state where Enter doesn't work properly. This resets it.
    """
    import sys

    if sys.platform != "win32":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # Get handle to stdin
        STD_INPUT_HANDLE = -10
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        # Enable line input and echo (normal console mode)
        # ENABLE_LINE_INPUT = 0x0002
        # ENABLE_ECHO_INPUT = 0x0004
        # ENABLE_PROCESSED_INPUT = 0x0001
        NORMAL_MODE = 0x0007  # Line input + echo + processed
        kernel32.SetConsoleMode(handle, NORMAL_MODE)
    except Exception:
        pass  # Silently ignore errors - this is best-effort


def safe_input(prompt_text: str = "") -> str:
    """Cross-platform safe input that works after prompt_toolkit Applications.

    On Windows, raw input() can fail after a prompt_toolkit Application exits
    because the terminal can be left in a weird state. This function resets
    the Windows console mode before calling input().

    Args:
        prompt_text: The prompt to display to the user

    Returns:
        The user's input string (stripped)

    Raises:
        KeyboardInterrupt: If user presses Ctrl+C
        EOFError: If user presses Ctrl+D/Ctrl+Z
    """
    # Reset Windows console to normal mode before reading input
    _reset_windows_console()

    # Use standard input() - now that console is reset, it should work
    result = input(prompt_text)
    return result.strip() if result else ""
