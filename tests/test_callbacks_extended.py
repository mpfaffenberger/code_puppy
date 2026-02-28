import asyncio
from unittest.mock import patch

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    count_callbacks,
    get_callbacks,
    on_custom_command,
    on_edit_file,
    on_load_model_config,
    on_post_tool_call,
    on_pre_tool_call,
    on_startup,
    on_stream_event,
    register_callback,
    unregister_callback,
)


class TestCallbacksExtended:
    """Test code_puppy/callbacks.py callback system."""

    def setup_method(self):
        """Clean up callbacks before each test."""
        clear_callbacks()

    def test_register_callback(self):
        """Test callback registration."""

        def test_callback():
            return "test"

        # Register callback for startup phase
        register_callback("startup", test_callback)

        # Verify callback was registered
        callbacks = get_callbacks("startup")
        assert len(callbacks) == 1
        assert callbacks[0] == test_callback

        # Verify count
        assert count_callbacks("startup") == 1
        assert count_callbacks() == 1

    def test_register_multiple_callbacks(self):
        """Test registering multiple callbacks for the same phase."""

        def callback1():
            return "1"

        def callback2():
            return "2"

        def callback3():
            return "3"

        register_callback("startup", callback1)
        register_callback("startup", callback2)
        register_callback("shutdown", callback3)

        assert count_callbacks("startup") == 2
        assert count_callbacks("shutdown") == 1
        assert count_callbacks() == 3

    def test_register_callback_invalid_phase(self):
        """Test registering callback with invalid phase raises error."""

        def test_callback():
            return "test"

        with pytest.raises(ValueError, match="Unsupported phase"):
            register_callback("invalid_phase", test_callback)

    def test_register_callback_non_callable(self):
        """Test registering non-callable raises error."""
        with pytest.raises(TypeError, match="Callback must be callable"):
            register_callback("startup", "not_a_function")

    def test_unregister_callback(self):
        """Test callback unregistration."""

        def test_callback():
            return "test"

        register_callback("startup", test_callback)
        assert count_callbacks("startup") == 1

        # Unregister successfully
        result = unregister_callback("startup", test_callback)
        assert result is True
        assert count_callbacks("startup") == 0

        # Try to unregister again
        result = unregister_callback("startup", test_callback)
        assert result is False

    def test_clear_callbacks_specific_phase(self):
        """Test clearing callbacks for a specific phase."""

        def callback1():
            return "1"

        def callback2():
            return "2"

        register_callback("startup", callback1)
        register_callback("shutdown", callback2)

        clear_callbacks("startup")

        assert count_callbacks("startup") == 0
        assert count_callbacks("shutdown") == 1

    def test_clear_callbacks_all(self):
        """Test clearing all callbacks."""

        def callback1():
            return "1"

        def callback2():
            return "2"

        register_callback("startup", callback1)
        register_callback("shutdown", callback2)

        clear_callbacks()

        assert count_callbacks() == 0

    @pytest.mark.asyncio
    async def test_execute_callbacks_async(self):
        """Test async callback execution."""

        def test_callback():
            return "test_result"

        register_callback("startup", test_callback)

        results = await on_startup()

        assert len(results) == 1
        assert results[0] == "test_result"

    @pytest.mark.asyncio
    async def test_execute_multiple_callbacks_async(self):
        """Test executing multiple async callbacks."""

        def callback1():
            return "result1"

        def callback2():
            return "result2"

        register_callback("startup", callback1)
        register_callback("startup", callback2)

        results = await on_startup()

        assert len(results) == 2
        assert results[0] == "result1"
        assert results[1] == "result2"

    def test_execute_callbacks_sync(self):
        """Test sync callback execution."""

        def test_callback():
            return "sync_result"

        register_callback("load_model_config", test_callback)

        results = on_load_model_config()

        assert len(results) == 1
        assert results[0] == "sync_result"

    def test_execute_callbacks_with_arguments(self):
        """Test callback execution with arguments."""

        def test_callback(file_path, content):
            return f"edited {file_path}"

        register_callback("edit_file", test_callback)

        results = on_edit_file("test.txt", "content")

        assert len(results) == 1
        assert results[0] == "edited test.txt"

    @pytest.mark.asyncio
    async def test_execute_callbacks_with_exception(self):
        """Test error handling in callbacks."""

        def failing_callback():
            raise Exception("Test error")

        register_callback("startup", failing_callback)

        # Should not raise exception, should return None for failed callback
        with patch("code_puppy.callbacks.logger") as mock_logger:
            results = await on_startup()

            assert len(results) == 1
            assert results[0] is None
            # Verify error was logged
            mock_logger.error.assert_called_once()

    def test_execute_callbacks_sync_with_exception(self):
        """Test error handling in sync callbacks."""

        def failing_callback():
            raise Exception("Test error")

        register_callback("load_model_config", failing_callback)

        with patch("code_puppy.callbacks.logger") as mock_logger:
            results = on_load_model_config()

            assert len(results) == 1
            assert results[0] is None
            mock_logger.error.assert_called_once()

    def test_execute_async_callback_in_sync_context(self):
        """Test async callback executed from sync trigger."""

        async def async_callback():
            await asyncio.sleep(0.001)
            return "async_result"

        register_callback("load_model_config", async_callback)

        # Run from sync context (not in async test)
        results = on_load_model_config()

        assert len(results) == 1
        assert results[0] == "async_result"

    def test_custom_command_callback(self):
        """Test custom command callback execution."""

        def test_callback(command, name):
            return True

        register_callback("custom_command", test_callback)

        results = on_custom_command("/test command", "test")

        assert len(results) == 1
        assert results[0] is True

    @pytest.mark.asyncio
    async def test_no_callbacks_registered(self):
        """Test behavior when no callbacks are registered."""
        results = await on_startup()
        assert results == []

        sync_results = on_load_model_config()
        assert sync_results == []

    def test_get_callbacks_returns_copy(self):
        """Test that get_callbacks returns a copy, not the original list."""

        def test_callback():
            return "test"

        register_callback("startup", test_callback)

        callbacks1 = get_callbacks("startup")
        callbacks2 = get_callbacks("startup")

        # Modifying one shouldn't affect the other
        def extra_callback():
            return "extra"

        callbacks1.append(extra_callback)

        assert len(callbacks1) == 2
        assert len(callbacks2) == 1
        assert len(get_callbacks("startup")) == 1


class TestPreToolCallCallback:
    """Test on_pre_tool_call callback hook."""

    def setup_method(self):
        """Clean up callbacks before each test."""
        clear_callbacks()

    @pytest.mark.asyncio
    async def test_pre_tool_call_receives_correct_args(self):
        """Test that pre_tool_call callbacks receive tool_name, tool_args, context."""
        captured_args = []

        async def capture_callback(tool_name, tool_args, context):
            captured_args.append((tool_name, tool_args, context))
            return "captured"

        register_callback("pre_tool_call", capture_callback)

        test_tool_args = {"file_path": "test.py", "content": "hello"}
        test_context = {"session_id": "abc123"}

        results = await on_pre_tool_call("edit_file", test_tool_args, test_context)

        assert len(results) == 1
        assert results[0] == "captured"
        assert len(captured_args) == 1
        assert captured_args[0][0] == "edit_file"
        assert captured_args[0][1] == test_tool_args
        assert captured_args[0][2] == test_context

    @pytest.mark.asyncio
    async def test_pre_tool_call_multiple_callbacks(self):
        """Test that multiple pre_tool_call callbacks are all called."""
        call_order = []

        async def callback1(tool_name, tool_args, context):
            call_order.append("callback1")
            return 1

        async def callback2(tool_name, tool_args, context):
            call_order.append("callback2")
            return 2

        def callback3_sync(tool_name, tool_args, context):
            call_order.append("callback3")
            return 3

        register_callback("pre_tool_call", callback1)
        register_callback("pre_tool_call", callback2)
        register_callback("pre_tool_call", callback3_sync)

        results = await on_pre_tool_call("list_files", {}, None)

        assert len(results) == 3
        assert results == [1, 2, 3]
        assert call_order == ["callback1", "callback2", "callback3"]

    @pytest.mark.asyncio
    async def test_pre_tool_call_error_handling(self):
        """Test that callback errors don't crash the system."""
        results_collected = []

        async def failing_callback(tool_name, tool_args, context):
            raise RuntimeError("Callback exploded!")

        async def working_callback(tool_name, tool_args, context):
            results_collected.append("working")
            return "success"

        register_callback("pre_tool_call", failing_callback)
        register_callback("pre_tool_call", working_callback)

        with patch("code_puppy.callbacks.logger") as mock_logger:
            results = await on_pre_tool_call("run_shell", {"cmd": "ls"}, None)

            # First callback failed (None), second succeeded
            assert len(results) == 2
            assert results[0] is None
            assert results[1] == "success"
            assert len(results_collected) == 1
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_tool_call_with_none_context(self):
        """Test pre_tool_call works when context is None."""
        received_context = []

        async def check_context(tool_name, tool_args, context):
            received_context.append(context)

        register_callback("pre_tool_call", check_context)

        await on_pre_tool_call("grep", {"pattern": "foo"}, None)

        assert received_context == [None]


class TestPostToolCallCallback:
    """Test on_post_tool_call callback hook."""

    def setup_method(self):
        """Clean up callbacks before each test."""
        clear_callbacks()

    @pytest.mark.asyncio
    async def test_post_tool_call_receives_all_args(self):
        """Test that callbacks receive tool_name, tool_args, result, duration_ms, context."""
        captured_args = []

        async def capture_callback(tool_name, tool_args, result, duration_ms, context):
            captured_args.append(
                {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "result": result,
                    "duration_ms": duration_ms,
                    "context": context,
                }
            )
            return "logged"

        register_callback("post_tool_call", capture_callback)

        test_args = {"file_path": "/tmp/test.txt"}
        test_result = {"success": True, "content": "file content"}
        test_context = {"agent": "code_puppy"}

        results = await on_post_tool_call(
            "read_file", test_args, test_result, 42.5, test_context
        )

        assert len(results) == 1
        assert results[0] == "logged"
        assert len(captured_args) == 1

        captured = captured_args[0]
        assert captured["tool_name"] == "read_file"
        assert captured["tool_args"] == test_args
        assert captured["result"] == test_result
        assert captured["duration_ms"] == 42.5
        assert captured["context"] == test_context

    @pytest.mark.asyncio
    async def test_post_tool_call_duration_is_positive_float(self):
        """Test that duration_ms is a positive float."""
        durations = []

        async def capture_duration(tool_name, tool_args, result, duration_ms, context):
            durations.append(duration_ms)

        register_callback("post_tool_call", capture_duration)

        # Test with various positive floats
        await on_post_tool_call("tool1", {}, {}, 0.001, None)
        await on_post_tool_call("tool2", {}, {}, 100.5, None)
        await on_post_tool_call("tool3", {}, {}, 9999.99, None)

        assert len(durations) == 3
        for d in durations:
            assert isinstance(d, float)
            assert d > 0

    @pytest.mark.asyncio
    async def test_post_tool_call_multiple_callbacks(self):
        """Test that multiple post_tool_call callbacks are all called."""
        call_order = []

        async def logger_callback(tool_name, tool_args, result, duration_ms, context):
            call_order.append(f"logged:{tool_name}")

        async def metrics_callback(tool_name, tool_args, result, duration_ms, context):
            call_order.append(f"metrics:{duration_ms}ms")

        register_callback("post_tool_call", logger_callback)
        register_callback("post_tool_call", metrics_callback)

        await on_post_tool_call(
            "delete_file", {"path": "x.txt"}, {"deleted": True}, 15.3, None
        )

        assert call_order == ["logged:delete_file", "metrics:15.3ms"]

    @pytest.mark.asyncio
    async def test_post_tool_call_error_handling(self):
        """Test that errors in callbacks don't crash the system."""
        successful_calls = []

        async def bad_callback(tool_name, tool_args, result, duration_ms, context):
            raise ValueError("Analytics service unavailable")

        async def good_callback(tool_name, tool_args, result, duration_ms, context):
            successful_calls.append(tool_name)
            return "OK"

        register_callback("post_tool_call", bad_callback)
        register_callback("post_tool_call", good_callback)

        with patch("code_puppy.callbacks.logger") as mock_logger:
            results = await on_post_tool_call(
                "edit_file", {}, {"edited": True}, 200.0, None
            )

            assert len(results) == 2
            assert results[0] is None  # Failed callback
            assert results[1] == "OK"  # Successful callback
            assert successful_calls == ["edit_file"]
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_tool_call_with_error_result(self):
        """Test post_tool_call with an error result from the tool."""
        captured_results = []

        async def capture_result(tool_name, tool_args, result, duration_ms, context):
            captured_results.append(result)

        register_callback("post_tool_call", capture_result)

        error_result = {"error": "File not found", "success": False}
        await on_post_tool_call("read_file", {}, error_result, 5.0, None)

        assert captured_results[0] == error_result


class TestStreamEventCallback:
    """Test on_stream_event callback hook."""

    def setup_method(self):
        """Clean up callbacks before each test."""
        clear_callbacks()

    @pytest.mark.asyncio
    async def test_stream_event_receives_correct_args(self):
        """Test that callbacks receive event_type, event_data, agent_session_id."""
        captured_events = []

        async def capture_event(event_type, event_data, agent_session_id):
            captured_events.append(
                {
                    "event_type": event_type,
                    "event_data": event_data,
                    "agent_session_id": agent_session_id,
                }
            )

        register_callback("stream_event", capture_event)

        await on_stream_event("token", {"content": "Hello"}, "session-123")

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event["event_type"] == "token"
        assert event["event_data"] == {"content": "Hello"}
        assert event["agent_session_id"] == "session-123"

    @pytest.mark.asyncio
    async def test_stream_event_different_event_types(self):
        """Test different event types are handled correctly."""
        events_by_type = {}

        async def categorize_event(event_type, event_data, agent_session_id):
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event_data)

        register_callback("stream_event", categorize_event)

        # Simulate various streaming events
        await on_stream_event("token", {"content": "foo"}, "sess-1")
        await on_stream_event("tool_call_start", {"tool": "edit_file"}, "sess-1")
        await on_stream_event(
            "tool_call_end", {"tool": "edit_file", "success": True}, "sess-1"
        )
        await on_stream_event("token", {"content": "bar"}, "sess-1")
        await on_stream_event("stream_end", {"reason": "complete"}, "sess-1")

        assert len(events_by_type["token"]) == 2
        assert len(events_by_type["tool_call_start"]) == 1
        assert len(events_by_type["tool_call_end"]) == 1
        assert len(events_by_type["stream_end"]) == 1

    @pytest.mark.asyncio
    async def test_stream_event_with_none_session_id(self):
        """Test stream_event works when agent_session_id is None."""
        captured_session_ids = []

        async def capture_session(event_type, event_data, agent_session_id):
            captured_session_ids.append(agent_session_id)

        register_callback("stream_event", capture_session)

        await on_stream_event("token", {"text": "hi"}, None)

        assert captured_session_ids == [None]

    @pytest.mark.asyncio
    async def test_stream_event_multiple_callbacks(self):
        """Test that multiple stream_event callbacks are all called."""
        call_count = {"logger": 0, "metrics": 0, "ui": 0}

        async def logger_cb(event_type, event_data, agent_session_id):
            call_count["logger"] += 1

        async def metrics_cb(event_type, event_data, agent_session_id):
            call_count["metrics"] += 1

        def ui_cb_sync(event_type, event_data, agent_session_id):
            call_count["ui"] += 1

        register_callback("stream_event", logger_cb)
        register_callback("stream_event", metrics_cb)
        register_callback("stream_event", ui_cb_sync)

        await on_stream_event("token", {}, "s1")

        assert call_count == {"logger": 1, "metrics": 1, "ui": 1}

    @pytest.mark.asyncio
    async def test_stream_event_error_handling(self):
        """Test that errors in stream callbacks don't crash the system."""
        successful_events = []

        async def crashing_callback(event_type, event_data, agent_session_id):
            raise ConnectionError("WebSocket disconnected")

        async def resilient_callback(event_type, event_data, agent_session_id):
            successful_events.append(event_type)
            return "OK"

        register_callback("stream_event", crashing_callback)
        register_callback("stream_event", resilient_callback)

        with patch("code_puppy.callbacks.logger") as mock_logger:
            results = await on_stream_event("token", {"content": "x"}, "sess")

            assert len(results) == 2
            assert results[0] is None  # Crashed
            assert results[1] == "OK"  # Survived
            assert successful_events == ["token"]
            mock_logger.error.assert_called_once()
