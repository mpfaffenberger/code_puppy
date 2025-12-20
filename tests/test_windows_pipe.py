"""Test Windows pipe non-blocking read functionality."""
import subprocess
import sys
import threading
import time

import pytest

from code_puppy.tools.command_runner import _win32_pipe_has_data


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
class TestWin32PipeHasData:
    """Tests for the _win32_pipe_has_data function."""

    def test_returns_true_when_data_available(self):
        """Test that function returns True when pipe has data."""
        proc = subprocess.Popen(
            "echo hello",
            shell=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        proc.wait()
        time.sleep(0.1)  # Give buffer time to fill
        
        assert _win32_pipe_has_data(proc.stdout) is True
        proc.stdout.close()

    def test_returns_false_when_no_data(self):
        """Test that function returns False when pipe has no data yet."""
        # Use a command that takes time to produce output
        proc = subprocess.Popen(
            "ping -n 3 127.0.0.1 >nul && echo done",
            shell=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        
        # Check immediately - should have no data
        result = _win32_pipe_has_data(proc.stdout)
        proc.kill()
        proc.wait()
        
        # Should be False (no output yet)
        assert result is False

    def test_reader_loop_can_be_stopped(self):
        """Test that a reader loop using _win32_pipe_has_data can be stopped via event."""
        # This is the key test - simulates the frozen agent scenario
        proc = subprocess.Popen(
            "ping -n 1000 127.0.0.1 >nul",  # Long-running, no stdout output
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        stop_event = threading.Event()
        loop_exited = threading.Event()
        
        def reader_loop():
            iterations = 0
            while not stop_event.is_set():
                iterations += 1
                if _win32_pipe_has_data(proc.stdout):
                    proc.stdout.readline()
                else:
                    time.sleep(0.05)  # Brief sleep when no data
                
                if iterations > 100:  # Safety limit
                    break
            loop_exited.set()
        
        # Start reader thread
        reader_thread = threading.Thread(target=reader_loop, daemon=True)
        reader_thread.start()
        
        # Wait briefly, then signal stop
        time.sleep(0.2)
        stop_event.set()
        
        # Thread should exit quickly
        reader_thread.join(timeout=1.0)
        
        # Cleanup
        proc.kill()
        proc.wait()
        
        # The key assertion: thread should have exited
        assert loop_exited.is_set(), "Reader loop should have exited when stop event was set"
        assert not reader_thread.is_alive(), "Reader thread should not be alive"

    def test_handles_closed_pipe(self):
        """Test that function handles closed pipes gracefully."""
        proc = subprocess.Popen(
            "echo test",
            shell=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        proc.wait()
        proc.stdout.close()
        
        # Should return False, not raise exception
        result = _win32_pipe_has_data(proc.stdout)
        assert result is False
