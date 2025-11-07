"""Type stubs for Windows UI Automation.

⚠️ **Windows ONLY** - Not available on macOS or Linux.
Use accessibility tools on macOS instead.
"""

import sys
from typing import Any

if sys.platform == "win32":
    # Full Windows UIA API

    def list_windows() -> dict[str, Any]:
        """List all open Windows windows using UIA.

        Returns:
            Dict with window titles and automation info

        Example:
            result = list_windows()
            for window in result["windows"]:
                print(window["title"])
        """
        ...

    def focus_window(title: str) -> bool:
        """Focus a Windows window by title.

        Args:
            title: Window title to focus

        Returns:
            True if successful

        Example:
            success = focus_window("Notepad")
        """
        ...

    def find_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Find UI element using Windows UIA.

        Args:
            automation_id: Element automation ID
            name: Element name/label
            control_type: Control type (e.g., 'Button', 'Edit')
            fuzzy: Enable fuzzy matching

        Returns:
            Dict with element info and coordinates

        Example:
            result = find_element(automation_id="SubmitButton")
            if result["found"]:
                print(f"Found at {result['x']}, {result['y']}")
        """
        ...

    def click_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Click UI element using Windows UIA.

        Args:
            automation_id: Element automation ID
            name: Element name/label
            control_type: Control type
            fuzzy: Enable fuzzy matching

        Returns:
            Dict with click result

        Example:
            result = click_element(name="OK", control_type="Button")
            assert result["success"] is True
        """
        ...

    def list_elements_in_window(
        window_title: str,
        control_type: str | None = ...,
    ) -> dict[str, Any]:
        """List all UI elements in a window.

        Args:
            window_title: Window title
            control_type: Filter by control type (optional)

        Returns:
            Dict with elements list

        Example:
            result = list_elements_in_window("Calculator", control_type="Button")
            for elem in result["elements"]:
                print(elem["name"])
        """
        ...

else:
    # Stub for non-Windows platforms

    def list_windows() -> None:
        """❌ **Windows ONLY** - Not available on this platform.

        Use window_control.list_windows() on macOS instead.
        """
        ...

    def focus_window(title: str) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...

    def find_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...

    def click_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...

    def list_elements_in_window(
        window_title: str,
        control_type: str | None = ...,
    ) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...
