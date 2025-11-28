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
    on_startup,
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
