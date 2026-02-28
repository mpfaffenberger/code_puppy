"""Full coverage tests for mcp_/captured_stdio_server.py."""

import os
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.captured_stdio_server import (
    CapturedMCPServerStdio,
    StderrCapture,
    StderrCollector,
)


class TestStderrCapture:
    def test_init_default_handler(self):
        cap = StderrCapture("test")
        assert cap.name == "test"
        assert cap._captured_lines == []

    def test_default_handler_logs(self):
        cap = StderrCapture("test")
        cap._default_handler("hello")
        # No crash

    def test_default_handler_empty(self):
        cap = StderrCapture("test")
        cap._default_handler("  ")
        # No crash

    def test_custom_handler(self):
        lines = []
        cap = StderrCapture("test", handler=lines.append)
        assert cap.handler is not None

    @pytest.mark.anyio
    async def test_start_capture(self):
        cap = StderrCapture("test")
        pipe_w = await cap.start_capture()
        assert pipe_w is not None
        assert cap._pipe_r is not None
        # Write something to trigger
        os.write(pipe_w, b"hello\n")
        import asyncio

        await asyncio.sleep(0.2)
        await cap.stop_capture()

    @pytest.mark.anyio
    async def test_stop_capture_without_start(self):
        cap = StderrCapture("test")
        await cap.stop_capture()  # Should not raise

    def test_get_captured_lines(self):
        cap = StderrCapture("test")
        cap._captured_lines = ["line1", "line2"]
        result = cap.get_captured_lines()
        assert result == ["line1", "line2"]
        assert result is not cap._captured_lines  # copy


class TestCapturedMCPServerStdio:
    def test_init(self):
        server = CapturedMCPServerStdio(command="echo", args=["hello"])
        assert server.command == "echo"
        assert server._captured_lines == []

    def test_init_with_handler(self):
        handler = MagicMock()
        server = CapturedMCPServerStdio(command="echo", stderr_handler=handler)
        assert server.stderr_handler is handler

    def test_get_captured_stderr(self):
        server = CapturedMCPServerStdio(command="echo")
        server._captured_lines = ["err1"]
        result = server.get_captured_stderr()
        assert result == ["err1"]
        assert result is not server._captured_lines

    def test_clear_captured_stderr(self):
        server = CapturedMCPServerStdio(command="echo")
        server._captured_lines = ["err1"]
        server.clear_captured_stderr()
        assert server._captured_lines == []


class TestStderrCollector:
    def test_init(self):
        col = StderrCollector()
        assert col.servers == {}
        assert col.all_lines == []

    def test_create_handler_and_call(self):
        col = StderrCollector()
        handler = col.create_handler("srv1")
        handler("test line")
        assert col.servers["srv1"] == ["test line"]
        assert len(col.all_lines) == 1
        assert col.all_lines[0]["server"] == "srv1"

    def test_create_handler_emit_to_user(self):
        col = StderrCollector()
        handler = col.create_handler("srv1", emit_to_user=True)
        with patch("code_puppy.messaging.emit_info"):
            handler("test")

    def test_get_server_output(self):
        col = StderrCollector()
        assert col.get_server_output("unknown") == []
        col.servers["srv1"] = ["line1"]
        assert col.get_server_output("srv1") == ["line1"]

    def test_get_all_output(self):
        col = StderrCollector()
        col.all_lines = [{"server": "s", "line": "l"}]
        result = col.get_all_output()
        assert len(result) == 1
        assert result is not col.all_lines

    def test_clear_specific_server(self):
        col = StderrCollector()
        col.servers["s1"] = ["l1"]
        col.servers["s2"] = ["l2"]
        col.all_lines = [
            {"server": "s1", "line": "l1"},
            {"server": "s2", "line": "l2"},
        ]
        col.clear("s1")
        assert "s1" not in col.servers
        assert "s2" in col.servers
        assert len(col.all_lines) == 1

    def test_clear_all(self):
        col = StderrCollector()
        col.servers["s1"] = ["l1"]
        col.all_lines = [{"server": "s1", "line": "l1"}]
        col.clear()
        assert col.servers == {}
        assert col.all_lines == []

    def test_clear_nonexistent_server(self):
        col = StderrCollector()
        col.clear("nonexistent")  # Should not raise
