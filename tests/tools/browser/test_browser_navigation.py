"""Comprehensive tests for browser_navigation.py with mocking.

Tests navigation operations (navigate, go_back, go_forward, reload) without actual browser.
"""

from unittest.mock import AsyncMock, patch

import pytest

from code_puppy.tools.browser.browser_navigation import (
    get_page_info,
    go_back,
    go_forward,
    navigate_to_url,
    reload_page,
    wait_for_load_state,
)


class TestNavigateToUrl:
    """Test URL navigation functionality."""

    @pytest.mark.asyncio
    async def test_navigate_to_url_success(self):
        """Test successful navigation to a URL."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example Domain"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch(
                    "code_puppy.tools.browser.browser_navigation.emit_success"
                ) as mock_emit_success:
                    result = await navigate_to_url("https://example.com")

                    assert result["success"] is True
                    assert result["url"] == "https://example.com"
                    assert result["title"] == "Example Domain"
                    assert result["requested_url"] == "https://example.com"
                    assert mock_emit_success.called

    @pytest.mark.asyncio
    async def test_navigate_with_redirect(self):
        """Test navigation that follows redirects."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.url = "https://final-url.example.com"  # After redirect
        mock_page.title.return_value = "Final Title"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    result = await navigate_to_url("https://example.com")

                    assert result["success"] is True
                    assert result["url"] == "https://final-url.example.com"  # Final URL
                    assert result["requested_url"] == "https://example.com"  # Requested

    @pytest.mark.asyncio
    async def test_navigate_no_page_available(self):
        """Test navigation when no page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                result = await navigate_to_url("https://example.com")

                assert result["success"] is False
                assert "No active browser page" in result["error"]

    @pytest.mark.asyncio
    async def test_navigate_timeout_error(self):
        """Test navigation timeout handling."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.side_effect = TimeoutError("Navigation timeout")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_error"):
                    result = await navigate_to_url("https://slow-site.com")

                    assert result["success"] is False
                    assert "error" in result

    @pytest.mark.asyncio
    async def test_navigate_network_error(self):
        """Test handling of network errors during navigation."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.side_effect = RuntimeError("Network error")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_error"):
                    result = await navigate_to_url("https://unreachable.com")

                    assert result["success"] is False


class TestGetPageInfo:
    """Test page information retrieval."""

    @pytest.mark.asyncio
    async def test_get_page_info_success(self):
        """Test successful page info retrieval."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                result = await get_page_info()

                assert result["success"] is True
                assert result["url"] == "https://example.com"
                assert result["title"] == "Example"

    @pytest.mark.asyncio
    async def test_get_page_info_no_page(self):
        """Test page info when no page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                result = await get_page_info()

                assert result["success"] is False
                assert "No active browser page" in result["error"]


class TestGoBack:
    """Test browser back button functionality."""

    @pytest.mark.asyncio
    async def test_go_back_success(self):
        """Test successful back navigation."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.go_back.return_value = None
        mock_page.url = "https://previous.com"
        mock_page.title.return_value = "Previous Page"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    result = await go_back()

                    assert result["success"] is True
                    assert result["url"] == "https://previous.com"
                    assert result["title"] == "Previous Page"
                    assert mock_page.go_back.called

    @pytest.mark.asyncio
    async def test_go_back_no_history(self):
        """Test back navigation when no history exists."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.go_back.return_value = None
        mock_page.url = "https://current.com"
        mock_page.title.return_value = "Current Page"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    result = await go_back()

                    # Should still return success (no-op)
                    assert result["success"] is True

    @pytest.mark.asyncio
    async def test_go_back_no_page(self):
        """Test go back when no page available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                result = await go_back()

                assert result["success"] is False


class TestGoForward:
    """Test browser forward button functionality."""

    @pytest.mark.asyncio
    async def test_go_forward_success(self):
        """Test successful forward navigation."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.go_forward.return_value = None
        mock_page.url = "https://next.com"
        mock_page.title.return_value = "Next Page"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    result = await go_forward()

                    assert result["success"] is True
                    assert result["url"] == "https://next.com"


class TestReloadPage:
    """Test page reload functionality."""

    @pytest.mark.asyncio
    async def test_reload_page_success(self):
        """Test successful page reload."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.reload.return_value = None
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    result = await reload_page()

                    assert result["success"] is True
                    assert mock_page.reload.called


class TestWaitForLoadState:
    """Test page load state waiting."""

    @pytest.mark.asyncio
    async def test_wait_for_load_state_networkidle(self):
        """Test waiting for network idle state."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.wait_for_load_state.return_value = None
        mock_page.url = "https://example.com"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                result = await wait_for_load_state("networkidle")

                assert result["success"] is True


class TestNavigationIntegration:
    """Integration tests for navigation workflows."""

    @pytest.mark.asyncio
    async def test_navigate_then_get_info(self):
        """Test navigation followed by getting page info."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    # Navigate
                    nav_result = await navigate_to_url("https://example.com")
                    assert nav_result["success"] is True

                    # Get info
                    info_result = await get_page_info()
                    assert info_result["success"] is True
                    assert info_result["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_navigate_back_forward(self):
        """Test back and forward navigation workflow."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.go_back.return_value = None
        mock_page.go_forward.return_value = None
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_navigation.get_camoufox_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_navigation.emit_info"):
                with patch("code_puppy.tools.browser.browser_navigation.emit_success"):
                    # Navigate to page 1
                    await navigate_to_url("https://page1.com")

                    # Navigate to page 2
                    await navigate_to_url("https://page2.com")

                    # Go back to page 1
                    back_result = await go_back()
                    assert back_result["success"] is True

                    # Go forward to page 2
                    forward_result = await go_forward()
                    assert forward_result["success"] is True
