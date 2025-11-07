"""Type stubs for macOS Accessibility API.

⚠️ **macOS ONLY** - Not available on Windows or Linux.
Use windows_automation on Windows instead.
"""

import sys
from typing import Any

if sys.platform == "darwin":
    # Full macOS Accessibility API

    def find_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        description: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Find UI element using macOS Accessibility API.

        Args:
            role: Element role (e.g., 'AXButton', 'AXTextField')
            title: Element title/label
            description: Element description
            fuzzy: Enable fuzzy matching

        Returns:
            Dict with element info and coordinates

        Example:
            result = find_accessible_element(role="AXButton", title="Submit")
            if result["found"]:
                print(f"Found at {result['x']}, {result['y']}")
        """
        ...

    def list_accessible_elements(
        role: str | None = ...,
    ) -> list[dict[str, Any]]:
        """List all accessible elements in active window.

        Args:
            role: Filter by role (optional)

        Returns:
            List of element dictionaries

        Example:
            elements = list_accessible_elements(role="AXButton")
            for elem in elements:
                print(elem["AXTitle"])
        """
        ...

    def click_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Click UI element using Accessibility API.

        Args:
            role: Element role
            title: Element title/label
            fuzzy: Enable fuzzy matching

        Returns:
            Dict with click result

        Example:
            result = click_accessible_element(role="AXButton", title="OK")
            assert result["success"] is True
        """
        ...

else:
    # Stub for non-macOS platforms

    def find_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        description: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform.

        Use windows_automation.find_element() on Windows instead.
        """
        ...

    def list_accessible_elements(
        role: str | None = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform."""
        ...

    def click_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform."""
        ...
