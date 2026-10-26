"""Core hook seams that only plugins call into (so core must test them itself)."""

from __future__ import annotations

import pytest

from code_puppy import callbacks


@pytest.fixture
def phase(monkeypatch):
    """Give a phase a clean callback list for the duration of one test."""

    def _clean(name: str) -> str:
        monkeypatch.setitem(callbacks._callbacks, name, [])
        return name

    return _clean


@pytest.mark.parametrize(
    "name, dispatch",
    [
        (
            "check_claude_oauth_token_expiry",
            callbacks.on_check_claude_oauth_token_expiry,
        ),
        ("refresh_claude_oauth_token", callbacks.on_refresh_claude_oauth_token),
        ("load_claude_oauth_models", callbacks.on_load_claude_oauth_models),
        ("claude_oauth_authenticate", callbacks.on_claude_oauth_authenticate),
    ],
)
def test_claude_oauth_capabilities_dispatch_to_the_plugin(phase, name, dispatch):
    phase(name)  # isolate from any real plugin an earlier test loaded
    assert dispatch() == []  # plugin not loaded: core sees "no answer"
    callbacks.register_callback(name, lambda: "from-plugin")
    assert dispatch() == ["from-plugin"]


async def test_async_callback_in_sync_trigger_under_a_running_loop_is_undecided(phase):
    """Can't await inside a running loop: report None and don't leak the coroutine."""
    ran = []

    async def plugin():
        ran.append(True)

    callbacks.register_callback(phase("custom_command_help"), plugin)
    assert callbacks._trigger_callbacks_sync("custom_command_help") == [None]
    assert ran == []


def test_thinking_filters_chain_and_a_failing_filter_changes_nothing(phase):
    def shout(text, **_):
        return text.upper()

    def explode(text, **_):
        raise RuntimeError("boom")

    def not_a_string(text, **_):
        return 42

    name = phase("thinking_display_filter")
    for callback in (shout, explode, not_a_string):
        callbacks.register_callback(name, callback)
    result = callbacks.on_thinking_display_filter(
        "hmm", stream_id=object(), part_index=0, final=True
    )
    assert result == "HMM"
