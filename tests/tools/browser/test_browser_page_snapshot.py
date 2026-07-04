"""Tests for the DOM-first page snapshot tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_page_snapshot import (
    get_page_snapshot,
    register_get_page_snapshot,
)


@pytest.mark.asyncio
async def test_get_page_snapshot_success():
    """Snapshot returns structured DOM state on the happy path."""
    fake_snapshot = {
        "url": "https://example.com/",
        "title": "Example",
        "visible_text": "Hello world",
        "headings": [{"level": "h1", "text": "Welcome"}],
        "buttons": [{"name": "Submit", "disabled": False}],
        "links": [{"text": "Home", "href": "/"}],
        "inputs": [{"tag": "input", "type": "text", "value": ""}],
        "landmarks": [{"role": "main", "label": None}],
    }

    mock_manager = AsyncMock()
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=fake_snapshot)
    mock_manager.get_current_page.return_value = mock_page

    with patch(
        "code_puppy.tools.browser.browser_page_snapshot.get_session_browser_manager",
        return_value=mock_manager,
    ):
        with patch("code_puppy.tools.browser.browser_page_snapshot.emit_info"):
            with patch("code_puppy.tools.browser.browser_page_snapshot.emit_success"):
                result = await get_page_snapshot(limit=10)

    assert result["success"] is True
    assert result["url"] == "https://example.com/"
    assert result["buttons"][0]["name"] == "Submit"
    # limit forwarded to the JS evaluate call
    mock_page.evaluate.assert_awaited_once()
    assert mock_page.evaluate.await_args.args[1] == 10


@pytest.mark.asyncio
async def test_get_page_snapshot_no_page():
    """Returns an error dict when no page is active."""
    mock_manager = AsyncMock()
    mock_manager.get_current_page.return_value = None

    with patch(
        "code_puppy.tools.browser.browser_page_snapshot.get_session_browser_manager",
        return_value=mock_manager,
    ):
        with patch("code_puppy.tools.browser.browser_page_snapshot.emit_info"):
            result = await get_page_snapshot()

    assert result["success"] is False
    assert "No active browser page" in result["error"]


@pytest.mark.asyncio
async def test_get_page_snapshot_exception():
    """Exceptions are surfaced as an error dict, not raised."""
    mock_manager = AsyncMock()
    mock_manager.get_current_page.side_effect = Exception("boom")

    with patch(
        "code_puppy.tools.browser.browser_page_snapshot.get_session_browser_manager",
        return_value=mock_manager,
    ):
        with patch("code_puppy.tools.browser.browser_page_snapshot.emit_info"):
            result = await get_page_snapshot()

    assert result["success"] is False
    assert "boom" in result["error"]


def test_register_get_page_snapshot():
    """Registration attaches a tool to the agent."""
    agent = MagicMock()
    register_get_page_snapshot(agent)
    agent.tool.assert_called_once()
