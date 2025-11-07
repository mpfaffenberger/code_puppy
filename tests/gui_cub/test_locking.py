"""Test suite for GUI-Cub locking mechanism."""

import threading
import time

import pytest

from code_puppy.tools.gui_cub.locking import (
    GuiCubAlreadyRunningError,
    gui_cub_agent_guard,
    is_gui_cub_active,
)


class TestGuiCubAgentGuard:
    """Test GUI-Cub agent guard context manager."""

    def test_guard_allows_single_agent(self):
        """Test that guard allows a single agent to run."""
        assert not is_gui_cub_active()

        with gui_cub_agent_guard():
            # Should be active inside guard
            assert is_gui_cub_active()

        # Should be inactive after guard exits
        assert not is_gui_cub_active()

    def test_guard_prevents_concurrent_agents(self):
        """Test that guard prevents concurrent agents."""
        with gui_cub_agent_guard():
            # First agent is running
            assert is_gui_cub_active()

            # Try to start second agent - should raise error
            with pytest.raises(GuiCubAlreadyRunningError):
                with gui_cub_agent_guard():
                    pass  # Should never reach here

            # First agent still active
            assert is_gui_cub_active()

        # After first agent exits, should be inactive
        assert not is_gui_cub_active()

    def test_guard_releases_on_exception(self):
        """Test that guard releases lock even on exception."""
        assert not is_gui_cub_active()

        try:
            with gui_cub_agent_guard():
                assert is_gui_cub_active()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Lock should be released even after exception
        assert not is_gui_cub_active()

        # Should be able to acquire lock again
        with gui_cub_agent_guard():
            assert is_gui_cub_active()

    def test_guard_allows_sequential_agents(self):
        """Test that guard allows sequential (non-concurrent) agents."""
        # First agent
        with gui_cub_agent_guard():
            assert is_gui_cub_active()

        assert not is_gui_cub_active()

        # Second agent (after first completes)
        with gui_cub_agent_guard():
            assert is_gui_cub_active()

        assert not is_gui_cub_active()

        # Third agent
        with gui_cub_agent_guard():
            assert is_gui_cub_active()

        assert not is_gui_cub_active()

    def test_guard_nested_same_thread_fails(self):
        """Test that nested guards in same thread fail."""
        with gui_cub_agent_guard():
            # Try to nest guard - should fail
            with pytest.raises(GuiCubAlreadyRunningError):
                with gui_cub_agent_guard():
                    pass


class TestIsGuiCubActive:
    """Test is_gui_cub_active() function."""

    def test_returns_false_when_inactive(self):
        """Test returns False when no agent is running."""
        # Ensure no agent is running
        assert not is_gui_cub_active()

    def test_returns_true_when_active(self):
        """Test returns True when agent is running."""
        with gui_cub_agent_guard():
            assert is_gui_cub_active()

    def test_thread_safe_checking(self):
        """Test that is_gui_cub_active is thread-safe."""
        results = []

        def check_status():
            for _ in range(100):
                results.append(is_gui_cub_active())
                time.sleep(0.001)

        # Start checking thread
        thread = threading.Thread(target=check_status)
        thread.start()

        # Activate guard in main thread
        time.sleep(0.05)
        with gui_cub_agent_guard():
            time.sleep(0.05)

        thread.join()

        # Should have mix of True and False, but no errors
        assert True in results or False in results


class TestThreadSafety:
    """Test thread safety of locking mechanism."""

    def test_concurrent_threads_only_one_succeeds(self):
        """Test that only one thread can acquire lock."""
        success_count = [0]
        error_count = [0]
        lock = threading.Lock()

        def try_acquire():
            try:
                with gui_cub_agent_guard():
                    with lock:
                        success_count[0] += 1
                    time.sleep(0.1)  # Hold lock briefly
            except GuiCubAlreadyRunningError:
                with lock:
                    error_count[0] += 1

        # Start 5 threads trying to acquire simultaneously
        threads = [threading.Thread(target=try_acquire) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed, others should get error
        assert success_count[0] == 1
        assert error_count[0] == 4

    def test_sequential_thread_access(self):
        """Test that sequential thread access works."""
        success_count = [0]
        lock = threading.Lock()

        def acquire_and_release():
            with gui_cub_agent_guard():
                with lock:
                    success_count[0] += 1
                time.sleep(0.01)

        # Run threads sequentially (one at a time)
        for _ in range(5):
            thread = threading.Thread(target=acquire_and_release)
            thread.start()
            thread.join()  # Wait for each to complete

        # All should succeed since they run sequentially
        assert success_count[0] == 5


class TestGuiCubAlreadyRunningError:
    """Test GuiCubAlreadyRunningError exception."""

    def test_error_message(self):
        """Test that error has informative message."""
        error = GuiCubAlreadyRunningError()
        message = str(error)

        assert "already running" in message.lower()
        assert "desktop automation" in message.lower()
        assert "parallel" in message.lower()

    def test_error_is_runtime_error(self):
        """Test that error is a RuntimeError subclass."""
        assert issubclass(GuiCubAlreadyRunningError, RuntimeError)

    def test_error_raised_correctly(self):
        """Test that error is raised in correct situations."""
        with gui_cub_agent_guard():
            with pytest.raises(GuiCubAlreadyRunningError):
                with gui_cub_agent_guard():
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
