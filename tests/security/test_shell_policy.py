"""Tests for shell safety changes (Epic 3 / P0-04)."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import RunContext


def test_yolo_mode_defaults_false():
    from code_puppy.config import get_yolo_mode

    with patch("code_puppy.config.get_value", return_value=None):
        assert get_yolo_mode() is False


def test_shell_safety_loaded_at_default_permission_level():
    """shell_safety plugin should load when safety_permission_level is medium (default)."""
    from code_puppy.plugins import _load_builtin_plugins
    from pathlib import Path

    plugins_dir = Path(__file__).parent.parent.parent / "code_puppy" / "plugins"
    with patch("code_puppy.config.get_safety_permission_level", return_value="medium"):
        loaded = _load_builtin_plugins(plugins_dir)
    assert "shell_safety" in loaded


@pytest.mark.asyncio
async def test_background_command_requires_approval_before_popen():
    from code_puppy.tools.command_runner import run_shell_command

    ctx = MagicMock(spec=RunContext)

    with patch(
        "code_puppy.callbacks.on_run_shell_command",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch("code_puppy.config.get_yolo_mode", return_value=False):
            with patch(
                "code_puppy.tools.command_runner.is_subagent", return_value=False
            ):
                with patch("sys.stdin.isatty", return_value=True):
                    with patch(
                        "code_puppy.tools.command_runner.get_user_approval_async",
                        new_callable=AsyncMock,
                        return_value=(True, None),
                    ) as mock_approval:
                        with patch("subprocess.Popen") as MockPopen:
                            mock_proc = MagicMock()
                            mock_proc.pid = 12345
                            MockPopen.return_value = mock_proc
                            with patch(
                                "code_puppy.tools.command_runner.get_message_bus"
                            ) as mock_bus:
                                mock_bus.return_value = MagicMock()
                                with patch("code_puppy.tools.command_runner.emit_info"):
                                    result = await run_shell_command(
                                        ctx,
                                        "sleep 100",
                                        timeout=10,
                                        background=True,
                                    )

    # Approval should have been called before Popen
    mock_approval.assert_called_once()
    assert result.success is True
    assert result.background is True
    if result.log_file and os.path.exists(result.log_file):
        os.unlink(result.log_file)


@pytest.mark.asyncio
async def test_background_command_denial_does_not_start_process():
    from code_puppy.tools.command_runner import run_shell_command

    ctx = MagicMock(spec=RunContext)

    with patch(
        "code_puppy.callbacks.on_run_shell_command",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch("code_puppy.config.get_yolo_mode", return_value=False):
            with patch(
                "code_puppy.tools.command_runner.is_subagent", return_value=False
            ):
                with patch("sys.stdin.isatty", return_value=True):
                    with patch(
                        "code_puppy.tools.command_runner.get_user_approval_async",
                        new_callable=AsyncMock,
                        return_value=(False, "nope"),
                    ):
                        with patch("subprocess.Popen") as MockPopen:
                            result = await run_shell_command(
                                ctx,
                                "sleep 100",
                                timeout=10,
                                background=True,
                            )

    MockPopen.assert_not_called()
    assert result.success is False
    assert "nope" in result.error


def test_shell_output_retains_only_tail_lines():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "command_runner_module",
        Path(__file__).parent.parent.parent
        / "code_puppy"
        / "tools"
        / "command_runner.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    source = Path(spec.origin).read_text()
    # Verify deque with maxlen=256 is used in streaming
    assert "deque(maxlen=256)" in source
    assert "stdout_lines: deque" in source
    assert "stderr_lines: deque" in source


def test_failed_command_has_no_fixed_sleep():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "command_runner_module",
        Path(__file__).parent.parent.parent
        / "code_puppy"
        / "tools"
        / "command_runner.py",
    )
    source = Path(spec.origin).read_text()
    assert "time.sleep(1)" not in source


def test_background_job_registry_lists_and_stops_job(tmp_path):
    from code_puppy.tools.background_jobs import (
        _BACKGROUND_JOBS,
        list_background_jobs,
        register_background_job,
        stop_background_job,
    )

    _BACKGROUND_JOBS.clear()
    log_file = tmp_path / "test.log"
    log_file.write_text("test")
    register_background_job(9999, "echo hi", str(tmp_path), str(log_file))
    jobs = list_background_jobs()
    assert len(jobs) == 1
    assert jobs[0].pid == 9999

    # stop_background_job should remove and attempt kill
    assert stop_background_job(9999) is True
    assert not list_background_jobs()

    # Stopping unknown job returns False
    assert stop_background_job(8888) is False
    _BACKGROUND_JOBS.clear()
