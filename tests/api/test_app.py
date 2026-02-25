"""Tests for code_puppy/api/app.py - FastAPI application factory."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from code_puppy.api.app import REQUEST_TIMEOUT, TimeoutMiddleware, create_app, lifespan


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_root(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Code Puppy" in resp.text
    assert "Open Terminal" in resp.text


@pytest.mark.asyncio
async def test_terminal_page_exists(client: AsyncClient) -> None:
    resp = await client.get("/terminal")
    # Template file exists in the source tree
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_terminal_page_not_found(app: FastAPI) -> None:
    """When template file doesn't exist, returns 404 HTML."""
    with patch("pathlib.Path.exists", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/terminal")
            assert resp.status_code == 404
            assert "not found" in resp.text.lower()


def test_create_app_returns_fastapi() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Code Puppy API"


@pytest.mark.asyncio
async def test_timeout_middleware_allows_normal_requests() -> None:
    """Normal requests pass through without timeout."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_startup_shutdown() -> None:
    """Test lifespan context manager runs startup and shutdown."""
    app = FastAPI()

    mock_manager = MagicMock()
    mock_manager.close_all = AsyncMock()

    with patch(
        "code_puppy.api.app.get_pty_manager", return_value=mock_manager, create=True
    ):
        with patch("code_puppy.api.app.Path") as mock_path_cls:
            mock_pid = MagicMock()
            mock_pid.exists.return_value = True
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_pid)

            # Patch the imports inside lifespan
            with patch.dict(
                "sys.modules",
                {
                    "code_puppy.api.pty_manager": MagicMock(
                        get_pty_manager=MagicMock(return_value=mock_manager)
                    ),
                    "code_puppy.config": MagicMock(STATE_DIR="/tmp/test_state"),
                },
            ):
                async with lifespan(app):
                    pass  # startup done
                # shutdown done


@pytest.mark.asyncio
async def test_lifespan_shutdown_handles_errors() -> None:
    """Lifespan shutdown handles exceptions gracefully."""
    app = FastAPI()

    with patch.dict(
        "sys.modules",
        {
            "code_puppy.api.pty_manager": MagicMock(
                get_pty_manager=MagicMock(side_effect=Exception("boom"))
            ),
            "code_puppy.config": MagicMock(STATE_DIR="/nonexistent"),
        },
    ):
        async with lifespan(app):
            pass
        # Should not raise


def test_request_timeout_constant() -> None:
    assert REQUEST_TIMEOUT == 30.0


@pytest.mark.asyncio
async def test_timeout_middleware_returns_504() -> None:
    """Slow endpoint triggers 504 from timeout middleware."""
    from starlette.responses import PlainTextResponse

    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout=0.01)

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(10)
        return PlainTextResponse("done")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/slow")
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_timeout_middleware_skips_websocket_upgrade() -> None:
    """Requests with upgrade:websocket header skip timeout."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # A regular request to /ws/ path should skip timeout
        resp = await c.get("/ws/nonexistent")
        # Will 404 but won't 504
        assert resp.status_code != 504


@pytest.mark.asyncio
async def test_lifespan_pid_file_cleanup() -> None:
    """Test PID file removal during shutdown."""
    import tempfile
    from pathlib import Path as RealPath

    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = RealPath(tmpdir) / "api_server.pid"
        pid_file.write_text("12345")

        mock_manager = MagicMock()
        mock_manager.close_all = AsyncMock()

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.api.pty_manager": MagicMock(
                    get_pty_manager=MagicMock(return_value=mock_manager)
                ),
                "code_puppy.config": MagicMock(STATE_DIR=tmpdir),
            },
        ):
            app = FastAPI()
            async with lifespan(app):
                pass
            assert not pid_file.exists()
