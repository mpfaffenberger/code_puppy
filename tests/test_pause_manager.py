"""Tests for PauseManager: registry, steering queues, and pause barrier.

Also includes tests for OutputQuiescenceTracker.
"""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from code_puppy.pause_manager import (
    AgentEntry,
    AgentStatus,
    get_output_quiescence_tracker,
    get_pause_manager,
    reset_output_quiescence_tracker,
    reset_pause_manager,
)


@pytest.fixture
def pause_manager():
    """Provide a fresh PauseManager for each test."""
    # Reset the singleton before each test
    pm = get_pause_manager()
    pm.reset()
    return pm


class TestAgentEntry:
    """Tests for AgentEntry dataclass."""

    def test_agent_entry_creation(self):
        """Test basic AgentEntry creation."""
        entry = AgentEntry(agent_id="test-123", name="TestAgent")
        assert entry.agent_id == "test-123"
        assert entry.name == "TestAgent"
        assert entry.status == AgentStatus.RUNNING
        assert entry.registered_at > 0
        assert entry.pause_requested_at is None

    def test_agent_entry_steering_queue_lazy_creation(self):
        """Test that steering queue is created lazily."""
        entry = AgentEntry(agent_id="test-123", name="TestAgent")
        # Internal queue should be None initially
        assert entry._steering_queue is None
        # Accessing property creates it
        queue = entry.steering_queue
        assert queue is not None
        assert isinstance(queue, asyncio.Queue)
        # Same queue returned on subsequent access
        assert entry.steering_queue is queue


class TestPauseManagerSingleton:
    """Tests for singleton pattern."""

    def test_singleton_same_instance(self):
        """Test that get_pause_manager returns same instance."""
        pm1 = get_pause_manager()
        pm2 = get_pause_manager()
        assert pm1 is pm2

    def test_singleton_thread_safety(self):
        """Test singleton is thread-safe."""
        instances = []

        def get_instance():
            instances.append(get_pause_manager())

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the same instance
        assert len(set(id(inst) for inst in instances)) == 1


class TestAgentRegistry:
    """Tests for agent registration functionality."""

    def test_register_agent(self, pause_manager):
        """Test registering an agent."""
        result = pause_manager.register("agent-1", "FirstAgent")
        assert result is True
        assert pause_manager.agent_count() == 1

    def test_register_duplicate_agent(self, pause_manager):
        """Test registering the same agent twice."""
        pause_manager.register("agent-1", "FirstAgent")
        result = pause_manager.register("agent-1", "FirstAgent")
        assert result is False  # Already registered
        assert pause_manager.agent_count() == 1

    def test_unregister_agent(self, pause_manager):
        """Test unregistering an agent."""
        pause_manager.register("agent-1", "FirstAgent")
        result = pause_manager.unregister("agent-1")
        assert result is True
        assert pause_manager.agent_count() == 0

    def test_unregister_nonexistent_agent(self, pause_manager):
        """Test unregistering a non-existent agent."""
        result = pause_manager.unregister("nonexistent")
        assert result is False

    def test_get_agent(self, pause_manager):
        """Test getting an agent by ID."""
        pause_manager.register("agent-1", "FirstAgent")
        entry = pause_manager.get_agent("agent-1")
        assert entry is not None
        assert entry.name == "FirstAgent"

    def test_get_nonexistent_agent(self, pause_manager):
        """Test getting a non-existent agent."""
        entry = pause_manager.get_agent("nonexistent")
        assert entry is None

    def test_list_agents(self, pause_manager):
        """Test listing all agents."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        agents = pause_manager.list_agents()
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"First", "Second"}

    def test_list_running_agents(self, pause_manager):
        """Test listing only running agents."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        # Pause one agent
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")  # Transition to PAUSED

        running = pause_manager.list_running_agents()
        assert len(running) == 1
        assert running[0].name == "Second"

    def test_list_paused_agents(self, pause_manager):
        """Test listing paused agents."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        # Pause one agent
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        paused = pause_manager.list_paused_agents()
        assert len(paused) == 1
        assert paused[0].name == "First"

    def test_agent_count(self, pause_manager):
        """Test agent count."""
        assert pause_manager.agent_count() == 0
        pause_manager.register("agent-1", "First")
        assert pause_manager.agent_count() == 1
        pause_manager.register("agent-2", "Second")
        assert pause_manager.agent_count() == 2
        pause_manager.unregister("agent-1")
        assert pause_manager.agent_count() == 1


class TestPauseRequests:
    """Tests for pause request functionality."""

    def test_request_pause_single_agent(self, pause_manager):
        """Test requesting pause for a single agent."""
        pause_manager.register("agent-1", "First")
        result = pause_manager.request_pause("agent-1")
        assert result is True
        entry = pause_manager.get_agent("agent-1")
        assert entry.status == AgentStatus.PAUSE_REQUESTED
        assert entry.pause_requested_at is not None

    def test_request_pause_global(self, pause_manager):
        """Test requesting global pause."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        result = pause_manager.request_pause()  # Global
        assert result is True
        assert pause_manager.is_pause_requested() is True
        for agent in pause_manager.list_agents():
            assert agent.status == AgentStatus.PAUSE_REQUESTED

    def test_request_pause_nonexistent_agent(self, pause_manager):
        """Test requesting pause for non-existent agent."""
        result = pause_manager.request_pause("nonexistent")
        assert result is False

    def test_request_pause_already_paused(self, pause_manager):
        """Test requesting pause when already paused."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        # Request again - should still return True (idempotent)
        result = pause_manager.request_pause("agent-1")
        assert result is True

    def test_request_resume_single_agent(self, pause_manager):
        """Test resuming a single agent."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")
        result = pause_manager.request_resume("agent-1")
        assert result is True
        entry = pause_manager.get_agent("agent-1")
        assert entry.status == AgentStatus.RUNNING

    def test_request_resume_global(self, pause_manager):
        """Test global resume."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        pause_manager.request_pause()
        pause_manager.request_resume()
        assert pause_manager.is_pause_requested() is False
        for agent in pause_manager.list_agents():
            assert agent.status == AgentStatus.RUNNING

    def test_is_pause_requested_agent_specific(self, pause_manager):
        """Test checking pause state for specific agent."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        assert pause_manager.is_pause_requested("agent-1") is False
        pause_manager.request_pause("agent-1")
        assert pause_manager.is_pause_requested("agent-1") is True
        assert pause_manager.is_pause_requested("agent-2") is False

    def test_is_pause_requested_unknown_agent(self, pause_manager):
        """Test is_pause_requested for unknown agent."""
        assert pause_manager.is_pause_requested("nonexistent") is False


class TestDBOSGuard:
    """Tests for DBOS compatibility guard."""

    def test_pause_blocked_when_dbos_enabled(self, pause_manager):
        """Test that pause is blocked when DBOS is enabled."""
        pause_manager.register("agent-1", "First")

        with patch("code_puppy.pause_manager.get_use_dbos", return_value=True):
            result = pause_manager.request_pause("agent-1")
            assert result is False  # Blocked by DBOS guard
            entry = pause_manager.get_agent("agent-1")
            assert entry.status == AgentStatus.RUNNING  # Not changed

    def test_pause_allowed_when_dbos_disabled(self, pause_manager):
        """Test that pause works when DBOS is disabled."""
        pause_manager.register("agent-1", "First")

        with patch("code_puppy.pause_manager.get_use_dbos", return_value=False):
            result = pause_manager.request_pause("agent-1")
            assert result is True
            entry = pause_manager.get_agent("agent-1")
            assert entry.status == AgentStatus.PAUSE_REQUESTED

    def test_checkpoint_noop_when_dbos_enabled(self, pause_manager):
        """Test that pause checkpoint is no-op when DBOS enabled."""
        pause_manager.register("agent-1", "First")
        # Manually set status to test checkpoint behavior
        entry = pause_manager.get_agent("agent-1")
        entry.status = AgentStatus.PAUSE_REQUESTED

        with patch("code_puppy.pause_manager.get_use_dbos", return_value=True):
            result = pause_manager.pause_checkpoint("agent-1")
            assert result is False  # Should not pause

    def test_is_dbos_enabled_method(self, pause_manager):
        """Test is_dbos_enabled convenience method."""
        with patch("code_puppy.pause_manager.get_use_dbos", return_value=True):
            assert pause_manager.is_dbos_enabled() is True

        with patch("code_puppy.pause_manager.get_use_dbos", return_value=False):
            assert pause_manager.is_dbos_enabled() is False


class TestPauseCheckpoint:
    """Tests for pause checkpoint/barrier functionality."""

    def test_pause_checkpoint_transitions_to_paused(self, pause_manager):
        """Test that checkpoint transitions from PAUSE_REQUESTED to PAUSED."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")

        result = pause_manager.pause_checkpoint("agent-1")
        assert result is True
        entry = pause_manager.get_agent("agent-1")
        assert entry.status == AgentStatus.PAUSED

    def test_pause_checkpoint_returns_false_when_running(self, pause_manager):
        """Test checkpoint returns False when agent is running."""
        pause_manager.register("agent-1", "First")
        result = pause_manager.pause_checkpoint("agent-1")
        assert result is False

    def test_pause_checkpoint_unknown_agent_uses_global(self, pause_manager):
        """Test checkpoint for unknown agent uses global state."""
        assert pause_manager.pause_checkpoint("unknown") is False
        pause_manager._global_pause_requested = True
        assert pause_manager.pause_checkpoint("unknown") is True

    @pytest.mark.asyncio
    async def test_async_pause_checkpoint(self, pause_manager):
        """Test async version of pause checkpoint."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")

        result = await pause_manager.async_pause_checkpoint("agent-1")
        assert result is True
        entry = pause_manager.get_agent("agent-1")
        assert entry.status == AgentStatus.PAUSED


class TestWaitForResume:
    """Tests for wait_for_resume functionality."""

    def test_wait_for_resume_timeout(self, pause_manager):
        """Test wait_for_resume times out."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        start = time.time()
        result = pause_manager.wait_for_resume("agent-1", timeout=0.2)
        elapsed = time.time() - start

        assert result is False  # Timed out
        assert elapsed >= 0.2
        assert elapsed < 0.5  # Shouldn't take too long

    def test_wait_for_resume_succeeds_on_resume(self, pause_manager):
        """Test wait_for_resume succeeds when agent is resumed."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        # Resume in a separate thread
        def resume_later():
            time.sleep(0.1)
            pause_manager.request_resume("agent-1")

        t = threading.Thread(target=resume_later)
        t.start()

        result = pause_manager.wait_for_resume("agent-1", timeout=1.0)
        t.join()

        assert result is True

    def test_wait_for_resume_unknown_agent(self, pause_manager):
        """Test wait_for_resume returns True for unknown agent."""
        result = pause_manager.wait_for_resume("unknown", timeout=0.1)
        assert result is True  # Don't block for unknown agents

    @pytest.mark.asyncio
    async def test_async_wait_for_resume_timeout(self, pause_manager):
        """Test async wait_for_resume times out."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        start = time.time()
        result = await pause_manager.async_wait_for_resume("agent-1", timeout=0.2)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.2

    @pytest.mark.asyncio
    async def test_async_wait_for_resume_succeeds(self, pause_manager):
        """Test async wait_for_resume succeeds when resumed."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        async def resume_later():
            await asyncio.sleep(0.1)
            pause_manager.request_resume("agent-1")

        # Run both concurrently
        result = await asyncio.gather(
            pause_manager.async_wait_for_resume("agent-1", timeout=1.0),
            resume_later(),
        )

        assert result[0] is True


class TestSteeringQueues:
    """Tests for steering queue functionality."""

    def test_get_steering_queue(self, pause_manager):
        """Test getting steering queue for agent."""
        pause_manager.register("agent-1", "First")
        queue = pause_manager.get_steering_queue("agent-1")
        assert queue is not None
        assert isinstance(queue, asyncio.Queue)

    def test_get_steering_queue_unknown_agent(self, pause_manager):
        """Test getting steering queue for unknown agent."""
        queue = pause_manager.get_steering_queue("unknown")
        assert queue is None

    def test_send_steering_input(self, pause_manager):
        """Test sending steering input."""
        pause_manager.register("agent-1", "First")
        result = pause_manager.send_steering_input("agent-1", {"action": "continue"})
        assert result is True

        # Check it's in the queue
        queue = pause_manager.get_steering_queue("agent-1")
        assert not queue.empty()

    def test_send_steering_input_unknown_agent(self, pause_manager):
        """Test sending steering input to unknown agent."""
        result = pause_manager.send_steering_input("unknown", {"action": "stop"})
        assert result is False

    @pytest.mark.asyncio
    async def test_receive_steering_input(self, pause_manager):
        """Test receiving steering input."""
        pause_manager.register("agent-1", "First")
        pause_manager.send_steering_input("agent-1", {"action": "modify", "data": 42})

        result = await pause_manager.receive_steering_input("agent-1", timeout=1.0)
        assert result == {"action": "modify", "data": 42}

    @pytest.mark.asyncio
    async def test_receive_steering_input_timeout(self, pause_manager):
        """Test receive times out when queue empty."""
        pause_manager.register("agent-1", "First")
        result = await pause_manager.receive_steering_input("agent-1", timeout=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_receive_steering_input_unknown_agent(self, pause_manager):
        """Test receive from unknown agent."""
        result = await pause_manager.receive_steering_input("unknown", timeout=0.1)
        assert result is None

    def test_clear_steering_queue(self, pause_manager):
        """Test clearing steering queue."""
        pause_manager.register("agent-1", "First")
        pause_manager.send_steering_input("agent-1", "input1")
        pause_manager.send_steering_input("agent-1", "input2")
        pause_manager.send_steering_input("agent-1", "input3")

        count = pause_manager.clear_steering_queue("agent-1")
        assert count == 3

        queue = pause_manager.get_steering_queue("agent-1")
        assert queue.empty()

    def test_clear_steering_queue_unknown_agent(self, pause_manager):
        """Test clearing queue for unknown agent."""
        count = pause_manager.clear_steering_queue("unknown")
        assert count == 0


class TestPauseCallbacks:
    """Tests for pause state callbacks."""

    def test_add_pause_callback(self, pause_manager):
        """Test adding a pause callback."""
        callback_results = []

        def my_callback(is_paused):
            callback_results.append(is_paused)

        pause_manager.add_pause_callback(my_callback)
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause()  # Global pause triggers callback

        assert callback_results == [True]

    def test_callback_on_resume(self, pause_manager):
        """Test callback is called on resume."""
        callback_results = []

        def my_callback(is_paused):
            callback_results.append(is_paused)

        pause_manager.add_pause_callback(my_callback)
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause()
        pause_manager.request_resume()

        assert callback_results == [True, False]

    def test_remove_pause_callback(self, pause_manager):
        """Test removing a pause callback."""
        callback_results = []

        def my_callback(is_paused):
            callback_results.append(is_paused)

        pause_manager.add_pause_callback(my_callback)
        result = pause_manager.remove_pause_callback(my_callback)
        assert result is True

        pause_manager.register("agent-1", "First")
        pause_manager.request_pause()

        assert callback_results == []  # Callback was removed

    def test_remove_nonexistent_callback(self, pause_manager):
        """Test removing a callback that doesn't exist."""

        def my_callback(is_paused):
            pass

        result = pause_manager.remove_pause_callback(my_callback)
        assert result is False

    def test_callback_exception_handling(self, pause_manager):
        """Test that callback exceptions are handled gracefully."""

        def bad_callback(is_paused):
            raise ValueError("Callback error!")

        results = []

        def good_callback(is_paused):
            results.append(is_paused)

        pause_manager.add_pause_callback(bad_callback)
        pause_manager.add_pause_callback(good_callback)
        pause_manager.register("agent-1", "First")

        # Should not raise, and good callback should still be called
        pause_manager.request_pause()
        assert results == [True]


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_agents(self, pause_manager):
        """Test reset clears all agents."""
        pause_manager.register("agent-1", "First")
        pause_manager.register("agent-2", "Second")
        pause_manager.reset()
        assert pause_manager.agent_count() == 0

    def test_reset_clears_pause_state(self, pause_manager):
        """Test reset clears pause state."""
        pause_manager.register("agent-1", "First")
        pause_manager.request_pause()
        pause_manager.reset()
        assert pause_manager.is_pause_requested() is False

    def test_reset_clears_callbacks(self, pause_manager):
        """Test reset clears callbacks."""
        results = []

        def callback(paused):
            results.append(paused)

        pause_manager.add_pause_callback(callback)
        pause_manager.reset()

        pause_manager.register("agent-1", "First")
        pause_manager.request_pause()
        assert results == []  # Callback was cleared

    def test_reset_pause_manager_function(self, pause_manager):
        """Test module-level reset function."""
        pause_manager.register("agent-1", "First")
        reset_pause_manager()
        assert pause_manager.agent_count() == 0


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_registration(self, pause_manager):
        """Test concurrent agent registration."""
        results = []

        def register_agent(agent_id):
            result = pause_manager.register(agent_id, f"Agent-{agent_id}")
            results.append((agent_id, result))

        threads = [
            threading.Thread(target=register_agent, args=(f"agent-{i}",))
            for i in range(20)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert all(r[1] for r in results)
        assert pause_manager.agent_count() == 20

    def test_concurrent_pause_resume(self, pause_manager):
        """Test concurrent pause/resume operations."""
        pause_manager.register("agent-1", "First")

        def toggle_pause(iterations):
            for _ in range(iterations):
                pause_manager.request_pause("agent-1")
                pause_manager.request_resume("agent-1")

        threads = [threading.Thread(target=toggle_pause, args=(50,)) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without deadlock or exception
        # Final state should be consistent
        entry = pause_manager.get_agent("agent-1")
        assert entry is not None


# =============================================================================
# OutputQuiescenceTracker Tests
# =============================================================================


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
        quiescence_tracker.end_stream()  # Should not raise or go negative
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

        # All should be the same instance
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

        assert results == [False]  # Became non-quiescent

    def test_callback_on_quiescent(self, quiescence_tracker):
        """Test callback is called when becoming quiescent."""
        results = []

        def my_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(my_callback)
        quiescence_tracker.start_stream()
        quiescence_tracker.end_stream()

        assert results == [False, True]  # Non-quiescent, then quiescent

    def test_remove_callback(self, quiescence_tracker):
        """Test removing a callback."""
        results = []

        def my_callback(is_quiescent):
            results.append(is_quiescent)

        quiescence_tracker.add_callback(my_callback)
        result = quiescence_tracker.remove_callback(my_callback)
        assert result is True

        quiescence_tracker.start_stream()
        assert results == []  # Callback was removed

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

        # Should not raise, and good callback should still be called
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
        assert results == []  # Callback was cleared

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
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=stream_cycle, args=(100,)) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final count should be 0 (all streams ended)
        assert quiescence_tracker.active_stream_count() == 0
