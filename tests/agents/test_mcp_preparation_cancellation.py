"""Preparation borrows interactive cancellation only until runtime takes over."""

import threading
from unittest.mock import Mock

import pytest

from code_puppy.agents import _key_listeners, _runtime
from code_puppy.agents._run_signals import mcp_preparation_cancellation
from code_puppy.tools import command_runner


@pytest.mark.parametrize("nested_by", ["runtime", "preparation"])
async def test_nested_preparation_leaves_outer_cancel_owner_untouched(
    monkeypatch, nested_by
):
    outer_cancel = Mock()
    monkeypatch.setattr(_runtime, "_active_run_depth", int(nested_by == "runtime"))
    monkeypatch.setattr(
        _key_listeners,
        "_cancel_handler",
        outer_cancel if nested_by == "preparation" else None,
    )
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", outer_cancel)
    acquire = Mock(
        side_effect=AssertionError("Nested preparation must not acquire stdin")
    )
    monkeypatch.setattr(_key_listeners, "acquire_listener", acquire)
    with mcp_preparation_cancellation():
        assert command_runner._AGENT_CANCEL_CB is outer_cancel
    acquire.assert_not_called()
    assert command_runner._AGENT_CANCEL_CB is outer_cancel
    assert _key_listeners._resolve_cancel_handler(None) is (
        outer_cancel if nested_by == "preparation" else None
    )


@pytest.mark.parametrize("failure", ["startup", "listener"])
async def test_preparation_failure_releases_cancel_owner(monkeypatch, failure):
    handle = _key_listeners.KeyListenerHandle(Mock(), threading.Event())
    monkeypatch.setattr(_runtime, "_active_run_depth", 0)
    monkeypatch.setattr(_key_listeners, "_cancel_handler", None)
    monkeypatch.setattr(_key_listeners, "_active_handle", None)
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", None)
    acquire = Mock(return_value=(handle, True))
    if failure == "listener":
        acquire.side_effect = RuntimeError("listener failed")
    monkeypatch.setattr(_key_listeners, "acquire_listener", acquire)
    with pytest.raises(RuntimeError):
        with mcp_preparation_cancellation():
            assert _key_listeners._resolve_cancel_handler(None) is not None
            raise RuntimeError("startup failed")
    assert _key_listeners._resolve_cancel_handler(None) is None
    assert command_runner._AGENT_CANCEL_CB is None
    if failure == "startup":
        assert handle.stop_event.is_set()
        handle.thread.join.assert_called_once_with(timeout=1.0)
    else:
        handle.thread.join.assert_not_called()


async def test_nested_preparation_keeps_the_same_cancel_callback(monkeypatch):
    monkeypatch.setattr(_runtime, "_active_run_depth", 0)
    monkeypatch.setattr(_key_listeners, "_cancel_handler", None)
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", None)
    acquire = Mock(return_value=(None, True))
    monkeypatch.setattr(_key_listeners, "acquire_listener", acquire)
    with mcp_preparation_cancellation():
        outer_cancel = _key_listeners._resolve_cancel_handler(None)
        with mcp_preparation_cancellation():
            assert _key_listeners._resolve_cancel_handler(None) is outer_cancel
        assert _key_listeners._resolve_cancel_handler(None) is outer_cancel
        assert command_runner._AGENT_CANCEL_CB is outer_cancel
    acquire.assert_called_once()
    assert _key_listeners._resolve_cancel_handler(None) is None
    assert command_runner._AGENT_CANCEL_CB is None
