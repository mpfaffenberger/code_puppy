"""Tests for code_puppy/command_line/mcp/logs_command.py"""

from unittest.mock import MagicMock, patch

MODULE = "code_puppy.command_line.mcp.logs_command"
UTILS = "code_puppy.command_line.mcp.utils"


def _make_cmd():
    """Create a LogsCommand with mocked manager."""
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.logs_command import LogsCommand

        cmd = LogsCommand()
    return cmd


class TestExecuteNoArgs:
    @patch(f"{MODULE}.list_servers_with_logs", return_value=[])
    @patch(f"{MODULE}.emit_info")
    def test_no_servers(self, mock_info, mock_list):
        cmd = _make_cmd()
        cmd.execute([])
        mock_info.assert_called()

    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "total_size_bytes": 2048,
            "rotated_count": 0,
            "line_count": 50,
            "exists": True,
        },
    )
    @patch(f"{MODULE}.list_servers_with_logs", return_value=["my-srv"])
    @patch(f"{MODULE}.emit_info")
    def test_with_servers(self, mock_info, mock_list, mock_stats):
        cmd = _make_cmd()
        cmd.execute([])
        # Should contain server name in output
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("my-srv" in c for c in calls)

    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "total_size_bytes": 1024 * 1024 * 2,
            "rotated_count": 3,
            "line_count": 1000,
            "exists": True,
        },
    )
    @patch(f"{MODULE}.list_servers_with_logs", return_value=["big-srv"])
    @patch(f"{MODULE}.emit_info")
    def test_large_file_with_rotated(self, mock_info, mock_list, mock_stats):
        cmd = _make_cmd()
        cmd.execute([])
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("rotated" in c for c in calls)


class TestExecuteClear:
    @patch(f"{MODULE}.clear_logs")
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "exists": True,
            "rotated_count": 1,
            "line_count": 10,
            "total_size_bytes": 100,
        },
    )
    @patch(f"{MODULE}.emit_info")
    def test_clear_existing(self, mock_info, mock_stats, mock_clear):
        cmd = _make_cmd()
        cmd.execute(["my-srv", "--clear"])
        mock_clear.assert_called_once_with("my-srv", include_rotated=True)

    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "exists": False,
            "rotated_count": 0,
            "line_count": 0,
            "total_size_bytes": 0,
        },
    )
    @patch(f"{MODULE}.emit_info")
    def test_clear_nonexistent(self, mock_info, mock_stats):
        cmd = _make_cmd()
        cmd.execute(["my-srv", "--clear"])
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("No logs" in c for c in calls)

    @patch(f"{MODULE}.get_log_stats", side_effect=Exception("disk error"))
    @patch(f"{MODULE}.emit_error")
    def test_clear_exception(self, mock_error, mock_stats):
        cmd = _make_cmd()
        cmd.execute(["my-srv", "--clear"])
        mock_error.assert_called()


class TestExecuteShowLogs:
    @patch(f"{UTILS}.find_server_id_by_name", return_value="srv-id")
    @patch(f"{MODULE}.read_logs", return_value=["line1", "line2"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 2,
            "exists": True,
            "total_size_bytes": 100,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/test.log")
    @patch(f"{MODULE}.emit_info")
    def test_show_default_lines(
        self, mock_info, mock_path, mock_stats, mock_read, mock_find
    ):
        cmd = _make_cmd()
        cmd.execute(["my-srv"])
        mock_read.assert_called_once_with("my-srv", lines=50)

    @patch(f"{UTILS}.find_server_id_by_name", return_value="srv-id")
    @patch(f"{MODULE}.read_logs", return_value=["line1"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 100,
            "exists": True,
            "total_size_bytes": 100,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/test.log")
    @patch(f"{MODULE}.emit_info")
    def test_show_with_hint(
        self, mock_info, mock_path, mock_stats, mock_read, mock_find
    ):
        """When showing < total, should show hint for more."""
        cmd = _make_cmd()
        cmd.execute(["my-srv", "1"])
        mock_read.assert_called_once_with("my-srv", lines=1)

    @patch(f"{UTILS}.find_server_id_by_name", return_value="srv-id")
    @patch(f"{MODULE}.read_logs", return_value=["line1", "line2"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 2,
            "exists": True,
            "total_size_bytes": 100,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/test.log")
    @patch(f"{MODULE}.emit_info")
    def test_show_all(self, mock_info, mock_path, mock_stats, mock_read, mock_find):
        cmd = _make_cmd()
        cmd.execute(["my-srv", "all"])
        mock_read.assert_called_once_with("my-srv", lines=None)

    @patch(f"{UTILS}.find_server_id_by_name", return_value="srv-id")
    @patch(f"{MODULE}.read_logs", return_value=[])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 0,
            "exists": True,
            "total_size_bytes": 0,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/test.log")
    @patch(f"{MODULE}.emit_info")
    def test_no_logs(self, mock_info, mock_path, mock_stats, mock_read, mock_find):
        cmd = _make_cmd()
        cmd.execute(["my-srv"])
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("No logs" in c for c in calls)

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "exists": False,
            "line_count": 0,
            "total_size_bytes": 0,
            "rotated_count": 0,
        },
    )
    @patch(f"{UTILS}.suggest_similar_servers")
    @patch(f"{MODULE}.emit_info")
    def test_server_not_found(self, mock_info, mock_suggest, mock_stats, mock_find):
        cmd = _make_cmd()
        cmd.execute(["nonexistent"])
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("not found" in c for c in calls)

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "exists": True,
            "line_count": 5,
            "total_size_bytes": 100,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.read_logs", return_value=["old log line"])
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/old.log")
    @patch(f"{MODULE}.emit_info")
    def test_server_not_configured_but_has_logs(
        self, mock_info, mock_path, mock_read, mock_stats, mock_find
    ):
        cmd = _make_cmd()
        cmd.execute(["old-srv"])
        mock_read.assert_called()

    @patch(f"{MODULE}.find_server_id_by_name", side_effect=Exception("db error"))
    @patch(f"{MODULE}.emit_error")
    def test_exception(self, mock_error, mock_find):
        cmd = _make_cmd()
        cmd.execute(["my-srv"])
        mock_error.assert_called()


class TestExecuteLinesParsing:
    @patch(f"{UTILS}.find_server_id_by_name", return_value="id")
    @patch(f"{MODULE}.read_logs", return_value=["x"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 1,
            "exists": True,
            "total_size_bytes": 10,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/t.log")
    @patch(f"{MODULE}.emit_info")
    def test_invalid_number(
        self, mock_info, mock_path, mock_stats, mock_read, mock_find
    ):
        cmd = _make_cmd()
        cmd.execute(["srv", "notanum"])
        # Should fall back to 50
        mock_read.assert_called_once_with("srv", lines=50)

    @patch(f"{UTILS}.find_server_id_by_name", return_value="id")
    @patch(f"{MODULE}.read_logs", return_value=["x"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 1,
            "exists": True,
            "total_size_bytes": 10,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/t.log")
    @patch(f"{MODULE}.emit_info")
    def test_negative_number(
        self, mock_info, mock_path, mock_stats, mock_read, mock_find
    ):
        cmd = _make_cmd()
        cmd.execute(["srv", "-5"])
        # Should fall back to 50
        mock_read.assert_called_once_with("srv", lines=50)

    @patch(f"{UTILS}.find_server_id_by_name", return_value="id")
    @patch(f"{MODULE}.read_logs", return_value=["x"])
    @patch(
        f"{MODULE}.get_log_stats",
        return_value={
            "line_count": 1,
            "exists": True,
            "total_size_bytes": 10,
            "rotated_count": 0,
        },
    )
    @patch(f"{MODULE}.get_log_file_path", return_value="/tmp/t.log")
    @patch(f"{MODULE}.emit_info")
    def test_custom_line_count(
        self, mock_info, mock_path, mock_stats, mock_read, mock_find
    ):
        cmd = _make_cmd()
        cmd.execute(["srv", "100"])
        mock_read.assert_called_once_with("srv", lines=100)


class TestGenerateGroupId:
    def test_generates_uuid(self):
        cmd = _make_cmd()
        gid = cmd.generate_group_id()
        assert isinstance(gid, str)
        assert len(gid) > 0

    def test_with_provided_group_id(self):
        cmd = _make_cmd()
        cmd.execute([], group_id="custom-group")
