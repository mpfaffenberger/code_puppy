"""Full coverage tests for api/pty_manager.py."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.api.pty_manager import (
    PTYManager,
    PTYSession,
    get_pty_manager,
)


class TestPTYManager:
    def test_sessions_property(self):
        mgr = PTYManager()
        assert mgr.sessions == {}

    def test_list_sessions_empty(self):
        mgr = PTYManager()
        assert mgr.list_sessions() == []

    def test_get_session_none(self):
        mgr = PTYManager()
        assert mgr.get_session("nonexistent") is None

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_create_unix_session(self):
        mgr = PTYManager()
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()

        with (
            patch("pty.fork", return_value=(123, 5)),
            patch("fcntl.ioctl"),
            patch("fcntl.fcntl", return_value=0),
            patch("asyncio.create_task", return_value=mock_task),
        ):
            on_output = MagicMock()
            session = await mgr.create_session("test-1", on_output=on_output)
            assert session.session_id == "test-1"
            assert session.pid == 123
            assert session.master_fd == 5
            assert session._running is True
            assert "test-1" in mgr.list_sessions()

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_create_session_replaces_existing(self):
        mgr = PTYManager()
        # Pre-populate a session
        old_session = PTYSession(session_id="dup", pid=1)
        mgr._sessions["dup"] = old_session

        with (
            patch("pty.fork", return_value=(456, 6)),
            patch("fcntl.ioctl"),
            patch("fcntl.fcntl", return_value=0),
            patch("asyncio.create_task", return_value=MagicMock()),
        ):
            session = await mgr.create_session("dup")
            assert session.pid == 456

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_write_unix(self):
        mgr = PTYManager()
        session = PTYSession(session_id="w", master_fd=10)
        mgr._sessions["w"] = session

        with patch("os.write") as mock_write:
            result = await mgr.write("w", b"hello")
            assert result is True
            mock_write.assert_called_once_with(10, b"hello")

    @pytest.mark.anyio
    async def test_write_nonexistent_session(self):
        mgr = PTYManager()
        result = await mgr.write("nope", b"hello")
        assert result is False

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_write_exception(self):
        mgr = PTYManager()
        session = PTYSession(session_id="e", master_fd=10)
        mgr._sessions["e"] = session

        with patch("os.write", side_effect=OSError("fail")):
            result = await mgr.write("e", b"hello")
            assert result is False

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_resize_unix(self):
        mgr = PTYManager()
        session = PTYSession(session_id="r", master_fd=10)
        mgr._sessions["r"] = session

        with patch("fcntl.ioctl"):
            result = await mgr.resize("r", 120, 40)
            assert result is True
            assert session.cols == 120
            assert session.rows == 40

    @pytest.mark.anyio
    async def test_resize_nonexistent(self):
        mgr = PTYManager()
        result = await mgr.resize("nope", 80, 24)
        assert result is False

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_resize_exception(self):
        mgr = PTYManager()
        session = PTYSession(session_id="re", master_fd=10)
        mgr._sessions["re"] = session

        with patch("fcntl.ioctl", side_effect=OSError("fail")):
            result = await mgr.resize("re", 80, 24)
            assert result is False

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_close_session(self):
        mgr = PTYManager()
        task = asyncio.ensure_future(asyncio.sleep(100))

        session = PTYSession(session_id="c", master_fd=10, pid=123)
        session._reader_task = task
        mgr._sessions["c"] = session

        with (
            patch("os.close"),
            patch("os.kill"),
            patch("os.waitpid", return_value=(123, 0)),
        ):
            result = await mgr.close_session("c")
            assert result is True
            assert "c" not in mgr._sessions

    @pytest.mark.anyio
    async def test_close_nonexistent(self):
        mgr = PTYManager()
        result = await mgr.close_session("nope")
        assert result is False

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_close_all(self):
        mgr = PTYManager()
        s1 = PTYSession(session_id="a")
        s2 = PTYSession(session_id="b")
        mgr._sessions["a"] = s1
        mgr._sessions["b"] = s2

        await mgr.close_all()
        assert len(mgr._sessions) == 0

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    async def test_close_session_os_errors(self):
        """close handles OSError on close/kill gracefully."""
        mgr = PTYManager()
        session = PTYSession(session_id="e", master_fd=10, pid=999)
        mgr._sessions["e"] = session

        with (
            patch("os.close", side_effect=OSError),
            patch("os.kill", side_effect=OSError),
            patch("os.waitpid", side_effect=ChildProcessError),
        ):
            result = await mgr.close_session("e")
            assert result is True

    def test_read_unix_pty_data(self):
        mgr = PTYManager()
        with patch("os.read", return_value=b"data"):
            result = mgr._read_unix_pty(5)
            assert result == b"data"

    def test_read_unix_pty_blocking(self):
        mgr = PTYManager()
        with patch("os.read", side_effect=BlockingIOError):
            result = mgr._read_unix_pty(5)
            assert result is None

    def test_read_unix_pty_eof(self):
        mgr = PTYManager()
        with patch("os.read", side_effect=OSError):
            result = mgr._read_unix_pty(5)
            assert result == b""

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    async def test_write_windows(self):
        mgr = PTYManager()
        mock_winpty = MagicMock()
        session = PTYSession(session_id="w", winpty_process=mock_winpty)
        mgr._sessions["w"] = session

        result = await mgr.write("w", b"hello")
        assert result is True
        mock_winpty.write.assert_called_once_with("hello")

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    async def test_resize_windows(self):
        mgr = PTYManager()
        mock_winpty = MagicMock()
        session = PTYSession(session_id="rw", winpty_process=mock_winpty)
        mgr._sessions["rw"] = session

        result = await mgr.resize("rw", 100, 30)
        assert result is True
        mock_winpty.setwinsize.assert_called_once_with(30, 100)

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    async def test_close_windows(self):
        mgr = PTYManager()
        mock_winpty = MagicMock()
        session = PTYSession(session_id="cw", winpty_process=mock_winpty)
        mgr._sessions["cw"] = session

        result = await mgr.close_session("cw")
        assert result is True
        mock_winpty.terminate.assert_called_once()

    @pytest.mark.anyio
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    async def test_close_windows_terminate_error(self):
        mgr = PTYManager()
        mock_winpty = MagicMock()
        mock_winpty.terminate.side_effect = Exception("fail")
        session = PTYSession(session_id="cwe", winpty_process=mock_winpty)
        mgr._sessions["cwe"] = session

        result = await mgr.close_session("cwe")
        assert result is True


class TestGetPtyManager:
    def test_singleton(self):
        import code_puppy.api.pty_manager as mod

        mod._pty_manager = None
        mgr1 = get_pty_manager()
        mgr2 = get_pty_manager()
        assert mgr1 is mgr2
        mod._pty_manager = None


class TestPTYSessionIsAliveWindows:
    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    def test_windows_no_winpty(self):
        session = PTYSession(session_id="x", winpty_process=None)
        assert session.is_alive() is False
