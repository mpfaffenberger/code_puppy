"""Tests for the steer_queue plugin + PauseController queue operations.

New contract: mid-run Enter queues by default, /steer injects mid-turn,
/queue manages the queue via TUI, and a '(N pending)' tag rides the
bottom bar's status row.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.messaging.pause_controller import (
    PauseController,
    reset_pause_controller,
)
from code_puppy.plugins.steer_queue import register_callbacks as rc
from code_puppy.plugins.steer_queue.queue_menu import (
    QueueMenuApp,
    QueueMenuState,
    _preview,
)


@pytest.fixture(autouse=True)
def fresh_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


# =========================================================================
# PauseController: peek / replace / pop / listeners
# =========================================================================


def test_peek_does_not_drain():
    pc = PauseController()
    pc.request_steer("one", mode="queue")
    assert pc.peek_pending_steer_queued() == ["one"]
    assert pc.peek_pending_steer_queued() == ["one"]  # still there


def test_replace_swaps_queue_and_drops_blank_entries():
    pc = PauseController()
    pc.request_steer("old", mode="queue")
    pc.replace_pending_steer_queued(["a", "  ", "", "b"])
    assert pc.peek_pending_steer_queued() == ["a", "b"]


def test_pop_next_returns_oldest_then_none():
    pc = PauseController()
    pc.request_steer("first", mode="queue")
    pc.request_steer("second", mode="queue")
    assert pc.pop_next_steer_queued() == "first"
    assert pc.pop_next_steer_queued() == "second"
    assert pc.pop_next_steer_queued() is None


def test_listener_fires_on_every_queue_mutation():
    pc = PauseController()
    counts = []
    pc.add_steer_queue_listener(counts.append)

    pc.request_steer("a", mode="queue")  # -> 1
    pc.request_steer("b", mode="queue")  # -> 2
    pc.pop_next_steer_queued()  # -> 1
    pc.replace_pending_steer_queued(["x", "y", "z"])  # -> 3
    pc.drain_pending_steer_queued()  # -> 0
    assert counts == [1, 2, 1, 3, 0]


def test_listener_fires_for_now_mode_addition():
    """``/steer`` (now-mode) now triggers the listener -- so the status
    bar can show a '(N pending)' tag from the moment the user submits."""
    pc = PauseController()
    counts = []
    pc.add_steer_queue_listener(counts.append)
    pc.request_steer("inject me", mode="now")
    assert counts == [1]


def test_listener_fires_for_now_mode_drain():
    pc = PauseController()
    counts = []
    pc.request_steer("a", mode="now")  # fill before listener attaches
    pc.add_steer_queue_listener(counts.append)
    pc.drain_pending_steer_now()
    assert counts == [0]


def test_listener_total_count_includes_both_queues():
    pc = PauseController()
    counts = []
    pc.add_steer_queue_listener(counts.append)
    pc.request_steer("now one", mode="now")
    pc.request_steer("queued one", mode="queue")
    # After the second request the total across both queues is 2.
    assert counts == [1, 2]
    assert counts[-1] == 2


def test_drain_all_notifies_when_queued_items_existed():
    pc = PauseController()
    counts = []
    pc.request_steer("q", mode="queue")
    pc.add_steer_queue_listener(counts.append)
    pc.drain_pending_steer()
    assert counts == [0]


def test_drain_all_notifies_when_only_now_queue_had_items():
    pc = PauseController()
    counts = []
    pc.request_steer("now-only", mode="now")
    pc.add_steer_queue_listener(counts.append)
    pc.drain_pending_steer()
    assert counts == [0]


def test_listener_not_fired_for_empty_drain():
    pc = PauseController()
    counts = []
    pc.add_steer_queue_listener(counts.append)
    pc.drain_pending_steer_now()  # empty: no event
    pc.drain_pending_steer_queued()  # empty: no event
    pc.drain_pending_steer()  # empty: no event
    assert counts == []


def test_broken_listener_does_not_break_mutations():
    pc = PauseController()

    def boom(_count):
        raise RuntimeError("bad listener")

    pc.add_steer_queue_listener(boom)
    pc.request_steer("still fine", mode="queue")  # must not raise
    assert pc.peek_pending_steer_queued() == ["still fine"]


# =========================================================================
# Full-screen queue menu state
# =========================================================================


def test_queue_preview_collapses_whitespace_and_truncates():
    assert _preview("one\n\n two", width=20) == "one two"
    assert _preview("abcdefghijklmnopqrstuvwxyz", width=10) == "abcdefghi…"


def test_queue_state_adds_and_edits_prompts():
    pc = PauseController()
    state = QueueMenuState(pc)

    state.begin_add()
    assert state.save("  first prompt  ") is True
    assert pc.peek_pending_steer_queued() == ["first prompt"]
    assert state.selected == 0

    assert state.begin_edit() is True
    assert state.save("updated prompt") is True
    assert pc.peek_pending_steer_queued() == ["updated prompt"]
    assert state.notice == "Prompt updated"


def test_queue_state_rejects_blank_prompt_without_leaving_editor():
    state = QueueMenuState(PauseController())
    state.begin_add()
    assert state.save("  \n ") is False
    assert state.editing is True
    assert state.notice == "Prompt cannot be blank"


def test_queue_state_delete_requires_second_press_and_clamps_selection():
    pc = PauseController()
    pc.replace_pending_steer_queued(["one", "two"])
    state = QueueMenuState(pc, selected=1)

    assert state.request_delete() is False
    assert pc.peek_pending_steer_queued() == ["one", "two"]
    assert state.request_delete() is True
    assert pc.peek_pending_steer_queued() == ["one"]
    assert state.selected == 0


def test_queue_state_selection_change_disarms_delete():
    pc = PauseController()
    pc.replace_pending_steer_queued(["one", "two"])
    state = QueueMenuState(pc)
    state.request_delete()
    state.move_selection(1)
    assert state.delete_armed is None


def test_queue_state_reorders_items_and_tracks_selection():
    pc = PauseController()
    pc.replace_pending_steer_queued(["one", "two", "three"])
    state = QueueMenuState(pc, selected=1)

    assert state.reorder(-1) is True
    assert pc.peek_pending_steer_queued() == ["two", "one", "three"]
    assert state.selected == 0
    assert state.reorder(-1) is False


def test_queue_menu_app_constructs_with_empty_and_populated_queue():
    empty_app = QueueMenuApp(PauseController())
    assert empty_app.application.full_screen is True

    pc = PauseController()
    pc.replace_pending_steer_queued(["inspect this", "then do that"])
    app = QueueMenuApp(pc)
    assert app.state.selected_text == "inspect this"
    assert "inspect this" in app._editor_buffer.text


def test_queue_menu_uses_shared_semantic_roles_without_local_palette():
    pc = PauseController()
    pc.replace_pending_steer_queued(["one", "two"])
    app = QueueMenuApp(pc)

    assert app._render_header()[0][0] == "class:tui.title"
    assert {style for style, _ in app._render_list()} >= {
        "class:tui.selected",
        "class:tui.selected class:tui.muted",
        "class:tui.body",
        "class:tui.body class:tui.muted",
    }
    assert app._render_notice()[0][0] == "class:tui.warning"
    assert {style for style, _ in app._render_footer()} == {
        "class:tui.help",
        "class:tui.help-key",
    }
    app.state.editing = True
    assert app._editor_prefix()[0][0] == "class:tui.label"


# =========================================================================
# /steer command handler
# =========================================================================


def test_steer_bare_shows_usage():
    infos = []
    with patch.object(rc, "_emit_info", infos.append):
        assert rc._handle_steer("/steer") is True
    assert any("Usage" in m for m in infos)


def test_steer_at_idle_warns_and_does_not_queue():
    warnings = []
    with (
        patch.object(rc, "_emit_warning", warnings.append),
        patch("code_puppy.messaging.run_ui.is_run_active", return_value=False),
    ):
        assert rc._handle_steer("/steer do a thing") is True
    assert warnings, "expected an idle warning"
    from code_puppy.messaging.pause_controller import get_pause_controller

    assert get_pause_controller().has_pending_steer() is False


def test_steer_mid_run_lands_in_now_queue():
    with patch("code_puppy.messaging.run_ui.is_run_active", return_value=True):
        assert rc._handle_steer("/steer focus please") is True
    from code_puppy.messaging.pause_controller import get_pause_controller

    assert get_pause_controller().drain_pending_steer_now() == ["focus please"]


def test_unrelated_command_returns_none():
    assert rc._handle_custom_command("/other", "other") is None


# =========================================================================
# Status suffix wiring
# =========================================================================


class FakeBar:
    def __init__(self):
        self.suffixes = []

    def set_status_suffix(self, text):
        self.suffixes.append(text)


def test_suffix_updates_and_clears(monkeypatch):
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    rc._update_status_suffix(3)
    rc._update_status_suffix(0)
    assert fake.suffixes == [" (3 pending)", ""]


def test_startup_wires_listener_end_to_end(monkeypatch):
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    rc._on_startup()
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    pc.request_steer("queued thing", mode="queue")
    pc.drain_pending_steer_queued()
    assert fake.suffixes == [" (1 pending)", ""]


def test_startup_wires_steer_listener_for_now_mode(monkeypatch):
    """/steer (now-mode) should tag the bar from submit until drain."""
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    rc._on_startup()
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    pc.request_steer("focus on the tests", mode="now")
    pc.drain_pending_steer_now()
    assert fake.suffixes == [" (1 pending)", ""]
