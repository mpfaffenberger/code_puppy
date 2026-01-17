"""Comprehensive tests for SteeringManager module.

Tests cover:
- Singleton pattern behavior
- Pause/resume functionality
- Async wait_for_resume behavior
- Message queueing
- Agent tracking
- Thread safety with concurrent operations
"""

import asyncio
import threading
import time

import pytest

from code_puppy.steering import AgentInfo, SteeringManager, get_steering_manager


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_steering_manager():
    """Reset the SteeringManager singleton before and after each test."""
    SteeringManager.reset_instance()
    yield
    SteeringManager.reset_instance()


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestSingletonPattern:
    """Tests for singleton pattern behavior."""

    def test_steering_manager_singleton(self):
        """get_instance() should return the same instance."""
        manager1 = SteeringManager.get_instance()
        manager2 = SteeringManager.get_instance()
        manager3 = get_steering_manager()

        assert manager1 is manager2
        assert manager2 is manager3

    def test_reset_instance(self):
        """reset_instance() should clear the singleton and create a new one."""
        manager1 = SteeringManager.get_instance()
        manager1.register_agent("test-session", "test-agent", "test-model")

        SteeringManager.reset_instance()

        manager2 = SteeringManager.get_instance()

        # Should be a different instance
        assert manager1 is not manager2
        # New instance should have no agents
        assert manager2.get_active_agents() == []

    def test_convenience_function(self):
        """get_steering_manager() should return the singleton."""
        manager = get_steering_manager()
        assert isinstance(manager, SteeringManager)
        assert manager is SteeringManager.get_instance()


# =============================================================================
# Pause/Resume Tests
# =============================================================================


class TestPauseResume:
    """Tests for pause/resume functionality."""

    def test_initial_not_paused(self):
        """Manager should not be paused initially."""
        manager = get_steering_manager()
        assert manager.is_paused() is False

    def test_pause_all_sets_paused(self):
        """pause_all() should set paused state to True."""
        manager = get_steering_manager()

        manager.pause_all()

        assert manager.is_paused() is True

    def test_resume_all_clears_paused(self):
        """resume_all() should clear paused state."""
        manager = get_steering_manager()
        manager.pause_all()
        assert manager.is_paused() is True

        manager.resume_all()

        assert manager.is_paused() is False

    def test_pause_resume_multiple_cycles(self):
        """Multiple pause/resume cycles should work correctly."""
        manager = get_steering_manager()

        for _ in range(5):
            assert manager.is_paused() is False
            manager.pause_all()
            assert manager.is_paused() is True
            manager.resume_all()
            assert manager.is_paused() is False

    def test_resume_when_not_paused(self):
        """resume_all() when not paused should be a no-op."""
        manager = get_steering_manager()
        assert manager.is_paused() is False

        manager.resume_all()  # Should not raise

        assert manager.is_paused() is False

    def test_pause_when_already_paused(self):
        """pause_all() when already paused should be idempotent."""
        manager = get_steering_manager()
        manager.pause_all()
        assert manager.is_paused() is True

        manager.pause_all()  # Should not raise

        assert manager.is_paused() is True

    async def test_pause_clears_existing_event(self):
        """pause_all() should clear the event when it exists."""
        manager = get_steering_manager()

        # First create the event by calling wait_for_resume
        await manager.wait_for_resume()  # Creates event in SET state
        assert manager._pause_event is not None
        assert manager._pause_event.is_set()  # Should be set (not paused)

        # Now pause - this should clear the event
        manager.pause_all()

        assert manager._pause_event is not None
        assert not manager._pause_event.is_set()  # Should be cleared (paused)


# =============================================================================
# Async wait_for_resume Tests
# =============================================================================


class TestAsyncWaitForResume:
    """Tests for async wait_for_resume behavior."""

    async def test_wait_for_resume_not_paused(self):
        """wait_for_resume() should return immediately when not paused."""
        manager = get_steering_manager()
        assert manager.is_paused() is False

        start = time.time()
        await manager.wait_for_resume()
        elapsed = time.time() - start

        # Should return very quickly (< 100ms)
        assert elapsed < 0.1

    async def test_wait_for_resume_when_paused(self):
        """wait_for_resume() should block when paused and unblock on resume."""
        manager = get_steering_manager()
        manager.pause_all()
        assert manager.is_paused() is True

        resumed = False

        async def resume_after_delay():
            await asyncio.sleep(0.1)
            manager.resume_all()

        async def wait_and_flag():
            nonlocal resumed
            await manager.wait_for_resume()
            resumed = True

        # Run both concurrently
        await asyncio.gather(resume_after_delay(), wait_and_flag())

        assert resumed is True
        assert manager.is_paused() is False

    async def test_wait_for_resume_multiple_waiters(self):
        """Multiple waiters should all be unblocked on resume."""
        manager = get_steering_manager()
        manager.pause_all()

        resumed_count = 0
        lock = asyncio.Lock()

        async def waiter():
            nonlocal resumed_count
            await manager.wait_for_resume()
            async with lock:
                resumed_count += 1

        async def resume_after_delay():
            await asyncio.sleep(0.1)
            manager.resume_all()

        # Create 5 waiters + 1 resumer
        tasks = [waiter() for _ in range(5)]
        tasks.append(resume_after_delay())

        await asyncio.gather(*tasks)

        assert resumed_count == 5

    async def test_wait_for_resume_creates_event_lazily(self):
        """Event should be created lazily on first wait_for_resume call."""
        manager = get_steering_manager()

        # Before any async call, event should not exist
        assert manager._pause_event is None

        # Calling wait_for_resume should create the event
        await manager.wait_for_resume()

        assert manager._pause_event is not None

    async def test_wait_for_resume_respects_prior_pause(self):
        """If paused before event creation, wait should still block."""
        manager = get_steering_manager()

        # Pause before event is created
        manager.pause_all()
        assert manager._pause_event is None  # Event not yet created
        assert manager.is_paused() is True

        unblocked = False

        async def try_wait():
            nonlocal unblocked
            await manager.wait_for_resume()
            unblocked = True

        async def resume_later():
            await asyncio.sleep(0.1)
            manager.resume_all()

        await asyncio.gather(try_wait(), resume_later())

        assert unblocked is True


# =============================================================================
# Message Queue Tests
# =============================================================================


class TestMessageQueue:
    """Tests for message queueing functionality."""

    def test_queue_message(self):
        """queue_message() should add messages to the queue."""
        manager = get_steering_manager()

        manager.queue_message("session-1", "Message 1")
        manager.queue_message("session-1", "Message 2")

        messages = manager.get_queued_messages("session-1")

        assert messages == ["Message 1", "Message 2"]

    def test_get_queued_messages_clears_queue(self):
        """get_queued_messages() should clear the queue after retrieval."""
        manager = get_steering_manager()

        manager.queue_message("session-1", "Message 1")
        messages1 = manager.get_queued_messages("session-1")
        messages2 = manager.get_queued_messages("session-1")

        assert messages1 == ["Message 1"]
        assert messages2 == []  # Queue should be empty after first retrieval

    def test_get_queued_messages_unknown_session(self):
        """get_queued_messages() for unknown session should return empty list."""
        manager = get_steering_manager()

        messages = manager.get_queued_messages("nonexistent-session")

        assert messages == []

    def test_queue_messages_per_session(self):
        """Messages should be queued separately per session."""
        manager = get_steering_manager()

        manager.queue_message("session-1", "For session 1")
        manager.queue_message("session-2", "For session 2")
        manager.queue_message("session-1", "Also for session 1")

        messages1 = manager.get_queued_messages("session-1")
        messages2 = manager.get_queued_messages("session-2")

        assert messages1 == ["For session 1", "Also for session 1"]
        assert messages2 == ["For session 2"]

    def test_queue_empty_message(self):
        """Empty messages should be queueable."""
        manager = get_steering_manager()

        manager.queue_message("session-1", "")

        messages = manager.get_queued_messages("session-1")
        assert messages == [""]


# =============================================================================
# Agent Tracking Tests
# =============================================================================


class TestAgentTracking:
    """Tests for agent registration and tracking."""

    def test_register_agent(self):
        """register_agent() should add agent to tracking."""
        manager = get_steering_manager()

        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")

        agents = manager.get_active_agents()
        assert len(agents) == 1
        assert agents[0]["session_id"] == "session-1"
        assert agents[0]["agent_name"] == "husky"
        assert agents[0]["model_name"] == "claude-3-5-sonnet"
        assert "registered_at" in agents[0]

    def test_unregister_agent(self):
        """unregister_agent() should remove agent from tracking."""
        manager = get_steering_manager()
        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")
        assert len(manager.get_active_agents()) == 1

        manager.unregister_agent("session-1")

        assert len(manager.get_active_agents()) == 0

    def test_unregister_clears_messages(self):
        """unregister_agent() should also clear queued messages."""
        manager = get_steering_manager()
        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")
        manager.queue_message("session-1", "Test message")

        manager.unregister_agent("session-1")

        # Messages should be cleared too
        messages = manager.get_queued_messages("session-1")
        assert messages == []

    def test_unregister_unknown_agent(self):
        """unregister_agent() for unknown session should be a no-op."""
        manager = get_steering_manager()

        manager.unregister_agent("nonexistent")  # Should not raise

        assert manager.get_active_agents() == []

    def test_get_active_agents(self):
        """get_active_agents() should return all registered agents."""
        manager = get_steering_manager()

        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")
        manager.register_agent("session-2", "pack-leader", "gpt-4o")
        manager.register_agent("session-3", "retriever", "gemini-pro")

        agents = manager.get_active_agents()

        assert len(agents) == 3
        agent_names = {a["agent_name"] for a in agents}
        assert agent_names == {"husky", "pack-leader", "retriever"}

    def test_get_agent_info(self):
        """get_agent() should return AgentInfo for a specific session."""
        manager = get_steering_manager()
        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")

        agent = manager.get_agent("session-1")

        assert agent is not None
        assert isinstance(agent, AgentInfo)
        assert agent.session_id == "session-1"
        assert agent.agent_name == "husky"
        assert agent.model_name == "claude-3-5-sonnet"

    def test_get_agent_unknown(self):
        """get_agent() for unknown session should return None."""
        manager = get_steering_manager()

        agent = manager.get_agent("nonexistent")

        assert agent is None

    def test_register_overwrites_existing(self):
        """Registering same session_id should overwrite."""
        manager = get_steering_manager()

        manager.register_agent("session-1", "husky", "claude-3-5-sonnet")
        manager.register_agent("session-1", "retriever", "gpt-4o")

        agents = manager.get_active_agents()
        assert len(agents) == 1
        assert agents[0]["agent_name"] == "retriever"
        assert agents[0]["model_name"] == "gpt-4o"


# =============================================================================
# AgentInfo Tests
# =============================================================================


class TestAgentInfo:
    """Tests for AgentInfo dataclass."""

    def test_agent_info_creation(self):
        """AgentInfo should be created with correct fields."""
        info = AgentInfo(
            session_id="test-session",
            agent_name="test-agent",
            model_name="test-model",
        )

        assert info.session_id == "test-session"
        assert info.agent_name == "test-agent"
        assert info.model_name == "test-model"
        assert info.registered_at > 0

    def test_agent_info_to_dict(self):
        """to_dict() should return correct dictionary representation."""
        info = AgentInfo(
            session_id="test-session",
            agent_name="test-agent",
            model_name="test-model",
        )

        result = info.to_dict()

        assert result["session_id"] == "test-session"
        assert result["agent_name"] == "test-agent"
        assert result["model_name"] == "test-model"
        assert "registered_at" in result


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_pause_resume(self):
        """Concurrent pause/resume operations should not cause errors."""
        manager = get_steering_manager()
        errors = []

        def pause_resume_cycle():
            try:
                for _ in range(100):
                    manager.pause_all()
                    manager.is_paused()
                    manager.resume_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=pause_resume_cycle) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # Final state should be not paused (all threads finished with resume)
        # Note: This is a race, but no errors should occur

    def test_concurrent_agent_registration(self):
        """Concurrent agent registration should not cause errors."""
        manager = get_steering_manager()
        errors = []

        def register_agents(thread_id):
            try:
                for i in range(50):
                    session_id = f"session-{thread_id}-{i}"
                    manager.register_agent(session_id, f"agent-{thread_id}", "model")
                    manager.get_active_agents()
                    manager.unregister_agent(session_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_agents, args=(i,)) for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_message_queueing(self):
        """Concurrent message queueing should not lose messages."""
        manager = get_steering_manager()
        session_id = "shared-session"
        messages_per_thread = 100
        num_threads = 5

        def queue_messages(thread_id):
            for i in range(messages_per_thread):
                manager.queue_message(session_id, f"Thread-{thread_id}-Msg-{i}")

        threads = [
            threading.Thread(target=queue_messages, args=(i,)) for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        messages = manager.get_queued_messages(session_id)

        # All messages should be present
        assert len(messages) == messages_per_thread * num_threads

    def test_singleton_thread_safety(self):
        """get_instance() should be thread-safe."""
        SteeringManager.reset_instance()
        instances = []
        lock = threading.Lock()

        def get_instance():
            instance = SteeringManager.get_instance()
            with lock:
                instances.append(instance)

        threads = [threading.Thread(target=get_instance) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the same instance
        assert len(instances) == 20
        assert all(inst is instances[0] for inst in instances)
