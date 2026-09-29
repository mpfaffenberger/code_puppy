"""Ctrl+X Ctrl+S: toggle speculative execution."""

import asyncio
from unittest.mock import Mock

import pytest

from code_puppy.messaging import chords, speculation_toggle
from code_puppy.messaging.line_editor import RunningLineEditor
from code_puppy.messaging.speculation_toggle import (
    CHORD_KEY,
    make_speculation_toggle_handler,
    toggle_speculation,
)

CTRL_X = "\x18"


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def up(self, _t):
        return None

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    active = False

    def cancel(self):
        pass


@pytest.fixture
def editor():
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


@pytest.fixture(autouse=True)
def _clean_chords():
    chords.unregister_chord(CHORD_KEY)
    yield
    chords.unregister_chord(CHORD_KEY)


@pytest.fixture
def switch(monkeypatch):
    """In-memory stand-in for the persisted flag plus spies on side effects."""
    state = {"enabled": True}
    monkeypatch.setattr(
        speculation_toggle,
        "get_speculative_code_mode_enabled",
        lambda: state["enabled"],
    )
    monkeypatch.setattr(
        speculation_toggle,
        "set_speculative_code_mode_enabled",
        lambda value: state.__setitem__("enabled", value),
    )
    agent = Mock()
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent", lambda: agent
    )
    monkeypatch.setattr(speculation_toggle, "_refresh_row", Mock())
    emitted = []
    monkeypatch.setattr(
        "code_puppy.messaging.message_queue.emit_info",
        lambda text: emitted.append(text),
    )
    state["agent"] = agent
    state["emitted"] = emitted
    return state


def test_toggle_flips_persists_rebuilds_and_reports(switch):
    assert toggle_speculation() is False
    assert switch["enabled"] is False
    switch["agent"].reload_code_generation_agent.assert_called_once()
    speculation_toggle._refresh_row.assert_called_once()
    assert switch["emitted"] == [
        "Speculation off. Next turn uses plain tool calls. Ctrl+X Ctrl+S to re-enable."
    ]

    assert toggle_speculation() is True
    assert switch["enabled"] is True
    assert switch["emitted"][-1].startswith("Speculation on.")


def test_rebuild_failure_keeps_the_config_write(switch):
    switch["agent"].reload_code_generation_agent.side_effect = RuntimeError("boom")
    assert toggle_speculation() is False
    assert switch["enabled"] is False
    assert len(switch["emitted"]) == 1


def test_chord_hops_to_loop_from_listener_thread(editor, switch):
    async def scenario():
        loop = asyncio.get_running_loop()
        chords.register_chord(
            CHORD_KEY, make_speculation_toggle_handler(lambda: loop), "x"
        )
        # Feed from an executor thread, like the real key listener.
        await loop.run_in_executor(None, editor.feed, CTRL_X + CHORD_KEY)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert switch["enabled"] is False


def test_handler_without_loop_is_noop(editor, switch):
    chords.register_chord(CHORD_KEY, make_speculation_toggle_handler(lambda: None), "x")
    editor.feed(CTRL_X)
    editor.feed(CHORD_KEY)
    assert switch["enabled"] is True


def test_row_collapses_while_speculation_is_off(monkeypatch):
    from code_puppy.messaging.speculation_stats import get_speculation_status

    monkeypatch.setattr(
        "code_puppy.config.get_speculative_code_mode_enabled", lambda: False
    )
    assert get_speculation_status() is None
    monkeypatch.setattr(
        "code_puppy.config.get_speculative_code_mode_enabled", lambda: True
    )
    assert get_speculation_status() is not None
