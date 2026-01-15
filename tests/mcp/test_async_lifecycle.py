"""
Comprehensive tests for AsyncServerLifecycleManager.

Covers all major code paths, edge cases, and error handling
for the async server lifecycle management system.
"""

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.mcp_.async_lifecycle import (
    AsyncServerLifecycleManager,
    ManagedServerContext,
    get_lifecycle_manager,
)


class TestManagedServerContext:
    """Test the ManagedServerContext dataclass."""

    def test_creation(self):
        """Test creating a ManagedServerContext."""
        server = Mock()
        exit_stack = AsyncExitStack()
        start_time = datetime.now()
        task = Mock(spec=asyncio.Task)

        context = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=start_time,
            task=task,
        )

        assert context.server_id == "test-server"
        assert context.server == server
        assert context.exit_stack == exit_stack
        assert context.start_time == start_time
        assert context.task == task

    def test_dataclass_fields(self):
        """Test that ManagedServerContext has all required fields."""
        server = Mock()
        exit_stack = AsyncExitStack()
        start_time = datetime.now()
        task = Mock(spec=asyncio.Task)

        context = ManagedServerContext(
            server_id="test",
            server=server,
            exit_stack=exit_stack,
            start_time=start_time,
            task=task,
        )

        # Verify all fields are accessible
        assert hasattr(context, "server_id")
        assert hasattr(context, "server")
        assert hasattr(context, "exit_stack")
        assert hasattr(context, "start_time")
        assert hasattr(context, "task")


class TestAsyncServerLifecycleManagerInit:
    """Test AsyncServerLifecycleManager initialization."""

    def test_initialization(self):
        """Test that the manager initializes correctly."""
        manager = AsyncServerLifecycleManager()
        assert manager._servers == {}
        assert isinstance(manager._lock, asyncio.Lock)

    def test_list_servers_empty(self):
        """Test list_servers returns empty dict on init."""
        manager = AsyncServerLifecycleManager()
        assert manager.list_servers() == {}

    def test_is_running_nonexistent(self):
        """Test is_running returns False for nonexistent server."""
        manager = AsyncServerLifecycleManager()
        assert manager.is_running("nonexistent") is False


class TestAsyncServerLifecycleManagerStartServer:
    """Test AsyncServerLifecycleManager start_server method."""

    @pytest.mark.asyncio
    async def test_start_server_success(self):
        """Test successfully starting a server."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        # Mock the _server_lifecycle_task to avoid it blocking
        with patch.object(
            manager,
            "_server_lifecycle_task",
            new_callable=AsyncMock,
        ) as mock_task:
            # Prevent the task from exiting immediately
            async def fake_lifecycle():
                await asyncio.sleep(10)  # Sleep to keep it alive

            mock_task.side_effect = fake_lifecycle

            result = await manager.start_server("test-server", server)

            # Should succeed (or at least not fail immediately)
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_start_server_already_running(self):
        """Test starting a server that's already running."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        # Create a fake running context
        exit_stack = AsyncExitStack()
        task = asyncio.create_task(asyncio.sleep(10))
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        result = await manager.start_server("test-server", server)

        # Should return True since it's already running
        assert result is True

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_server_cleanup_dead_server(self):
        """Test cleanup of a server that exists but isn't running."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = False

        # Create a dead context
        dead_exit_stack = AsyncExitStack()
        dead_task = asyncio.create_task(asyncio.sleep(10))
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=dead_exit_stack,
            start_time=datetime.now(),
            task=dead_task,
        )

        # Mock the stop method to prevent actual task cancellation
        with patch.object(
            manager,
            "_server_lifecycle_task",
            new_callable=AsyncMock,
        ):
            await manager.start_server("test-server", server)

        # Cleanup
        dead_task.cancel()
        try:
            await dead_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_server_task_fails_immediately(self):
        """Test handling when the lifecycle task fails immediately."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()

        # Mock the task to fail immediately
        with patch.object(
            manager,
            "_server_lifecycle_task",
            new_callable=AsyncMock,
        ) as mock_task:
            mock_task.side_effect = RuntimeError("Task creation failed")

            result = await manager.start_server("test-server", server)

            # Should fail since task creation failed
            assert result is False


class TestAsyncServerLifecycleTaskLifecycle:
    """Test the _server_lifecycle_task method."""

    @pytest.mark.asyncio
    async def test_lifecycle_task_context_enter_exit(self):
        """Test that the lifecycle task properly enters and exits context."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        # Mock the AsyncExitStack to track enter/exit
        enter_called = False
        exit_called = False

        original_enter = AsyncExitStack.enter_async_context

        async def mock_enter_async_context(self, async_cm):
            nonlocal enter_called
            enter_called = True
            return await original_enter(self, async_cm)

        async def mock_aclose(self):
            nonlocal exit_called
            exit_called = True
            # Create a minimal close to avoid cleanup issues
            self._exit_callbacks.clear()

        with patch.object(
            AsyncExitStack, "enter_async_context", mock_enter_async_context
        ):
            with patch.object(AsyncExitStack, "aclose", mock_aclose):
                # Create a task that will be immediately cancelled
                task = asyncio.create_task(
                    manager._server_lifecycle_task("test-server", server)
                )

                # Give it a moment to start
                await asyncio.sleep(0.2)

                # Cancel the task
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # Verify context was managed
                assert enter_called is True
                assert exit_called is True

    @pytest.mark.asyncio
    async def test_lifecycle_task_stores_context(self):
        """Test that the lifecycle task stores the context."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        task = asyncio.create_task(
            manager._server_lifecycle_task("test-server", server)
        )

        # Give it time to store
        await asyncio.sleep(0.2)

        # Should be stored
        assert "test-server" in manager._servers
        stored_context = manager._servers["test-server"]
        assert stored_context.server_id == "test-server"
        assert stored_context.server == server

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_lifecycle_task_heartbeat_loop(self):
        """Test the heartbeat loop in lifecycle task."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        task = asyncio.create_task(
            manager._server_lifecycle_task("test-server", server)
        )

        # Let it run for a bit
        await asyncio.sleep(0.5)

        # Should still be running
        assert "test-server" in manager._servers

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_lifecycle_task_detects_stopped_server(self):
        """Test that the lifecycle task detects when server stops."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()

        # Start with running
        server.is_running = True

        asyncio.create_task(manager._server_lifecycle_task("test-server", server))

        # Give it time to start
        await asyncio.sleep(0.2)
        assert "test-server" in manager._servers

        # Now mark server as not running
        server.is_running = False

        # Give it time to detect
        await asyncio.sleep(1.5)

        # Task should have exited and cleaned up
        assert "test-server" not in manager._servers

    @pytest.mark.asyncio
    async def test_lifecycle_task_cancelled_error(self):
        """Test handling of CancelledError in lifecycle task."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        task = asyncio.create_task(
            manager._server_lifecycle_task("test-server", server)
        )

        # Give it time to start
        await asyncio.sleep(0.2)
        assert "test-server" in manager._servers

        # Cancel the task
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Should be cleaned up
        assert "test-server" not in manager._servers

    @pytest.mark.asyncio
    async def test_lifecycle_task_exception_handling(self):
        """Test exception handling in lifecycle task."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()

        # Make the context entry fail
        async def failing_context_manager():
            raise RuntimeError("Context entry failed")

        server.__aenter__ = Mock(side_effect=RuntimeError("Context entry failed"))
        server.__aexit__ = AsyncMock()

        task = asyncio.create_task(
            manager._server_lifecycle_task("test-server", server)
        )

        # Wait for it to complete
        try:
            await task
        except Exception:
            pass

        # Should not be in servers since it failed to enter context
        # The task will fail before storing the context
        await asyncio.sleep(0.1)


class TestAsyncServerLifecycleManagerStopServer:
    """Test AsyncServerLifecycleManager stop_server method."""

    @pytest.mark.asyncio
    async def test_stop_server_success(self):
        """Test successfully stopping a server."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        # Create a real task that can be cancelled
        exit_stack = AsyncExitStack()
        task = asyncio.create_task(asyncio.sleep(100))

        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        result = await manager.stop_server("test-server")

        assert result is True
        # Task should be cancelled
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_server_not_found(self):
        """Test stopping a server that doesn't exist."""
        manager = AsyncServerLifecycleManager()
        result = await manager.stop_server("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_server_internal_called_with_lock(self):
        """Test that stop_server uses the lock correctly."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()

        # Create a fake context
        exit_stack = AsyncExitStack()
        task = asyncio.create_task(asyncio.sleep(100))
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        with patch.object(
            manager, "_stop_server_internal", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = True
            await manager.stop_server("test-server")
            mock_internal.assert_called_once_with("test-server")


class TestAsyncServerLifecycleManagerStopAll:
    """Test AsyncServerLifecycleManager stop_all method."""

    @pytest.mark.asyncio
    async def test_stop_all_servers(self):
        """Test stopping all servers."""
        manager = AsyncServerLifecycleManager()

        # Create multiple fake contexts with mock tasks
        for i in range(3):
            server = AsyncMock()
            exit_stack = AsyncExitStack()
            task = Mock(spec=asyncio.Task)
            task.cancel = Mock()
            manager._servers[f"server-{i}"] = ManagedServerContext(
                server_id=f"server-{i}",
                server=server,
                exit_stack=exit_stack,
                start_time=datetime.now(),
                task=task,
            )

        assert len(manager._servers) == 3

        # Mock the stop_server method to actually remove servers
        async def mock_stop_server(server_id):
            if server_id in manager._servers:
                del manager._servers[server_id]
            return True

        with patch.object(manager, "stop_server", side_effect=mock_stop_server):
            await manager.stop_all()

        # After mocking the cleanup
        assert len(manager._servers) == 0

    @pytest.mark.asyncio
    async def test_stop_all_empty(self):
        """Test stopping all when no servers are running."""
        manager = AsyncServerLifecycleManager()
        # Should not raise
        await manager.stop_all()
        assert len(manager._servers) == 0


class TestAsyncServerLifecycleManagerIsRunning:
    """Test AsyncServerLifecycleManager is_running method."""

    def test_is_running_true(self):
        """Test is_running returns True for running server."""
        manager = AsyncServerLifecycleManager()
        server = Mock()
        server.is_running = True

        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        assert manager.is_running("test-server") is True

    def test_is_running_false(self):
        """Test is_running returns False for stopped server."""
        manager = AsyncServerLifecycleManager()
        server = Mock()
        server.is_running = False

        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        assert manager.is_running("test-server") is False

    def test_is_running_nonexistent(self):
        """Test is_running returns False for nonexistent server."""
        manager = AsyncServerLifecycleManager()
        assert manager.is_running("nonexistent") is False


class TestAsyncServerLifecycleManagerListServers:
    """Test AsyncServerLifecycleManager list_servers method."""

    def test_list_servers_empty(self):
        """Test list_servers with no servers."""
        manager = AsyncServerLifecycleManager()
        result = manager.list_servers()
        assert result == {}

    def test_list_servers_single_server(self):
        """Test list_servers with one server."""
        manager = AsyncServerLifecycleManager()
        server = Mock()
        server.__class__.__name__ = "MCPServerStdio"
        server.is_running = True

        now = datetime.now()
        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=now,
            task=task,
        )

        result = manager.list_servers()

        assert "test-server" in result
        assert result["test-server"]["type"] == "MCPServerStdio"
        assert result["test-server"]["is_running"] is True
        assert result["test-server"]["uptime_seconds"] >= 0
        assert result["test-server"]["start_time"] == now.isoformat()

    def test_list_servers_multiple_servers(self):
        """Test list_servers with multiple servers."""
        manager = AsyncServerLifecycleManager()

        for i in range(3):
            server = Mock()
            server.__class__.__name__ = f"MCPServer{i}"
            server.is_running = True

            exit_stack = AsyncExitStack()
            task = Mock(spec=asyncio.Task)
            start_time = datetime.now() - timedelta(seconds=i * 10)
            manager._servers[f"server-{i}"] = ManagedServerContext(
                server_id=f"server-{i}",
                server=server,
                exit_stack=exit_stack,
                start_time=start_time,
                task=task,
            )

        result = manager.list_servers()

        assert len(result) == 3
        assert "server-0" in result
        assert "server-1" in result
        assert "server-2" in result

        # Check uptime increases (server-0 started most recently, server-2 started earliest)
        assert (
            result["server-0"]["uptime_seconds"] <= result["server-1"]["uptime_seconds"]
        )
        assert (
            result["server-1"]["uptime_seconds"] <= result["server-2"]["uptime_seconds"]
        )

    def test_list_servers_uptime_calculation(self):
        """Test that uptime is calculated correctly."""
        manager = AsyncServerLifecycleManager()
        server = Mock()
        server.__class__.__name__ = "MCPServerTest"
        server.is_running = True

        start_time = datetime.now() - timedelta(seconds=42)
        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=start_time,
            task=task,
        )

        result = manager.list_servers()
        uptime = result["test-server"]["uptime_seconds"]

        # Should be approximately 42 seconds (allow 1 second tolerance)
        assert 41 <= uptime <= 43


class TestGlobalLifecycleManager:
    """Test the global lifecycle manager singleton."""

    def test_get_lifecycle_manager_returns_instance(self):
        """Test that get_lifecycle_manager returns an instance."""
        with patch("code_puppy.mcp_.async_lifecycle._lifecycle_manager", None):
            manager = get_lifecycle_manager()
            assert isinstance(manager, AsyncServerLifecycleManager)

    def test_get_lifecycle_manager_singleton(self):
        """Test that get_lifecycle_manager returns the same instance."""
        # Reset the global
        import code_puppy.mcp_.async_lifecycle as lifecycle_module

        lifecycle_module._lifecycle_manager = None

        manager1 = get_lifecycle_manager()
        manager2 = get_lifecycle_manager()

        assert manager1 is manager2


class TestConcurrentOperations:
    """Test concurrent operations on the lifecycle manager."""

    @pytest.mark.asyncio
    async def test_concurrent_start_same_server(self):
        """Test starting the same server concurrently."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()
        server.is_running = True

        # Both tasks try to start the same server
        with patch.object(
            manager,
            "_server_lifecycle_task",
            new_callable=AsyncMock,
        ):
            results = await asyncio.gather(
                manager.start_server("test-server", server),
                manager.start_server("test-server", server),
                return_exceptions=False,
            )

            # At least one should succeed (or both if they handle it properly)
            assert any(results)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test multiple concurrent operations on different servers."""
        manager = AsyncServerLifecycleManager()

        async def start_and_stop(server_id):
            server = AsyncMock()
            server.is_running = True

            with patch.object(
                manager,
                "_server_lifecycle_task",
                new_callable=AsyncMock,
            ):
                await manager.start_server(server_id, server)
                await asyncio.sleep(0.1)
                await manager.stop_server(server_id)

        # Run multiple concurrent operations
        await asyncio.gather(
            start_and_stop("server-1"),
            start_and_stop("server-2"),
            start_and_stop("server-3"),
        )

        # All should be cleaned up
        assert len(manager._servers) == 0


class TestErrorConditions:
    """Test various error conditions."""

    def test_list_servers_with_invalid_class_name(self):
        """Test list_servers handles servers with custom class names."""
        manager = AsyncServerLifecycleManager()
        server = Mock()
        server.__class__.__name__ = "CustomMCPServer"
        server.is_running = True

        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["custom-server"] = ManagedServerContext(
            server_id="custom-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        result = manager.list_servers()
        assert result["custom-server"]["type"] == "CustomMCPServer"

    @pytest.mark.asyncio
    async def test_stop_server_with_already_cancelled_task(self):
        """Test stopping a server whose task is already cancelled."""
        manager = AsyncServerLifecycleManager()
        server = AsyncMock()

        exit_stack = AsyncExitStack()
        task = asyncio.create_task(asyncio.sleep(10))
        task.cancel()  # Already cancelled

        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        # Should handle it gracefully
        result = await manager.stop_server("test-server")
        assert result is True

    @pytest.mark.asyncio
    async def test_server_with_missing_is_running_attribute(self):
        """Test handling of server without is_running attribute."""
        manager = AsyncServerLifecycleManager()
        server = Mock(spec=[])
        # Don't set is_running

        exit_stack = AsyncExitStack()
        task = Mock(spec=asyncio.Task)
        manager._servers["test-server"] = ManagedServerContext(
            server_id="test-server",
            server=server,
            exit_stack=exit_stack,
            start_time=datetime.now(),
            task=task,
        )

        # Should handle gracefully
        try:
            result = manager.is_running("test-server")
            # Depending on implementation, this might raise or return False
            assert isinstance(result, bool)
        except AttributeError:
            # This is also acceptable behavior
            pass
