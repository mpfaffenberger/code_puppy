"""Steer-queue pub-sub and queued-turn bookkeeping on the PauseController.

This is the core API the steer-queue plugin's "(N queued)" UI builds on.
"""

from __future__ import annotations

from code_puppy.messaging.pause_controller import PauseController


def _controller_with_listener():
    controller = PauseController()
    counts: list[int] = []
    controller.add_steer_queue_listener(counts.append)
    controller.add_steer_queue_listener(counts.append)  # duplicates are ignored
    return controller, counts


def test_queued_turns_pop_oldest_first_and_report_totals():
    controller, counts = _controller_with_listener()
    controller.request_steer("now-1", mode="now")
    controller.request_steer("q-1", mode="queue")
    controller.request_steer("q-2", mode="queue")
    assert controller.pending_steer_counts() == (1, 2)
    counts.clear()

    assert controller.pop_next_steer_queued() == "q-1"
    assert controller.pop_next_steer_queued() == "q-2"
    assert controller.pop_next_steer_queued() is None
    # One notification per pop, carrying the TOTAL (now + queued) count.
    assert counts == [2, 1]
    assert controller.pending_steer_counts() == (1, 0)


def test_replace_drops_blank_entries_and_notifies_even_at_zero():
    controller, counts = _controller_with_listener()
    controller.replace_pending_steer_queued(["keep", "", "   ", "also"])
    assert controller.peek_pending_steer_queued() == ["keep", "also"]
    controller.replace_pending_steer_queued([])
    assert counts == [2, 0]  # zero still fires so the UI can clear its tag


def test_a_broken_listener_cannot_starve_the_others():
    controller = PauseController()
    seen: list[int] = []

    def broken(count: int) -> None:
        raise RuntimeError("ui exploded")

    controller.add_steer_queue_listener(broken)
    controller.add_steer_queue_listener(seen.append)
    controller.replace_pending_steer_queued(["x"])
    assert seen == [1]
