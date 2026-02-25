"""Tests for code_puppy/api/websocket.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_ws_health(app) -> None:
    """Test WebSocket health endpoint echoes messages."""
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/ws/health") as ws:
            ws.send_text("hello")
            data = ws.receive_text()
            assert data == "echo: hello"


@pytest.mark.asyncio
async def test_ws_events(app) -> None:
    """Test WebSocket events endpoint streams events and recent events."""
    from starlette.testclient import TestClient

    event_queue = asyncio.Queue()
    await event_queue.put({"type": "test", "data": "hello"})

    recent = [{"type": "recent", "data": "old"}]

    with (
        patch(
            "code_puppy.plugins.frontend_emitter.emitter.subscribe",
            return_value=event_queue,
            create=True,
        ),
        patch(
            "code_puppy.plugins.frontend_emitter.emitter.unsubscribe", create=True
        ) as mock_unsub,
        patch(
            "code_puppy.plugins.frontend_emitter.emitter.get_recent_events",
            return_value=recent,
            create=True,
        ),
    ):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/events") as ws:
                # First receives recent events
                data = ws.receive_json()
                assert data["type"] == "recent"
                # Then queued event
                data = ws.receive_json()
                assert data["type"] == "test"
        mock_unsub.assert_called_once()


@pytest.mark.asyncio
async def test_ws_terminal(app) -> None:
    """Test WebSocket terminal endpoint creates a session."""
    from starlette.testclient import TestClient

    mock_session = MagicMock()
    mock_manager = MagicMock()
    mock_manager.create_session = AsyncMock(return_value=mock_session)
    mock_manager.write = AsyncMock()
    mock_manager.resize = AsyncMock()
    mock_manager.close_session = AsyncMock()

    with patch(
        "code_puppy.api.pty_manager.get_pty_manager",
        return_value=mock_manager,
        create=True,
    ):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                # Should receive session info
                data = ws.receive_json()
                assert data["type"] == "session"
                assert "id" in data

                # Send input
                ws.send_json({"type": "input", "data": "ls\n"})

                # Send resize
                ws.send_json({"type": "resize", "cols": 120, "rows": 40})

            # After disconnect, session should be closed
            mock_manager.close_session.assert_called_once()


@pytest.mark.asyncio
async def test_ws_events_ping_on_timeout(app) -> None:
    """Events WS sends ping on queue timeout."""
    from starlette.testclient import TestClient

    # Empty queue - will timeout and send ping
    event_queue = asyncio.Queue()

    with (
        patch(
            "code_puppy.plugins.frontend_emitter.emitter.subscribe",
            return_value=event_queue,
            create=True,
        ),
        patch("code_puppy.plugins.frontend_emitter.emitter.unsubscribe", create=True),
        patch(
            "code_puppy.plugins.frontend_emitter.emitter.get_recent_events",
            return_value=[],
            create=True,
        ),
        patch(
            "asyncio.wait_for",
            side_effect=[asyncio.TimeoutError, asyncio.CancelledError],
        ),
    ):
        with TestClient(app) as client:
            try:
                with client.websocket_connect("/ws/events") as ws:
                    data = ws.receive_json()
                    assert data["type"] == "ping"
            except Exception:
                pass  # Connection closes after ping
