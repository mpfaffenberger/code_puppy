"""Platform-aware keyboard shortcuts for common operations."""

from __future__ import annotations

from pydantic_ai import RunContext

from .dependencies import PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

from .rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id

from .platform import IS_MACOS, get_platform_display_name
from .result_types import KeyboardActionResult
from .tool_wrapper import desktop_tool


def get_modifier_key() -> str:
    """Get the primary modifier key for the current platform.

    Returns:
        'command' on macOS, 'ctrl' on Windows
    """
    return "command" if IS_MACOS else "ctrl"


def register_keyboard_shortcut_tools(agent):
    """Register platform-aware keyboard shortcut tools."""

    @agent.tool
    @desktop_tool("COPY", requires="pyautogui")
    def desktop_copy(context: RunContext) -> KeyboardActionResult:
        """
        Copy selected content to clipboard (platform-aware).

        Uses Cmd+C on macOS, Ctrl+C on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_copy()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_copy", platform)
        emit_rich(
            f"[bold cyan]COPY[/bold cyan] ⌨️  Using {modifier}+C ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "c")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+c",
            keys=[modifier, "c"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("PASTE", requires="pyautogui")
    def desktop_paste(context: RunContext) -> KeyboardActionResult:
        """
        Paste clipboard content (platform-aware).

        Uses Cmd+V on macOS, Ctrl+V on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_paste()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_paste", platform)
        emit_rich(
            f"[bold cyan]PASTE[/bold cyan] ⌨️  Using {modifier}+V ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "v")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+v",
            keys=[modifier, "v"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("CUT", requires="pyautogui")
    def desktop_cut(context: RunContext) -> KeyboardActionResult:
        """
        Cut selected content to clipboard (platform-aware).

        Uses Cmd+X on macOS, Ctrl+X on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_cut()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_cut", platform)
        emit_rich(
            f"[bold cyan]CUT[/bold cyan] ⌨️  Using {modifier}+X ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "x")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+x",
            keys=[modifier, "x"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("SELECT ALL", requires="pyautogui")
    def desktop_select_all(context: RunContext) -> KeyboardActionResult:
        """
        Select all content (platform-aware).

        Uses Cmd+A on macOS, Ctrl+A on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_select_all()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_select_all", platform)
        emit_rich(
            f"[bold cyan]SELECT ALL[/bold cyan] ⌨️  Using {modifier}+A ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "a")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+a",
            keys=[modifier, "a"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("SAVE", requires="pyautogui")
    def desktop_save(context: RunContext) -> KeyboardActionResult:
        """
        Save current document (platform-aware).

        Uses Cmd+S on macOS, Ctrl+S on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_save()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_save", platform)
        emit_rich(
            f"[bold cyan]SAVE[/bold cyan] ⌨️  Using {modifier}+S ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "s")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+s",
            keys=[modifier, "s"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("UNDO", requires="pyautogui")
    def desktop_undo(context: RunContext) -> KeyboardActionResult:
        """
        Undo last action (platform-aware).

        Uses Cmd+Z on macOS, Ctrl+Z on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_undo()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_undo", platform)
        emit_rich(
            f"[bold cyan]UNDO[/bold cyan] ⌨️  Using {modifier}+Z ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "z")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+z",
            keys=[modifier, "z"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("REDO", requires="pyautogui")
    def desktop_redo(context: RunContext) -> KeyboardActionResult:
        """
        Redo last undone action (platform-aware).

        Uses Cmd+Shift+Z on macOS, Ctrl+Y on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_redo()  # Uses correct shortcut for your OS
        """
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_redo", platform)

        if IS_MACOS:
            # macOS uses Cmd+Shift+Z for redo
            emit_rich(
                f"[bold cyan]REDO[/bold cyan] ⌨️  Using command+shift+Z ({platform})",
                message_group=group_id,
            )
            pyautogui.hotkey("command", "shift", "z")
            return KeyboardActionResult(
                success=True,
                hotkey="command+shift+z",
                keys=["command", "shift", "z"],
                platform=platform,
            )
        else:
            # Windows use Ctrl+Y for redo
            emit_rich(
                f"[bold cyan]REDO[/bold cyan] ⌨️  Using ctrl+Y ({platform})",
                message_group=group_id,
            )
            pyautogui.hotkey("ctrl", "y")
            return KeyboardActionResult(
                success=True,
                hotkey="ctrl+y",
                keys=["ctrl", "y"],
                platform=platform,
            )

    @agent.tool
    @desktop_tool("FIND", requires="pyautogui")
    def desktop_find(context: RunContext) -> KeyboardActionResult:
        """
        Open find/search dialog (platform-aware).

        Uses Cmd+F on macOS, Ctrl+F on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_find()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_find", platform)
        emit_rich(
            f"[bold cyan]FIND[/bold cyan] ⌨️  Using {modifier}+F ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "f")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+f",
            keys=[modifier, "f"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("NEW", requires="pyautogui")
    def desktop_new(context: RunContext) -> KeyboardActionResult:
        """
        Create new document/window (platform-aware).

        Uses Cmd+N on macOS, Ctrl+N on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_new()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_new", platform)
        emit_rich(
            f"[bold cyan]NEW[/bold cyan] ⌨️  Using {modifier}+N ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "n")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+n",
            keys=[modifier, "n"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("OPEN", requires="pyautogui")
    def desktop_open(context: RunContext) -> KeyboardActionResult:
        """
        Open file dialog (platform-aware).

        Uses Cmd+O on macOS, Ctrl+O on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_open()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_open", platform)
        emit_rich(
            f"[bold cyan]OPEN[/bold cyan] ⌨️  Using {modifier}+O ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "o")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+o",
            keys=[modifier, "o"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("CLOSE", requires="pyautogui")
    def desktop_close(context: RunContext) -> KeyboardActionResult:
        """
        Close current window/document (platform-aware).

        Uses Cmd+W on macOS, Ctrl+W on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_close()  # Uses correct shortcut for your OS
        """
        modifier = get_modifier_key()
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_close", platform)
        emit_rich(
            f"[bold cyan]CLOSE[/bold cyan] ⌨️  Using {modifier}+W ({platform})",
            message_group=group_id,
        )

        pyautogui.hotkey(modifier, "w")
        return KeyboardActionResult(
            success=True,
            hotkey=f"{modifier}+w",
            keys=[modifier, "w"],
            platform=platform,
        )

    @agent.tool
    @desktop_tool("QUIT", requires="pyautogui")
    def desktop_quit(context: RunContext) -> KeyboardActionResult:
        """
        Quit current application (platform-aware).

        Uses Cmd+Q on macOS, Alt+F4 on Windows automatically.

        Returns:
            KeyboardActionResult with success status

        Example:
            desktop_quit()  # Uses correct shortcut for your OS
        """
        platform = get_platform_display_name()

        group_id = generate_group_id("desktop_quit", platform)

        if IS_MACOS:
            emit_rich(
                f"[bold cyan]QUIT[/bold cyan] ⌨️  Using command+Q ({platform})",
                message_group=group_id,
            )
            pyautogui.hotkey("command", "q")
            return KeyboardActionResult(
                success=True,
                hotkey="command+q",
                keys=["command", "q"],
                platform=platform,
            )
        else:
            emit_rich(
                f"[bold cyan]QUIT[/bold cyan] ⌨️  Using alt+F4 ({platform})",
                message_group=group_id,
            )
            pyautogui.hotkey("alt", "f4")
            return KeyboardActionResult(
                success=True,
                hotkey="alt+f4",
                keys=["alt", "f4"],
                platform=platform,
            )
