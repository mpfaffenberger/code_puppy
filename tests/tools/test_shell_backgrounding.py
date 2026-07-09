"""Ctrl+X Ctrl+B: mid-flight backgrounding of streaming shell commands."""

import os
import subprocess
import sys
import time

from code_puppy.tools import command_runner
from code_puppy.tools.command_runner import run_shell_command_streaming
from code_puppy.tools.shell_backgrounding import (
    DivertLog,
    request_background_all,
)

#: Prints a line every 100ms for ~20s -- long enough to be mid-flight,
#: short enough to self-clean if a kill fails.
SLOW_SCRIPT = (
    "import time\n"
    "for i in range(200):\n"
    "    print('tick', i, flush=True)\n"
    "    time.sleep(0.1)\n"
)


def _spawn_slow_process():
    return subprocess.Popen(
        [sys.executable, "-u", "-c", SLOW_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_background_request_detaches_streaming_command():
    process = _spawn_slow_process()
    command_runner._register_process(process)
    try:
        # Request the detach shortly after streaming starts.
        import threading

        threading.Timer(0.5, request_background_all).start()
        result = run_shell_command_streaming(
            process, timeout=30, command="slow ticker", silent=True
        )

        assert result.background is True
        assert result.success is True
        assert result.pid == process.pid
        assert result.log_file and os.path.exists(result.log_file)
        assert result.exit_code is None
        # The agent must be TOLD, in prose, that the user detached it --
        # background=True alone is too easy for a model to skim past.
        assert result.user_feedback is not None
        assert "backgrounded" in result.user_feedback
        assert "NOT finished" in result.user_feedback
        assert result.log_file in result.user_feedback
        # The process must still be RUNNING -- backgrounded, not killed.
        assert process.poll() is None
        # ...and out of the kill-all registry.
        with command_runner._RUNNING_PROCESSES_LOCK:
            assert process not in command_runner._RUNNING_PROCESSES

        # Reader threads keep draining the pipes into the log file.
        time.sleep(1.0)
        with open(result.log_file, encoding="utf-8") as fh:
            content = fh.read()
        assert "backgrounded shell: slow ticker" in content
        assert "tick" in content
    finally:
        command_runner._kill_process_group(process)
        try:
            if result.log_file:
                time.sleep(0.2)
                os.unlink(result.log_file)
        except (OSError, UnboundLocalError):
            pass


def test_full_tool_path_returns_promptly_on_background():
    """End to end through _execute_shell_command (executor + keyboard
    context): the tool call must return within a couple of poll ticks of
    the chord firing -- NOT when the process exits. Uses asyncio like the
    real agent runtime."""
    import asyncio
    import threading

    async def scenario():
        # Bump AFTER startup lag (keyboard context + spawn can take ~2s
        # on a cold Windows box); measure from the bump, not from start.
        bumped_at = {}

        def bump():
            bumped_at["t"] = time.monotonic()
            request_background_all()

        threading.Timer(3.0, bump).start()
        result = await command_runner._execute_shell_command(
            command=f'"{sys.executable}" -c "import time; time.sleep(30)"',
            cwd=None,
            timeout=60,
            group_id="bg-e2e",
            silent=True,
        )
        returned_at = time.monotonic()
        return result, returned_at - bumped_at["t"]

    result, latency = asyncio.run(scenario())
    try:
        assert result.background is True
        assert latency < 3.0, f"tool call took {latency:.2f}s after the chord"
    finally:
        # Clean up the still-running sleep + its log.
        if result.pid:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(result.pid)]
                if sys.platform.startswith("win")
                else ["kill", "-9", str(result.pid)],
                capture_output=True,
                check=False,
            )
        if result.log_file:
            time.sleep(0.3)
            try:
                os.unlink(result.log_file)
            except OSError:
                pass


def test_streaming_unaffected_by_prior_background_requests():
    """Generation counting: an OLD background request must not detach a
    command that starts afterwards."""
    request_background_all()  # stale request from a previous chord press
    process = subprocess.Popen(
        [sys.executable, "-c", "print('hello')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    command_runner._register_process(process)
    result = run_shell_command_streaming(
        process, timeout=15, command="quick echo", silent=True
    )
    assert result.background is False
    assert result.success is True
    assert "hello" in (result.stdout or "")


def test_divert_log_writes_and_close_are_safe():
    log = DivertLog("demo command")
    log.write_line("stdout", "plain line")
    log.write_line("stderr", "error line")
    log.close()
    log.write_line("stdout", "after close")  # must not raise
    with open(log.path, encoding="utf-8") as fh:
        content = fh.read()
    os.unlink(log.path)
    assert "plain line" in content
    assert "[stderr] error line" in content
    assert "after close" not in content
