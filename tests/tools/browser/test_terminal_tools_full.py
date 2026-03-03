"""Full coverage tests for terminal_tools.py."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.terminal_tools import (
    _get_session_from_context,
    check_terminal_server,
    close_terminal,
    get_session_manager,
    get_terminal_session,
    open_terminal,
    register_check_terminal_server,
    register_close_terminal,
    register_open_terminal,
    register_start_api_server,
    set_terminal_session,
    start_api_server,
)

MOD = "code_puppy.tools.browser.terminal_tools"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


class TestSessionFunctions:
    def test_set_get_terminal_session(self):
        set_terminal_session("test-sess")
        assert get_terminal_session() == "test-sess"
        set_terminal_session(None)

    def test_get_session_manager(self):
        set_terminal_session("mgr-sess")
        mgr = get_session_manager()
        assert mgr is not None
        set_terminal_session(None)

    def test_get_session_from_context_with_session(self):
        set_terminal_session("ctx-sess")
        ctx = MagicMock()
        assert _get_session_from_context(ctx) == "ctx-sess"
        set_terminal_session(None)

    def test_get_session_from_context_default(self):
        set_terminal_session(None)
        ctx = MagicMock()
        assert _get_session_from_context(ctx) == "default"


class _FakeHttpxClient:
    """Fake httpx.AsyncClient that properly supports async with."""

    def __init__(self, get_return=None, get_side_effect=None):
        self._get_return = get_return
        self._get_side_effect = get_side_effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url):
        if self._get_side_effect:
            raise self._get_side_effect
        return self._get_return


class TestCheckTerminalServer:
    @pytest.mark.asyncio
    async def test_healthy(self):
        resp = MagicMock()
        resp.json.return_value = {"status": "healthy"}
        resp.raise_for_status = MagicMock()
        with patch(f"{MOD}.httpx") as mh:
            import httpx as real_httpx

            mh.AsyncClient.return_value = _FakeHttpxClient(get_return=resp)
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_unhealthy_response(self):
        resp = MagicMock()
        resp.json.return_value = {"status": "unhealthy"}
        resp.raise_for_status = MagicMock()
        with patch(f"{MOD}.httpx") as mh:
            import httpx as real_httpx

            mh.AsyncClient.return_value = _FakeHttpxClient(get_return=resp)
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_connect_error(self):
        import httpx as real_httpx

        with patch(f"{MOD}.httpx") as mh:
            mh.AsyncClient.return_value = _FakeHttpxClient(
                get_side_effect=real_httpx.ConnectError("refused")
            )
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        import httpx as real_httpx

        with patch(f"{MOD}.httpx") as mh:
            mh.AsyncClient.return_value = _FakeHttpxClient(
                get_side_effect=real_httpx.TimeoutException("t")
            )
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_http_status_error(self):
        import httpx as real_httpx

        mock_resp = MagicMock(status_code=500)
        with patch(f"{MOD}.httpx") as mh:
            mh.AsyncClient.return_value = _FakeHttpxClient(
                get_side_effect=real_httpx.HTTPStatusError(
                    "500", request=MagicMock(), response=mock_resp
                )
            )
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_generic_exception(self):
        import httpx as real_httpx

        with patch(f"{MOD}.httpx") as mh:
            mh.AsyncClient.return_value = _FakeHttpxClient(
                get_side_effect=RuntimeError("unexpected")
            )
            mh.ConnectError = real_httpx.ConnectError
            mh.TimeoutException = real_httpx.TimeoutException
            mh.HTTPStatusError = real_httpx.HTTPStatusError
            r = await check_terminal_server()
            assert r["success"] is False


class TestOpenTerminal:
    @pytest.mark.asyncio
    async def test_server_not_running(self):
        with patch(
            f"{MOD}.check_terminal_server",
            return_value={"success": False, "error": "not running"},
        ):
            r = await open_terminal()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with (
            patch(
                f"{MOD}.check_terminal_server",
                return_value={"success": True, "server_url": "http://localhost:8765"},
            ),
            patch(f"{MOD}.get_session_manager", return_value=mgr),
        ):
            r = await open_terminal()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "http://localhost:8765/terminal"
        page.title.return_value = "Terminal"
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page

        with (
            patch(
                f"{MOD}.check_terminal_server",
                return_value={"success": True, "server_url": "http://localhost:8765"},
            ),
            patch(f"{MOD}.get_session_manager", return_value=mgr),
        ):
            r = await open_terminal()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_xterm_timeout(self):
        page = AsyncMock()
        page.url = "http://localhost:8765/terminal"
        page.title.return_value = "Terminal"
        page.wait_for_selector.side_effect = RuntimeError("timeout")
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page

        with (
            patch(
                f"{MOD}.check_terminal_server",
                return_value={"success": True, "server_url": "http://localhost:8765"},
            ),
            patch(f"{MOD}.get_session_manager", return_value=mgr),
        ):
            r = await open_terminal()
            assert r["success"] is True  # Continues despite timeout

    @pytest.mark.asyncio
    async def test_exception(self):
        with (
            patch(
                f"{MOD}.check_terminal_server",
                return_value={"success": True, "server_url": "http://localhost:8765"},
            ),
            patch(f"{MOD}.get_session_manager", side_effect=RuntimeError("boom")),
        ):
            r = await open_terminal()
            assert r["success"] is False


class TestCloseTerminal:
    @pytest.mark.asyncio
    async def test_success(self):
        mgr = AsyncMock()
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await close_terminal()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.close.side_effect = RuntimeError("err")
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await close_terminal()
            assert r["success"] is False


class TestStartApiServer:
    @pytest.mark.asyncio
    async def test_already_running(self, tmp_path):
        pid_file = tmp_path / "api_server.pid"
        pid_file.write_text(str(os.getpid()))

        with patch("code_puppy.config.STATE_DIR", str(tmp_path)):
            r = await start_api_server()
            assert r["success"] is True
            assert r["already_running"] is True

    @pytest.mark.asyncio
    async def test_stale_pid_file(self, tmp_path):
        pid_file = tmp_path / "api_server.pid"
        pid_file.write_text("999999999")

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with (
            patch("code_puppy.config.STATE_DIR", str(tmp_path)),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            r = await start_api_server()
            assert r["success"] is True
            assert r["already_running"] is False

    @pytest.mark.asyncio
    async def test_start_exception(self, tmp_path):
        with (
            patch("code_puppy.config.STATE_DIR", str(tmp_path)),
            patch("subprocess.Popen", side_effect=RuntimeError("fail")),
        ):
            r = await start_api_server()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_invalid_pid_in_file(self, tmp_path):
        pid_file = tmp_path / "api_server.pid"
        pid_file.write_text("not-a-number")

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with (
            patch("code_puppy.config.STATE_DIR", str(tmp_path)),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            r = await start_api_server()
            assert r["success"] is True


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_check_terminal_server,
            register_open_terminal,
            register_close_terminal,
            register_start_api_server,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
