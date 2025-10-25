"""Comprehensive unit tests for code_puppy.callbacks module.

Tests callback registration, triggering, and lifecycle management.
"""
import asyncio
import pytest
from unittest.mock import Mock, MagicMock

from code_puppy.callbacks import (
    register_callback,
    unregister_callback,
    clear_callbacks,
    get_callbacks,
    count_callbacks,
    on_startup,
    on_shutdown,
    on_invoke_agent,
    on_agent_exception,
    on_version_check,
    on_load_model_config,
    on_edit_file,
    on_delete_file,
    on_run_shell_command,
    on_agent_reload,
    on_load_prompt,
    on_custom_command_help,
    on_custom_command,
)


class TestCallbackRegistration:
    """Test callback registration and management."""
    
    def teardown_method(self):
        """Clear all callbacks after each test."""
        clear_callbacks()
    
    def test_register_callback_success(self):
        """Test successful callback registration."""
        callback = Mock(__name__="test_callback")
        register_callback("startup", callback)
        
        callbacks = get_callbacks("startup")
        assert len(callbacks) == 1
        assert callbacks[0] == callback
    
    def test_register_multiple_callbacks(self):
        """Test registering multiple callbacks to same phase."""
        cb1, cb2, cb3 = Mock(__name__="cb1"), Mock(__name__="cb2"), Mock(__name__="cb3")
        
        register_callback("startup", cb1)
        register_callback("startup", cb2)
        register_callback("startup", cb3)
        
        callbacks = get_callbacks("startup")
        assert len(callbacks) == 3
        assert callbacks == [cb1, cb2, cb3]
    
    def test_register_callback_invalid_phase(self):
        """Test registration with invalid phase raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported phase"):
            register_callback("invalid_phase", Mock())
    
    def test_register_non_callable_raises_error(self):
        """Test registration with non-callable raises TypeError."""
        with pytest.raises(TypeError, match="Callback must be callable"):
            register_callback("startup", "not_a_function")
    
    def test_register_callback_different_phases(self):
        """Test registering callbacks to different phases."""
        cb_startup = Mock(__name__="cb_startup")
        cb_shutdown = Mock(__name__="cb_shutdown")
        
        register_callback("startup", cb_startup)
        register_callback("shutdown", cb_shutdown)
        
        assert get_callbacks("startup") == [cb_startup]
        assert get_callbacks("shutdown") == [cb_shutdown]


class TestCallbackUnregistration:
    """Test callback unregistration."""
    
    def teardown_method(self):
        clear_callbacks()
    
    def test_unregister_callback_success(self):
        """Test successful callback unregistration."""
        callback = Mock(__name__="callback")
        register_callback("startup", callback)
        
        result = unregister_callback("startup", callback)
        
        assert result is True
        assert get_callbacks("startup") == []
    
    def test_unregister_nonexistent_callback(self):
        """Test unregistering callback that was never registered."""
        callback = Mock()
        result = unregister_callback("startup", callback)
        
        assert result is False
    
    def test_unregister_from_invalid_phase(self):
        """Test unregistering from invalid phase."""
        callback = Mock()
        result = unregister_callback("invalid_phase", callback)
        
        assert result is False
    
    def test_unregister_one_of_multiple(self):
        """Test unregistering one callback when multiple exist."""
        cb1, cb2, cb3 = Mock(__name__="cb1"), Mock(__name__="cb2"), Mock(__name__="cb3")
        
        register_callback("startup", cb1)
        register_callback("startup", cb2)
        register_callback("startup", cb3)
        
        unregister_callback("startup", cb2)
        
        callbacks = get_callbacks("startup")
        assert len(callbacks) == 2
        assert cb2 not in callbacks
        assert cb1 in callbacks
        assert cb3 in callbacks


class TestClearCallbacks:
    """Test clearing callbacks."""
    
    def teardown_method(self):
        clear_callbacks()
    
    def test_clear_specific_phase(self):
        """Test clearing callbacks for specific phase."""
        register_callback("startup", Mock(__name__="m1"))
        register_callback("startup", Mock(__name__="m2"))
        register_callback("shutdown", Mock(__name__="m3"))
        
        clear_callbacks("startup")
        
        assert get_callbacks("startup") == []
        assert len(get_callbacks("shutdown")) == 1
    
    def test_clear_all_phases(self):
        """Test clearing all callbacks."""
        register_callback("startup", Mock(__name__="m1"))
        register_callback("shutdown", Mock(__name__="m2"))
        register_callback("edit_file", Mock(__name__="m3"))
        
        clear_callbacks()
        
        assert get_callbacks("startup") == []
        assert get_callbacks("shutdown") == []
        assert get_callbacks("edit_file") == []


class TestGetCallbacks:
    """Test getting callbacks."""
    
    def teardown_method(self):
        clear_callbacks()
    
    def test_get_callbacks_returns_copy(self):
        """Test get_callbacks returns a copy, not reference."""
        callback = Mock(__name__="callback")
        register_callback("startup", callback)
        
        callbacks1 = get_callbacks("startup")
        callbacks2 = get_callbacks("startup")
        
        # Should be equal but not same object
        assert callbacks1 == callbacks2
        assert callbacks1 is not callbacks2
    
    def test_get_callbacks_empty_phase(self):
        """Test getting callbacks from phase with none registered."""
        callbacks = get_callbacks("startup")
        assert callbacks == []
    
    def test_get_callbacks_nonexistent_phase(self):
        """Test getting callbacks from invalid phase."""
        callbacks = get_callbacks("nonexistent")
        assert callbacks == []


class TestCountCallbacks:
    """Test counting callbacks."""
    
    def teardown_method(self):
        clear_callbacks()
    
    def test_count_callbacks_single_phase(self):
        """Test counting callbacks in single phase."""
        register_callback("startup", Mock(__name__="m1"))
        register_callback("startup", Mock(__name__="m2"))
        
        assert count_callbacks("startup") == 2
    
    def test_count_callbacks_all_phases(self):
        """Test counting callbacks across all phases."""
        register_callback("startup", Mock(__name__="m1"))
        register_callback("startup", Mock(__name__="m2"))
        register_callback("shutdown", Mock(__name__="m3"))
        register_callback("edit_file", Mock(__name__="m4"))
        
        assert count_callbacks() == 4
    
    def test_count_callbacks_empty(self):
        """Test counting when no callbacks registered."""
        assert count_callbacks() == 0
        assert count_callbacks("startup") == 0


class TestAsyncCallbackTriggers:
    """Test async callback triggering."""
    
    def teardown_method(self):
        clear_callbacks()
    
    @pytest.mark.asyncio
    async def test_on_startup_triggers_callbacks(self):
        """Test on_startup triggers registered callbacks."""
        callback = Mock(__name__="callback", return_value="result")
        register_callback("startup", callback)
        
        results = await on_startup()
        
        assert len(results) == 1
        assert results[0] == "result"
        callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_on_shutdown_triggers_callbacks(self):
        """Test on_shutdown triggers callbacks."""
        callback = Mock(__name__="callback", return_value=42)
        register_callback("shutdown", callback)
        
        results = await on_shutdown()
        
        assert results == [42]
        callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_on_invoke_agent_with_args(self):
        """Test on_invoke_agent passes arguments to callbacks."""
        callback = Mock(__name__="callback")
        register_callback("invoke_agent", callback)
        
        await on_invoke_agent("agent_name", key="value")
        
        callback.assert_called_once_with("agent_name", key="value")
    
    @pytest.mark.asyncio
    async def test_on_agent_exception_with_exception(self):
        """Test on_agent_exception passes exception to callbacks."""
        callback = Mock(__name__="callback")
        register_callback("agent_exception", callback)
        
        exc = ValueError("test error")
        await on_agent_exception(exc)
        
        callback.assert_called_once_with(exc)
    
    @pytest.mark.asyncio
    async def test_on_version_check(self):
        """Test on_version_check triggers callbacks."""
        callback = Mock(__name__="callback")
        register_callback("version_check", callback)
        
        results = await on_version_check("1.0.0")
        
        callback.assert_called_once_with("1.0.0")
    
    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(self):
        """Test async callbacks are properly awaited."""
        async def async_callback():
            await asyncio.sleep(0.001)
            return "async_result"
        
        register_callback("startup", async_callback)
        
        results = await on_startup()
        
        assert results == ["async_result"]
    
    @pytest.mark.asyncio
    async def test_callback_exception_handled(self):
        """Test exceptions in callbacks are handled gracefully."""
        def failing_callback():
            raise RuntimeError("callback failed")
        
        def working_callback():
            return "success"
        
        register_callback("startup", failing_callback)
        register_callback("startup", working_callback)
        
        results = await on_startup()
        
        # First callback fails (returns None), second succeeds
        assert len(results) == 2
        assert results[0] is None
        assert results[1] == "success"


class TestSyncCallbackTriggers:
    """Test synchronous callback triggering."""
    
    def teardown_method(self):
        clear_callbacks()
    
    def test_on_load_model_config(self):
        """Test on_load_model_config triggers callbacks."""
        callback = Mock(__name__="callback", return_value={"model": "gpt-4"})
        register_callback("load_model_config", callback)
        
        results = on_load_model_config("config_name")
        
        assert results == [{"model": "gpt-4"}]
        callback.assert_called_once_with("config_name")
    
    def test_on_edit_file(self):
        """Test on_edit_file triggers callbacks."""
        callback = Mock(__name__="callback")
        register_callback("edit_file", callback)
        
        on_edit_file("file.py", "content")
        
        callback.assert_called_once_with("file.py", "content")
    
    def test_on_delete_file(self):
        """Test on_delete_file triggers callbacks."""
        callback = Mock(__name__="callback")
        register_callback("delete_file", callback)
        
        on_delete_file("file.py")
        
        callback.assert_called_once_with("file.py")
    
    def test_on_run_shell_command(self):
        """Test on_run_shell_command triggers callbacks."""
        callback = Mock(__name__="callback")
        register_callback("run_shell_command", callback)
        
        on_run_shell_command("ls -la")
        
        callback.assert_called_once_with("ls -la")
    
    def test_on_agent_reload(self):
        """Test on_agent_reload triggers callbacks."""
        callback = Mock(__name__="callback")
        register_callback("agent_reload", callback)
        
        on_agent_reload()
        
        callback.assert_called_once()
    
    def test_on_load_prompt(self):
        """Test on_load_prompt triggers callbacks."""
        callback = Mock(__name__="callback", return_value="prompt content")
        register_callback("load_prompt", callback)
        
        results = on_load_prompt()
        
        assert results == ["prompt content"]
    
    def test_on_custom_command_help(self):
        """Test on_custom_command_help triggers callbacks."""
        callback = Mock(__name__="callback", return_value=[("cmd1", "desc1")])
        register_callback("custom_command_help", callback)
        
        results = on_custom_command_help()
        
        assert results == [[("cmd1", "desc1")]]
    
    def test_on_custom_command(self):
        """Test on_custom_command triggers callbacks with command and name."""
        callback = Mock(__name__="callback", return_value=True)
        register_callback("custom_command", callback)
        
        results = on_custom_command("/foo bar", "foo")
        
        callback.assert_called_once_with("/foo bar", "foo")
        assert results == [True]


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def teardown_method(self):
        clear_callbacks()
    
    @pytest.mark.asyncio
    async def test_no_callbacks_registered(self):
        """Test triggering phase with no callbacks."""
        results = await on_startup()
        assert results == []
    
    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_fail(self):
        """Test all callbacks failing."""
        def fail1():
            raise ValueError("fail1")
        
        def fail2():
            raise RuntimeError("fail2")
        
        register_callback("startup", fail1)
        register_callback("startup", fail2)
        
        results = await on_startup()
        
        assert results == [None, None]
    
    def test_sync_trigger_with_no_callbacks(self):
        """Test sync trigger with no callbacks."""
        results = on_load_model_config()
        assert results == []
