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
