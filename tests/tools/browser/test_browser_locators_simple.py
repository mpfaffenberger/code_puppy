"""Simple working test for browser locators to get basic coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_locators import find_by_role


@pytest.mark.asyncio
async def test_find_by_role_basic():
    """Simple test to get basic coverage working."""
    # Mock the browser manager
    mock_manager = AsyncMock()
    mock_page = AsyncMock()
    mock_manager.get_current_page.return_value = mock_page

    # Mock the locator and element
    mock_locator = MagicMock()  # Use MagicMock for locator
    mock_locator.count = AsyncMock(return_value=1)

    # Mock locator.first as an object with wait_for method
    first_mock = MagicMock()
    first_mock.wait_for = AsyncMock()
    mock_locator.first = first_mock

    # Mock element with async methods - make them proper AsyncMock
    mock_element = AsyncMock()
    mock_element.is_visible = AsyncMock(return_value=True)
    mock_element.text_content = AsyncMock(return_value="Submit")

    mock_locator.nth = MagicMock(return_value=mock_element)

    # Fix: make sure get_by_role returns the locator mock, not a coroutine
    mock_page.get_by_role = MagicMock(return_value=mock_locator)

    with patch(
        "code_puppy.tools.browser.browser_locators.get_camoufox_manager",
        return_value=mock_manager,
    ):
        with patch(
            "code_puppy.tools.browser.browser_locators.emit_info"
        ):  # Mock emit_info to avoid side effects
            result = await find_by_role("button")

            assert result["success"] is True
            assert result["role"] == "button"
            assert result["count"] == 1


@pytest.mark.asyncio
async def test_find_by_role_no_page():
    """Test when no page is available."""
    mock_manager = AsyncMock()
    mock_manager.get_current_page.return_value = None

    with patch(
        "code_puppy.tools.browser.browser_locators.get_camoufox_manager",
        return_value=mock_manager,
    ):
        with patch("code_puppy.tools.browser.browser_locators.emit_info"):
            result = await find_by_role("button")

            assert result["success"] is False
            assert "No active browser page" in result["error"]


@pytest.mark.asyncio
async def test_find_by_role_exception():
    """Test exception handling."""
    mock_manager = AsyncMock()
    mock_manager.get_current_page.side_effect = Exception("Browser error")

    with patch(
        "code_puppy.tools.browser.browser_locators.get_camoufox_manager",
        return_value=mock_manager,
    ):
        with patch("code_puppy.tools.browser.browser_locators.emit_info"):
            result = await find_by_role("button")

            assert result["success"] is False
            assert "Browser error" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__])
