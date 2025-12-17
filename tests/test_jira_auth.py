"""Unit tests for Jira authentication module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.plugins.walmart_specific.jira_auth import (
    JIRA_COOKIES_FILE,
    JIRA_URL,
    _get_code_puppy_chrome_profile_path,
    _scrape_jira_session_playwright,
    get_jira_auth_help,
    handle_jira_auth_command,
    handle_jira_test_command,
    validate_jira_auth,
)


class TestPlaywrightImportFallback:
    """Test the playwright import fallback."""

    def test_async_playwright_none_when_import_fails(self):
        """Test that async_playwright is None when import fails."""
        # This tests lines 17-18 - we can test by checking what happens
        # when async_playwright is None
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright", None
        ):
            result = handle_jira_auth_command("/jira_auth", "jira_auth")
            assert "Playwright" in result


class TestChromeProfilePath:
    """Test suite for Chrome profile path handling."""

    def test_get_chrome_profile_path_returns_path(self):
        """Test that _get_code_puppy_chrome_profile_path returns a Path object."""
        profile_path = _get_code_puppy_chrome_profile_path()
        assert isinstance(profile_path, Path)
        assert "chrome_profile" in str(profile_path)

    @patch("pathlib.Path.mkdir")
    def test_get_chrome_profile_path_creates_directory(self, mock_mkdir):
        """Test that the profile directory is created if it doesn't exist."""
        _get_code_puppy_chrome_profile_path()
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestScrapeJiraSession:
    """Test suite for Jira session scraping."""

    @pytest.mark.asyncio
    async def test_scrape_jira_session_playwright_not_installed(self):
        """Test that scraper raises error when Playwright is not installed."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright", None
        ):
            with pytest.raises(RuntimeError, match="Playwright is not installed"):
                await _scrape_jira_session_playwright()

    @pytest.mark.asyncio
    async def test_scrape_jira_session_successful_auth(self):
        """Test successful Jira authentication and cookie extraction."""
        # Mock Playwright components
        mock_page = AsyncMock()
        mock_page.url = "https://jira.walmart.com/secure/Dashboard.jspa"
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        # Simulate authentication cookies being present
        mock_cookies = [
            {"name": "JSESSIONID", "value": "test-session-id"},
            {"name": "seraph.jira", "value": "test-seraph"},
            {"name": "atlassian.xsrf.token", "value": "test-xsrf"},
            {"name": "other-cookie", "value": "test-other"},
        ]
        mock_context.cookies = AsyncMock(return_value=mock_cookies)

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            # Mock asyncio.sleep to speed up test
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _scrape_jira_session_playwright()

        # Verify result structure
        assert "cookies" in result
        assert "all_cookies" in result
        assert "url" in result
        assert "base_url" in result
        assert "timestamp" in result

        # Verify important cookies were extracted
        assert "JSESSIONID" in result["cookies"]
        assert "seraph.jira" in result["cookies"]
        assert "atlassian.xsrf.token" in result["cookies"]

        # Verify all cookies were stored
        assert len(result["all_cookies"]) == 4

        # Verify base URL
        assert result["base_url"] == "https://jira.walmart.com"

    @pytest.mark.asyncio
    async def test_scrape_jira_session_timeout(self):
        """Test that scraper raises TimeoutError when auth times out."""
        mock_page = AsyncMock()
        mock_page.url = "https://jira.walmart.com/login.jsp"
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        # No authentication cookies present
        mock_context.cookies = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            # Mock time.time to simulate timeout immediately
            with patch("time.time") as mock_time:
                mock_time.side_effect = [0, 400]  # Start time, then past timeout

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with pytest.raises(TimeoutError, match="Authentication timed out"):
                        await _scrape_jira_session_playwright()


class TestHandleJiraAuthCommand:
    """Test suite for Jira auth command handler."""

    def test_handle_jira_auth_command_wrong_name(self):
        """Test that handler returns None for non-jira_auth commands."""
        result = handle_jira_auth_command("/other_command", "other_command")
        assert result is None

    def test_handle_jira_auth_command_playwright_not_installed(self):
        """Test that handler returns error when Playwright is not installed."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright", None
        ):
            result = handle_jira_auth_command("/jira_auth", "jira_auth")
            assert "Playwright is required" in result

    def test_handle_jira_auth_command_success(self, tmp_path):
        """Test successful Jira authentication command."""
        # Mock the async scraper to return fake cookies
        mock_result = {
            "cookies": {"JSESSIONID": "test-session"},
            "all_cookies": {"JSESSIONID": "test-session"},
            "url": "https://jira.walmart.com/secure/Dashboard.jspa",
            "base_url": "https://jira.walmart.com",
            "timestamp": "2025-01-01T12:00:00",
        }

        async def mock_scraper():
            return mock_result

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth._scrape_jira_session_playwright",
            new=mock_scraper,
        ):
            # Mock the event loop
            mock_loop = Mock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete.return_value = mock_result

            with patch("asyncio.get_event_loop", return_value=mock_loop):
                # Mock file writing
                mock_cookies_file = tmp_path / "jira.json"
                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
                    mock_cookies_file,
                ):
                    result = handle_jira_auth_command("/jira_auth", "jira_auth")

                    # Verify success message
                    assert "successful" in result.lower()

                    # Verify cookies were written to file
                    assert mock_cookies_file.exists()
                    with open(mock_cookies_file) as f:
                        saved_data = json.load(f)
                        assert saved_data == mock_result

    def test_handle_jira_auth_command_exception(self):
        """Test that handler gracefully handles exceptions."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth._scrape_jira_session_playwright"
        ) as mock_scraper:
            mock_scraper.side_effect = Exception("Test error")

            mock_loop = Mock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete.side_effect = Exception("Test error")

            with patch("asyncio.get_event_loop", return_value=mock_loop):
                result = handle_jira_auth_command("/jira_auth", "jira_auth")
                assert "failed" in result.lower()
                assert "Test error" in result


class TestGetJiraAuthHelp:
    """Test suite for Jira auth help function."""

    def test_get_jira_auth_help_returns_list(self):
        """Test that help function returns a list of tuples."""
        result = get_jira_auth_help()
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(item, tuple) for item in result)

    def test_get_jira_auth_help_contains_jira_auth(self):
        """Test that help includes the jira_auth command."""
        result = get_jira_auth_help()
        command_names = [item[0] for item in result]
        assert "jira_auth" in command_names

    def test_get_jira_auth_help_has_descriptions(self):
        """Test that each command has a description."""
        result = get_jira_auth_help()
        for command, description in result:
            assert isinstance(command, str)
            assert isinstance(description, str)
            assert len(description) > 0


class TestJiraAuthConstants:
    """Test suite for Jira auth module constants."""

    def test_jira_url_constant(self):
        """Test that JIRA_URL is correctly defined."""
        assert JIRA_URL == "https://jira.walmart.com/"

    def test_jira_cookies_file_constant(self):
        """Test that JIRA_COOKIES_FILE points to correct location."""
        assert isinstance(JIRA_COOKIES_FILE, Path)
        assert "jira.json" in str(JIRA_COOKIES_FILE)
        assert ".code_puppy" in str(JIRA_COOKIES_FILE)


class TestValidateJiraAuth:
    """Test suite for Jira auth validation."""

    def test_validate_jira_auth_no_session_file(self, tmp_path):
        """Test validation fails when no session file exists."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            tmp_path / "nonexistent.json",
        ):
            result = validate_jira_auth()
            assert result["success"] is False
            assert "No Jira session found" in result["error"]

    def test_validate_jira_auth_invalid_json(self, tmp_path):
        """Test validation fails with invalid JSON in session file."""
        session_file = tmp_path / "jira.json"
        session_file.write_text("not valid json")

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            result = validate_jira_auth()
            assert result["success"] is False
            assert "Failed to load session file" in result["error"]

    def test_validate_jira_auth_success(self, tmp_path):
        """Test successful auth validation."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "test-session"},
            "all_cookies": {"JSESSIONID": "test-session", "other": "cookie"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "testuser",
            "displayName": "Test User",
            "emailAddress": "test@walmart.com",
        }

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_client.return_value.__enter__ = Mock(
                    return_value=Mock(get=Mock(return_value=mock_response))
                )
                mock_client.return_value.__exit__ = Mock(return_value=None)

                result = validate_jira_auth()

                assert result["success"] is True
                assert result["user"] == "testuser"
                assert result["display_name"] == "Test User"
                assert result["email"] == "test@walmart.com"

    def test_validate_jira_auth_expired_session(self, tmp_path):
        """Test validation detects expired session."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "expired-session"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 401

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_client.return_value.__enter__ = Mock(
                    return_value=Mock(get=Mock(return_value=mock_response))
                )
                mock_client.return_value.__exit__ = Mock(return_value=None)

                result = validate_jira_auth()

                assert result["success"] is False
                assert "expired" in result["error"].lower()


class TestHandleJiraTestCommand:
    """Test suite for /jira_test command handler."""

    def test_handle_jira_test_command_wrong_name(self):
        """Test that handler returns None for non-jira_test commands."""
        result = handle_jira_test_command("/other_command", "other_command")
        assert result is None

    def test_handle_jira_test_command_success(self):
        """Test successful jira_test command."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.validate_jira_auth"
        ) as mock_validate:
            mock_validate.return_value = {
                "success": True,
                "user": "testuser",
                "display_name": "Test User",
                "email": "test@walmart.com",
            }

            result = handle_jira_test_command("/jira_test", "jira_test")

            assert "Test User" in result
            assert "testuser" in result

    def test_handle_jira_test_command_failure(self):
        """Test jira_test command with invalid auth."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.validate_jira_auth"
        ) as mock_validate:
            mock_validate.return_value = {
                "success": False,
                "error": "Session expired",
            }

            result = handle_jira_test_command("/jira_test", "jira_test")

            assert "Session expired" in result


class TestValidateJiraAuthDebugMode:
    """Test suite for debug mode in validate_jira_auth."""

    def test_validate_jira_auth_debug_output(self, tmp_path):
        """Test that debug mode emits debug information."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "test-session"},
            "all_cookies": {"JSESSIONID": "test-session", "other": "cookie"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "testuser",
            "displayName": "Test User",
            "emailAddress": "test@walmart.com",
        }
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.emit_info"
            ) as mock_emit:
                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
                ) as mock_client:
                    mock_instance = Mock()
                    mock_instance.get.return_value = mock_response
                    mock_client.return_value.__enter__ = Mock(
                        return_value=mock_instance
                    )
                    mock_client.return_value.__exit__ = Mock(return_value=None)

                    result = validate_jira_auth(debug=True)

                    assert result["success"] is True
                    # Verify debug info was emitted (at least for cookies, names, base_url)
                    assert mock_emit.call_count >= 3

    def test_validate_jira_auth_debug_on_401(self, tmp_path):
        """Test debug output on 401 response."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "all_cookies": {"JSESSIONID": "expired"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.emit_info"
            ) as mock_emit:
                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
                ) as mock_client:
                    mock_instance = Mock()
                    mock_instance.get.return_value = mock_response
                    mock_client.return_value.__enter__ = Mock(
                        return_value=mock_instance
                    )
                    mock_client.return_value.__exit__ = Mock(return_value=None)

                    result = validate_jira_auth(debug=True)

                    assert result["success"] is False
                    # Should emit response body in debug mode
                    debug_calls = [str(c) for c in mock_emit.call_args_list]
                    assert any(
                        "Response" in str(c) or "Debug" in str(c) for c in debug_calls
                    )

    def test_validate_jira_auth_other_http_error(self, tmp_path):
        """Test handling of non-401/403 HTTP errors."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "all_cookies": {"JSESSIONID": "test"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_instance = Mock()
                mock_instance.get.return_value = mock_response
                mock_client.return_value.__enter__ = Mock(return_value=mock_instance)
                mock_client.return_value.__exit__ = Mock(return_value=None)

                result = validate_jira_auth(debug=False)

                assert result["success"] is False
                assert "500" in result["error"]

    def test_validate_jira_auth_other_http_error_debug(self, tmp_path):
        """Test debug output on other HTTP errors."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "all_cookies": {"JSESSIONID": "test"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.emit_info"
            ) as mock_emit:
                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
                ) as mock_client:
                    mock_instance = Mock()
                    mock_instance.get.return_value = mock_response
                    mock_client.return_value.__enter__ = Mock(
                        return_value=mock_instance
                    )
                    mock_client.return_value.__exit__ = Mock(return_value=None)

                    result = validate_jira_auth(debug=True)

                    assert result["success"] is False
                    # Should emit response body in debug mode
                    debug_calls = [str(c) for c in mock_emit.call_args_list]
                    assert any(
                        "Response" in str(c) or "Debug" in str(c) for c in debug_calls
                    )

    def test_validate_jira_auth_connection_error(self, tmp_path):
        """Test handling of connection errors."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "all_cookies": {"JSESSIONID": "test"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_client.return_value.__enter__ = Mock(
                    side_effect=Exception("Connection refused")
                )

                result = validate_jira_auth()

                assert result["success"] is False
                assert "Connection error" in result["error"]

    def test_validate_jira_auth_fallback_to_cookies(self, tmp_path):
        """Test fallback to 'cookies' when 'all_cookies' is missing."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "test-session"},
            # No all_cookies key
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "testuser",
            "displayName": "Test User",
        }

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_instance = Mock()
                mock_instance.get.return_value = mock_response
                mock_client.return_value.__enter__ = Mock(return_value=mock_instance)
                mock_client.return_value.__exit__ = Mock(return_value=None)

                result = validate_jira_auth()

                assert result["success"] is True


class TestHandleJiraTestCommandDebug:
    """Test debug flag handling in jira_test command."""

    def test_handle_jira_test_command_with_debug_flag(self):
        """Test that debug flag is passed to validate_jira_auth."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.validate_jira_auth"
        ) as mock_validate:
            mock_validate.return_value = {
                "success": True,
                "user": "testuser",
                "display_name": "Test User",
                "email": "test@walmart.com",
            }

            handle_jira_test_command("/jira_test debug", "jira_test")

            mock_validate.assert_called_once_with(debug=True)

    def test_handle_jira_test_command_without_debug_flag(self):
        """Test that debug=False when no debug flag."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.validate_jira_auth"
        ) as mock_validate:
            mock_validate.return_value = {
                "success": True,
                "user": "testuser",
                "display_name": "Test User",
                "email": "test@walmart.com",
            }

            handle_jira_test_command("/jira_test", "jira_test")

            mock_validate.assert_called_once_with(debug=False)


class TestHandleJiraAuthEventLoop:
    """Test event loop handling in handle_jira_auth_command."""

    def test_handle_jira_auth_with_running_loop(self, tmp_path):
        """Test auth command when event loop is already running."""
        mock_result = {
            "cookies": {"JSESSIONID": "test-session"},
            "all_cookies": {"JSESSIONID": "test-session"},
            "url": "https://jira.walmart.com/",
            "base_url": "https://jira.walmart.com",
            "timestamp": "2025-01-01T12:00:00",
        }

        cookies_file = tmp_path / "jira.json"

        # Mock a running event loop
        mock_loop = Mock()
        mock_loop.is_running.return_value = True

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            cookies_file,
        ):
            # Patch asyncio at module level (imported inside function)
            with patch("asyncio.get_event_loop", return_value=mock_loop):
                with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
                    mock_future = Mock()
                    mock_future.result.return_value = mock_result
                    mock_context = Mock()
                    mock_context.submit.return_value = mock_future
                    mock_executor.return_value.__enter__ = Mock(
                        return_value=mock_context
                    )
                    mock_executor.return_value.__exit__ = Mock(return_value=None)

                    result = handle_jira_auth_command("/jira_auth", "jira_auth")

                    assert "successful" in result.lower()
                    # Verify the executor was used (running loop branch)
                    mock_context.submit.assert_called_once()


class TestScrapeJiraSessionEdgeCases:
    """Test edge cases in _scrape_jira_session_playwright."""

    @pytest.mark.asyncio
    async def test_scrape_jira_session_url_fallback_auth(self):
        """Test URL-based authentication fallback."""
        mock_page = AsyncMock()
        # First URL check shows jira.walmart.com without login
        mock_page.url = "https://jira.walmart.com/secure/Dashboard.jspa"
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.close = AsyncMock()

        # First call returns no auth cookies, second call (after URL check) returns them
        call_count = 0

        async def mock_cookies():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # No cookies initially
            else:
                # After URL fallback check, return auth cookies
                return [
                    {"name": "JSESSIONID", "value": "test-session"},
                    {"name": "atlassian.xsrf.token", "value": "test-xsrf"},
                ]

        mock_context.cookies = mock_cookies

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _scrape_jira_session_playwright()

        assert "cookies" in result
        assert "JSESSIONID" in result["cookies"]

    @pytest.mark.asyncio
    async def test_scrape_jira_session_no_important_cookies_fallback(self):
        """Test fallback when no important cookies are found.

        This tests the code path where we have cookies that trigger auth detection
        but after extraction, none match the 'important' list, so we fallback
        to storing all cookies.
        """
        mock_page = AsyncMock()
        mock_page.url = "https://jira.walmart.com/secure/Dashboard.jspa"
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.close = AsyncMock()

        # Return cookies that have atlassian for auth detection
        # but none match the "important" cookies list exactly
        only_non_important_cookies = [
            {"name": "atlassian.something.else", "value": "triggers-auth"},
            {"name": "random_cookie", "value": "random_value"},
        ]

        mock_context.cookies = AsyncMock(return_value=only_non_important_cookies)

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch("code_puppy.plugins.walmart_specific.jira_auth.emit_info"):
                    result = await _scrape_jira_session_playwright()

        # Should fallback to all_cookies since no important cookies matched
        assert "all_cookies" in result
        assert "cookies" in result
        # When no important cookies match, cookies dict should equal all_cookies
        assert result["cookies"] == result["all_cookies"]
        assert len(result["all_cookies"]) == 2


class TestJiraAuthIntegration:
    @pytest.mark.asyncio
    async def test_full_auth_workflow_simulation(self, tmp_path):
        """Simulate a full authentication workflow from command to file save."""
        # Setup temp cookies file
        mock_cookies_file = tmp_path / "jira.json"

        # Mock successful authentication
        mock_cookies = [
            {"name": "JSESSIONID", "value": "abc123"},
            {"name": "seraph.jira", "value": "xyz789"},
        ]

        mock_page = AsyncMock()
        mock_page.url = "https://jira.walmart.com/secure/Dashboard.jspa"
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.cookies = AsyncMock(return_value=mock_cookies)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Run scraper
                result = await _scrape_jira_session_playwright()

                # Verify result
                assert "JSESSIONID" in result["cookies"]
                assert "seraph.jira" in result["cookies"]

                # Simulate saving to file
                with open(mock_cookies_file, "w") as f:
                    json.dump(result, f, indent=2)

                # Verify file was created and contains correct data
                assert mock_cookies_file.exists()
                with open(mock_cookies_file) as f:
                    saved_data = json.load(f)
                    assert saved_data["cookies"]["JSESSIONID"] == "abc123"
                    assert saved_data["cookies"]["seraph.jira"] == "xyz789"


class TestScrapeJiraSessionTimeout:
    """Test timeout handling in _scrape_jira_session_playwright."""

    @pytest.mark.asyncio
    async def test_scrape_jira_session_timeout(self):
        """Test that timeout error is raised when auth takes too long."""
        mock_page = AsyncMock()
        mock_page.url = "https://login.walmart.com"  # Still on login page
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.close = AsyncMock()
        # Always return empty cookies (no auth detected)
        mock_context.cookies = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_browser
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright.return_value = mock_playwright

            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Mock time to exceed timeout
                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.AUTH_WAIT_TIMEOUT", 0
                ):
                    with patch("time.time") as mock_time:
                        # Simulate time passing beyond timeout
                        mock_time.side_effect = [
                            0,
                            1,
                            2,
                        ]  # Start, first check, past timeout

                        with pytest.raises(TimeoutError) as exc_info:
                            await _scrape_jira_session_playwright()

                        assert "timed out" in str(exc_info.value).lower()


class TestValidateJiraAuthDebugResponseBody:
    """Test debug response body output - covers lines 358 and 365."""

    def test_validate_jira_auth_403_debug_response_body(self, tmp_path):
        """Test debug output includes response body on 403."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "expired"},
            "all_cookies": {"JSESSIONID": "expired", "other": "cookie"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden - Access Denied"
        mock_response.headers = {"content-type": "text/plain"}

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_client.return_value.__enter__ = Mock(
                    return_value=Mock(get=Mock(return_value=mock_response))
                )
                mock_client.return_value.__exit__ = Mock(return_value=None)

                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.emit_info"
                ) as mock_emit:
                    result = validate_jira_auth(debug=True)

                    assert result["success"] is False
                    assert "403" in result["error"]
                    # Verify debug emitted response body
                    emit_calls = [str(c) for c in mock_emit.call_args_list]
                    assert any("Forbidden" in str(c) for c in emit_calls)

    def test_validate_jira_auth_502_debug_response_body(self, tmp_path):
        """Test debug output includes response body on 502."""
        session_file = tmp_path / "jira.json"
        session_data = {
            "cookies": {"JSESSIONID": "test"},
            "all_cookies": {"JSESSIONID": "test", "other": "cookie"},
            "base_url": "https://jira.walmart.com",
        }
        session_file.write_text(json.dumps(session_data))

        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway - Upstream server error"
        mock_response.headers = {"content-type": "text/plain"}

        with patch(
            "code_puppy.plugins.walmart_specific.jira_auth.JIRA_COOKIES_FILE",
            session_file,
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_auth.httpx.Client"
            ) as mock_client:
                mock_client.return_value.__enter__ = Mock(
                    return_value=Mock(get=Mock(return_value=mock_response))
                )
                mock_client.return_value.__exit__ = Mock(return_value=None)

                with patch(
                    "code_puppy.plugins.walmart_specific.jira_auth.emit_info"
                ) as mock_emit:
                    result = validate_jira_auth(debug=True)

                    assert result["success"] is False
                    assert "502" in result["error"]
                    # Verify debug emitted response body
                    emit_calls = [str(c) for c in mock_emit.call_args_list]
                    assert any("Bad Gateway" in str(c) for c in emit_calls)
