"""Comprehensive tests for terminal_tools.py.

Tests terminal server health check, terminal open/close operations
with extensive mocking to avoid actual browser and network operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from code_puppy.tools.browser.terminal_tools import (
    HEALTH_CHECK_TIMEOUT,
    TERMINAL_LOAD_TIMEOUT,
    check_terminal_server,
    close_terminal,
    open_terminal,
)


class TestCheckTerminalServer:
    """Tests for check_terminal_server function."""

    @pytest.mark.asyncio
    async def test_check_server_healthy(self):
        """Test successful health check when server is running."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_tools.emit_success"
                ) as mock_success:
                    result = await check_terminal_server()

                    assert result["success"] is True
                    assert result["server_url"] == "http://localhost:8765"
                    assert result["status"] == "healthy"
                    assert mock_success.called

    @pytest.mark.asyncio
    async def test_check_server_custom_host_port(self):
        """Test health check with custom host and port."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                    result = await check_terminal_server(
                        host="192.168.1.100", port=9000
                    )

                    assert result["success"] is True
                    assert result["server_url"] == "http://192.168.1.100:9000"
                    mock_client.get.assert_called_once_with(
                        "http://192.168.1.100:9000/health"
                    )

    @pytest.mark.asyncio
    async def test_check_server_not_running(self):
        """Test health check when server is not running."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_tools.emit_error"
                ) as mock_error:
                    result = await check_terminal_server()

                    assert result["success"] is False
                    assert "Server not running" in result["error"]
                    assert mock_error.called

    @pytest.mark.asyncio
    async def test_check_server_timeout(self):
        """Test health check when connection times out."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                    result = await check_terminal_server()

                    assert result["success"] is False
                    assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_check_server_http_error(self):
        """Test health check when server returns HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                    result = await check_terminal_server()

                    assert result["success"] is False
                    assert "error status 500" in result["error"]

    @pytest.mark.asyncio
    async def test_check_server_unexpected_health_response(self):
        """Test when server responds but with unexpected health status."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "degraded"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                    result = await check_terminal_server()

                    assert result["success"] is False
                    assert "Unexpected health response" in result["error"]

    @pytest.mark.asyncio
    async def test_check_server_unexpected_exception(self):
        """Test handling of unexpected exceptions."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = RuntimeError("Something unexpected")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                    result = await check_terminal_server()

                    assert result["success"] is False
                    assert "Failed to check server health" in result["error"]


class TestOpenTerminal:
    """Tests for open_terminal function."""

    @pytest.mark.asyncio
    async def test_open_terminal_success(self):
        """Test successful terminal opening."""
        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8765/terminal"
        mock_page.title.return_value = "Code Puppy Terminal"
        mock_page.wait_for_selector = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://localhost:8765",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                        result = await open_terminal()

                        assert result["success"] is True
                        assert result["url"] == "http://localhost:8765/terminal"
                        assert result["page_title"] == "Code Puppy Terminal"
                        mock_manager.async_initialize.assert_called_once()
                        mock_page.goto.assert_called_once_with(
                            "http://localhost:8765/terminal"
                        )

    @pytest.mark.asyncio
    async def test_open_terminal_custom_host_port(self):
        """Test opening terminal with custom host and port."""
        mock_page = AsyncMock()
        mock_page.url = "http://192.168.1.100:9000/terminal"
        mock_page.title.return_value = "Terminal"
        mock_page.wait_for_selector = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://192.168.1.100:9000",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                        result = await open_terminal(host="192.168.1.100", port=9000)

                        assert result["success"] is True
                        mock_page.goto.assert_called_once_with(
                            "http://192.168.1.100:9000/terminal"
                        )

    @pytest.mark.asyncio
    async def test_open_terminal_server_not_running(self):
        """Test opening terminal when server is not running."""
        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": False,
                "error": "Server not running at http://localhost:8765.",
            },
        ):
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                result = await open_terminal()

                assert result["success"] is False
                assert "Cannot open terminal" in result["error"]
                assert "Please start the API server" in result["error"]

    @pytest.mark.asyncio
    async def test_open_terminal_xterm_timeout(self):
        """Test that terminal still opens even if xterm.js selector times out."""
        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8765/terminal"
        mock_page.title.return_value = "Terminal"
        mock_page.wait_for_selector.side_effect = Exception(
            "Timeout waiting for selector"
        )
        mock_page.goto = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://localhost:8765",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                        result = await open_terminal()

                        # Should still succeed, just with a warning logged
                        assert result["success"] is True
                        assert result["url"] == "http://localhost:8765/terminal"

    @pytest.mark.asyncio
    async def test_open_terminal_browser_init_error(self):
        """Test error handling when browser initialization fails."""
        mock_manager = AsyncMock()
        mock_manager.async_initialize.side_effect = RuntimeError("Browser init failed")

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://localhost:8765",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_tools.emit_error"
                    ) as mock_error:
                        result = await open_terminal()

                        assert result["success"] is False
                        assert "Failed to open terminal" in result["error"]
                        assert mock_error.called

    @pytest.mark.asyncio
    async def test_open_terminal_navigation_error(self):
        """Test error handling when page navigation fails."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = RuntimeError("Navigation failed")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://localhost:8765",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                        result = await open_terminal()

                        assert result["success"] is False
                        assert "Failed to open terminal" in result["error"]


class TestCloseTerminal:
    """Tests for close_terminal function."""

    @pytest.mark.asyncio
    async def test_close_terminal_success(self):
        """Test successful terminal closing."""
        mock_manager = AsyncMock()
        mock_manager.close.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_tools.emit_success"
                ) as mock_success:
                    result = await close_terminal()

                    assert result["success"] is True
                    assert result["message"] == "Terminal closed"
                    mock_manager.close.assert_called_once()
                    assert mock_success.called

    @pytest.mark.asyncio
    async def test_close_terminal_error(self):
        """Test error handling when close fails."""
        mock_manager = AsyncMock()
        mock_manager.close.side_effect = RuntimeError("Close failed")

        with patch(
            "code_puppy.tools.browser.terminal_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_tools.emit_error"
                ) as mock_error:
                    result = await close_terminal()

                    assert result["success"] is False
                    assert "Failed to close terminal" in result["error"]
                    assert mock_error.called

    @pytest.mark.asyncio
    async def test_close_terminal_already_closed(self):
        """Test closing when browser is already closed."""
        mock_manager = AsyncMock()
        mock_manager.close.side_effect = RuntimeError("Browser already closed")

        with patch(
            "code_puppy.tools.browser.terminal_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                with patch("code_puppy.tools.browser.terminal_tools.emit_error"):
                    result = await close_terminal()

                    assert result["success"] is False
                    assert "error" in result


class TestToolRegistration:
    """Tests for tool registration functions."""

    def test_register_check_terminal_server(self):
        """Test that check_terminal_server registration works."""
        from code_puppy.tools.browser.terminal_tools import (
            register_check_terminal_server,
        )

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_check_terminal_server(mock_agent)

        # Verify agent.tool was used as a decorator
        assert mock_agent.tool.called

    def test_register_open_terminal(self):
        """Test that open_terminal registration works."""
        from code_puppy.tools.browser.terminal_tools import register_open_terminal

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_open_terminal(mock_agent)

        assert mock_agent.tool.called

    def test_register_close_terminal(self):
        """Test that close_terminal registration works."""
        from code_puppy.tools.browser.terminal_tools import register_close_terminal

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_close_terminal(mock_agent)

        assert mock_agent.tool.called


class TestConstants:
    """Tests for module constants."""

    def test_health_check_timeout_is_reasonable(self):
        """Test that health check timeout is a reasonable value."""
        assert HEALTH_CHECK_TIMEOUT > 0
        assert HEALTH_CHECK_TIMEOUT <= 30  # Should not be too long

    def test_terminal_load_timeout_is_reasonable(self):
        """Test that terminal load timeout is a reasonable value."""
        assert TERMINAL_LOAD_TIMEOUT > 0
        assert TERMINAL_LOAD_TIMEOUT <= 60000  # Should not be more than 60 seconds


class TestIntegrationScenarios:
    """Integration-like tests for full workflows."""

    @pytest.mark.asyncio
    async def test_open_and_close_workflow(self):
        """Test typical open → use → close workflow."""
        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8765/terminal"
        mock_page.title.return_value = "Terminal"
        mock_page.wait_for_selector = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.new_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
            return_value={
                "success": True,
                "server_url": "http://localhost:8765",
                "status": "healthy",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                        # Open terminal
                        open_result = await open_terminal()
                        assert open_result["success"] is True

                        # Close terminal
                        close_result = await close_terminal()
                        assert close_result["success"] is True

    @pytest.mark.asyncio
    async def test_check_then_open_workflow(self):
        """Test check server before opening."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_page = AsyncMock()
        mock_page.url = "http://localhost:8765/terminal"
        mock_page.title.return_value = "Terminal"
        mock_page.wait_for_selector = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.new_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_tools.httpx.AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value = mock_client
            with patch(
                "code_puppy.tools.browser.terminal_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch("code_puppy.tools.browser.terminal_tools.emit_info"):
                    with patch("code_puppy.tools.browser.terminal_tools.emit_success"):
                        # First check server
                        check_result = await check_terminal_server()
                        assert check_result["success"] is True

                        # Then open (this will check again internally)
                        # Need to re-patch for the internal check
                        with patch(
                            "code_puppy.tools.browser.terminal_tools.check_terminal_server",
                            return_value={
                                "success": True,
                                "server_url": "http://localhost:8765",
                                "status": "healthy",
                            },
                        ):
                            open_result = await open_terminal()
                            assert open_result["success"] is True
