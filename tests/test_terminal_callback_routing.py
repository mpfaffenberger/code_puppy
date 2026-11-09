"""Non-executed terminal updates reach observers, not tool-ran consumers."""

from unittest.mock import AsyncMock

import pytest

from code_puppy import callbacks


@pytest.fixture(autouse=True)
def isolated_post_callbacks():
    original = callbacks.get_callbacks("post_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    yield
    callbacks.clear_callbacks("post_tool_call")
    for callback in original:
        callbacks.register_callback("post_tool_call", callback)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["blocked", "cancelled"])
async def test_nonexecuted_terminal_only_reaches_opted_in_observers(outcome):
    ordinary = AsyncMock()
    observer = AsyncMock()
    callbacks.terminal_tool_observer(observer)
    callbacks.register_callback("post_tool_call", ordinary)
    callbacks.register_callback("post_tool_call", observer)

    await callbacks.on_post_tool_call(
        "write_file",
        {"file_path": "blocked.txt"},
        {"error": "did not execute"},
        0.0,
        {"outcome": outcome, "exception_type": None},
    )

    ordinary.assert_not_awaited()
    observer.assert_awaited_once()


@pytest.mark.asyncio
async def test_released_acp_module_remains_a_terminal_observer():
    ordinary = AsyncMock()
    legacy_acp = AsyncMock()
    legacy_acp.__module__ = "code_puppy_core_plugins.acp.bridge"
    callbacks.register_callback("post_tool_call", ordinary)
    callbacks.register_callback("post_tool_call", legacy_acp)

    await callbacks.on_post_tool_call(
        "shell",
        {"command": "denied"},
        {"blocked": True},
        0.0,
        {"outcome": "blocked", "execution_started": False},
    )

    ordinary.assert_not_awaited()
    legacy_acp.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ok", "error"])
async def test_executed_terminal_reaches_all_consumers(outcome):
    ordinary = AsyncMock()
    observer = AsyncMock()
    callbacks.terminal_tool_observer(observer)
    callbacks.register_callback("post_tool_call", ordinary)
    callbacks.register_callback("post_tool_call", observer)

    await callbacks.on_post_tool_call(
        "write_file",
        {"file_path": "ran.txt"},
        "done" if outcome == "ok" else {"error": "failed"},
        1.0,
        {"outcome": outcome, "exception_type": None, "execution_started": True},
    )

    ordinary.assert_awaited_once()
    observer.assert_awaited_once()


@pytest.mark.asyncio
async def test_execution_phase_cancel_reaches_all_consumers():
    ordinary = AsyncMock()
    observer = AsyncMock()
    callbacks.terminal_tool_observer(observer)
    callbacks.register_callback("post_tool_call", ordinary)
    callbacks.register_callback("post_tool_call", observer)
    context = {
        "outcome": "cancelled",
        "exception_type": "CancelledError",
        "execution_started": True,
    }

    await callbacks.on_post_tool_call(
        "write_file",
        {"file_path": "partially-written.txt"},
        {"cancelled": True, "error": "Tool call cancelled"},
        1.0,
        context,
    )

    ordinary.assert_awaited_once()
    assert ordinary.await_args.args[4] == context
    observer.assert_awaited_once()
