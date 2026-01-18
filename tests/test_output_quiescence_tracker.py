"""Tests for OutputQuiescenceTracker."""

import threading
import time

import pytest

from code_puppy.output_quiescence import (
    get_output_quiescence_tracker,
    reset_output_quiescence_tracker,
)


@pytest.fixture
def quiescence_tracker():
    """Provide a fresh OutputQuiescenceTracker for each test."""
    tracker = get_output_quiescence_tracker()
    tracker.reset()
    return tracker


class TestOutputQuiescenceTrackerBasics:
    """Test basic OutputQuiescenceTracker functionality."""

    def test_initial_state_is_quiescent(self, quiescence_tracker):
        """Test that tracker starts in quiescent state."""
        assert quiescence_tracker.is_quiescent() is True
        assert quiescence_tracker.active_stream_count() == 0

    def test_start_stream_increments_count(self, quiescence_tracker):
        """Test that start_stream increments count."""
        quiescence_tracker.start_stream()
        assert quiescence_tracker.active_stream_count() == 1
        assert quiescence_tracker.is_quiescent() is False

    def test_end_stream_decrements_count(self, quiescence_tracker):
        """Test that end_stream decrements count."""
        quiescence_tracker.start_stream()
        quiescence_tracker.end_stream()
        assert quiescence_tracker.active_stream_count() == 0
        assert quiescence_tracker.is_quiescent() is True

    def test_multiple_streams(self, quiescence_tracker):
        """Test tracking multiple concurrent streams."""
        quiescence_tracker.start_stream()
        quiescence_tracker.start_stream()
        quiescence_tracker.start_stream()
        assert quiescence_tracker.active_stream_count() == 3
        assert quiescence_tracker.is_quiescent() is False

        quiescence_tracker.end_stream()
        assert quiescence_tracker.active_stream_count() == 2

        quiescence_tracker.end_stream()
        quiescence_tracker.end_stream()
        assert quiescence_tracker.active_stream_count() == 0
        assert quiescence_tracker.is_quiescent() is True

    def test_end_stream_without_start_is_safe(self, quiescence_tracker):
        """Test that end_stream without start doesn't go negative."""
        quiescence_tracker.end_stream()
        assert quiescence_tracker.active_stream_count() == 0
        assert quiescence_tracker.is_quiescent() is True


class TestOutputQuiescenceTrackerSingleton:
    """Test singleton pattern for OutputQuiescenceTracker."""

    def test_singleton_same_instance(self):
        """Test that get_output_quiescence_tracker returns same instance."""
        tracker1 = get_output_quiescence_tracker()
        tracker2 = get_output_quiescence_tracker()
        assert tracker1 is tracker2

    def test_singleton_thread_safety(self):
        """Test singleton is thread-safe."""
        instances = []

        def get_instance():
            instances.append(get_output_quiescence_tracker())

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(id(inst) for inst in instances)) == 1


class TestOutputQuiescenceTrackerWait:
    """Test wait_for_quiescence methods."""

    def test_wait_returns_true_when_quiescent(self, quiescence_tracker):
        """Test wait_for_quiescence returns True immediately when quiescent."""
        result = quiescence_tracker.wait_for_quiescence(timeout=0.1)
        assert result is True

    def test_wait_timeout_when_active(self, quiescence_tracker):
        """Test wait_for_quiescence times out when streams active."""
        quiescence_tracker.start_stream()
        start = time.time()
        result = quiescence_tracker.wait_for_quiescence(timeout=0.2)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.2
        assert elapsed < 0.5

    def test_wait_succeeds_when_stream_ends(self, quiescence_tracker):
        """Test wait_for_quiescence succeeds when stream ends."""
        quiescence_tracker.start_stream()

        def end_later():
            time.sleep(0.1)
            quiescence_tracker.end_stream()

        t = threading.Thread(target=end_later)
        t.start()

        result = quiescence_tracker.wait_for_quiescence(timeout=1.0)
        t.join()

        assert result is True

    @pytest.mark.asyncio
    async def test_async_wait_returns_true_when_quiescent(self, quiescence_tracker):
        """Test async wait returns True immediately when quiescent."""
        result = await quiescence_tracker.async_wait_for_quiescence(timeout=0.1)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_wait_timeout_when_active(self, quiescence_tracker):
        """Test async wait times out when streams active."""
        quiescence_tracker.start_stream()
        start = time.time()
        result = await quiescence_tracker.async_wait_for_quiescence(timeout=0.2)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.2


class TestOutputQuiescenceTrackerCallbacks:
    """Test callback functionality."""

    def test_add_callback(self, quiescence_tracker):
        """Test adding a callback."""
        results = []

        def my_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(my_callback)
        quiescence_tracker.start_stream()

        assert results == [False]

    def test_callback_on_quiescent(self, quiescence_tracker):
        """Test callback is called when becoming quiescent."""
        results = []

        def my_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(my_callback)
        quiescence_tracker.start_stream()
        quiescence_tracker.end_stream()

        assert results == [False, True]

    def test_remove_callback(self, quiescence_tracker):
        """Test removing a callback."""
        results = []

        def my_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(my_callback)
        result = quiescence_tracker.remove_callback(my_callback)
        assert result is True

        quiescence_tracker.start_stream()
        assert results == []

    def test_remove_nonexistent_callback(self, quiescence_tracker):
        """Test removing a callback that doesn't exist."""

        def my_callback(is_quiescent):
            pass

        result = quiescence_tracker.remove_callback(my_callback)
        assert result is False

    def test_callback_exception_handling(self, quiescence_tracker):
        """Test that callback exceptions are handled gracefully."""

        def bad_callback(is_quiescent):
            raise ValueError("Callback error!")

        results = []

        def good_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(bad_callback)
        quiescence_tracker.add_callback(good_callback)

        quiescence_tracker.start_stream()
        assert results == [False]


class TestOutputQuiescenceTrackerReset:
    """Test reset functionality."""

    def test_reset_clears_count(self, quiescence_tracker):
        """Test reset clears active count."""
        quiescence_tracker.start_stream()
        quiescence_tracker.start_stream()
        quiescence_tracker.reset()
        assert quiescence_tracker.active_stream_count() == 0
        assert quiescence_tracker.is_quiescent() is True

    def test_reset_clears_callbacks(self, quiescence_tracker):
        """Test reset clears callbacks."""
        results = []

        def callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(callback)
        quiescence_tracker.reset()

        quiescence_tracker.start_stream()
        assert results == []

    def test_reset_module_function(self, quiescence_tracker):
        """Test module-level reset function."""
        quiescence_tracker.start_stream()
        reset_output_quiescence_tracker()
        assert quiescence_tracker.active_stream_count() == 0


class TestOutputQuiescenceTrackerThreadSafety:
    """Test thread safety of OutputQuiescenceTracker."""

    def test_concurrent_start_end(self, quiescence_tracker):
        """Test concurrent start/end stream operations."""
        errors = []

        def stream_cycle(iterations):
            try:
                for _ in range(iterations):
                    quiescence_tracker.start_stream()
                    quiescence_tracker.end_stream()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=stream_cycle, args=(100,)) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert quiescence_tracker.active_stream_count() == 0
