"""Regression coverage for QueuedMessageNavigator x HistoryNavigator interplay.

``up()`` predicts the suppression tail before recording edited drafts via
``_record_edits()``. The caller feeds that tail to
``HistoryNavigator.suppress_recent``. The suppression list
must mirror exactly what ``_record_edits()`` actually wrote (or left
untouched) on disk, in the same newest-first order the pop-matching loop in
``HistoryNavigator.up`` expects -- otherwise the very first mismatch breaks
that loop and nothing gets suppressed, surfacing a stale/duplicate draft
instead of genuine older history.

``HistoryNavigator.up``'s matching loop stays strictly positional and
contiguous-tail (break on the first mismatch, never scan past it): that is
a deliberate tripwire, not generic history filtering. Unrelated history
interleaved between queue-related entries, and older/independent
submissions that happen to share text with a queued item, must remain
visible rather than being silently consumed. ``QueuedMessageNavigator`` is
responsible for handing ``HistoryNavigator`` the *exact* predicted tail --
changed drafts (newest-queued-first) followed by their originals -- not the
other way around.

These tests drive the real ``QueuedMessageNavigator`` against a real,
tmp_path-backed ``HistoryStore``/``HistoryNavigator`` pair -- the same two
classes ``code_puppy/messaging/editor_actions.py`` wires together -- so the
suppression hand-off is exercised exactly as production does it, not
re-implemented.
"""

from __future__ import annotations

import pytest

from code_puppy.messaging.editor_history import HistoryNavigator, HistoryStore
from code_puppy.messaging.editor_queue import QueuedMessageNavigator


class FakeController:
    """Minimal steer-queue stand-in: a plain list, newest-queued at the end."""

    def __init__(self, pending: list[str] | None = None) -> None:
        self.pending = list(pending or [])
        self.restored_oldest_first: list[list[str]] = []

    def pop_latest_steer_queued(self) -> str | None:
        return self.pending.pop() if self.pending else None

    def restore_pending_steer_queued(self, oldest_first: list[str]) -> None:
        self.restored_oldest_first.append(list(oldest_first))
        self.pending = list(oldest_first)


@pytest.fixture
def store(tmp_path):
    return HistoryStore(str(tmp_path / "history.txt"))


@pytest.fixture
def navigator_pair(store, monkeypatch):
    """A (QueuedMessageNavigator, HistoryNavigator) pair sharing one store.

    ``_record_edits`` lazily imports ``save_command_to_history`` from
    ``code_puppy.config`` -- patch that one name so writes land in the same
    tmp_path store the ``HistoryNavigator`` reads from, exactly like
    production shares ``COMMAND_HISTORY_FILE``.
    """
    monkeypatch.setattr("code_puppy.config.save_command_to_history", store.append)

    def build(
        controller: FakeController,
    ) -> tuple[QueuedMessageNavigator, HistoryNavigator]:
        queue_nav = QueuedMessageNavigator(lambda: controller)
        history_nav = HistoryNavigator(store)
        return queue_nav, history_nav

    return build


def fallback_to_history(queue_nav, history_nav, current: str) -> str | None:
    """Replicate editor_actions.apply_action's "up" handling exactly."""
    handled, text, suppressions = queue_nav.up(current)
    if handled:
        return text
    if suppressions:
        history_nav.suppress_recent(suppressions)
    return history_nav.up(text)


# =========================================================================
# One edited item: the reported PUP-987-dependent hypothesis
# =========================================================================


def test_single_edit_up_past_queue_recalls_older_history_not_the_edit(
    store, navigator_pair
):
    store.append("old")
    store.append("a")
    controller = FakeController(pending=["a"])
    queue_nav, history_nav = navigator_pair(controller)

    handled, text, suppressions = queue_nav.up("")
    assert (handled, text, suppressions) == (True, "a", [])

    # User edits "a" -> "a2" in the buffer, then presses Up again with the
    # queue now empty: this is the exact reported scenario.
    result = fallback_to_history(queue_nav, history_nav, "a2")

    assert result == "old", (
        "Up past an edited, now-exhausted queue must recall the entry "
        "that predates the queued item, not the freshly-recorded edit "
        "echo or the stale pre-edit original."
    )


def test_single_edit_persists_only_the_draft_not_a_duplicate_original(
    store, navigator_pair
):
    store.append("old")
    store.append("a")
    controller = FakeController(pending=["a"])
    queue_nav, history_nav = navigator_pair(controller)

    queue_nav.up("")
    fallback_to_history(queue_nav, history_nav, "a2")

    assert store.load() == ["old", "a", "a2"]


# =========================================================================
# Unedited queued prompt: must keep working exactly as before
# =========================================================================


def test_unedited_queued_prompt_up_past_queue_recalls_older_history(
    store, navigator_pair
):
    store.append("old")
    store.append("a")
    controller = FakeController(pending=["a"])
    queue_nav, history_nav = navigator_pair(controller)

    handled, text, _ = queue_nav.up("")
    assert (handled, text) == (True, "a")

    # Recall again unchanged (current == item), so no edit occurred.
    result = fallback_to_history(queue_nav, history_nav, text)

    assert result == "old"
    assert store.load() == ["old", "a"], "unedited recall must not duplicate history"


# =========================================================================
# Multiple edits: must land on disk in chronological (not newest-first) order
# =========================================================================


def test_multiple_edits_recorded_oldest_queued_first(store, navigator_pair):
    store.append("older")
    store.append("a")
    store.append("b")
    # "b" was queued most recently, so it pops first (LIFO).
    controller = FakeController(pending=["a", "b"])
    queue_nav, history_nav = navigator_pair(controller)

    handled, text, _ = queue_nav.up("")  # recalls "b"
    assert (handled, text) == (True, "b")
    handled, text, _ = queue_nav.up("b2")  # edit b -> b2, recall "a"
    assert (handled, text) == (True, "a")

    # Queue now exhausted; "a" gets edited too before falling through.
    result = fallback_to_history(queue_nav, history_nav, "a2")

    assert store.load() == ["older", "a", "b", "a2", "b2"], (
        "edited drafts must be appended oldest-queued-item-first so the "
        "newest-queued item's edit lands newest on disk"
    )
    assert result == "older", (
        "suppression must skip both edited echoes and both pre-edit "
        "originals so Up lands on the entry predating the whole queue"
    )


def test_multiple_items_only_one_edited(store, navigator_pair):
    """Mixed queue: one edited, one recalled unchanged, in the same walk."""
    store.append("older")
    store.append("a")
    store.append("b")
    controller = FakeController(pending=["a", "b"])
    queue_nav, history_nav = navigator_pair(controller)

    queue_nav.up("")  # recalls "b"
    queue_nav.up("b2")  # edit b -> b2, recalls "a"

    # "a" is recalled unchanged this time.
    result = fallback_to_history(queue_nav, history_nav, "a")

    assert store.load() == ["older", "a", "b", "b2"]
    assert result == "older"


# =========================================================================
# Tripwire: the contiguous-tail match must stay bounded, not generic
# =========================================================================


def test_interleaved_unrelated_history_stops_suppression_and_stays_visible(
    store, navigator_pair
):
    """An unrelated submission wedged between two queued items' disk
    records must break the suppression walk and remain reachable -- never
    silently skipped over to keep suppressing further back.
    """
    store.append("ancient")
    store.append("a")
    store.append("an unrelated command typed in between")
    store.append("b")
    # "b" was queued most recently, so it pops first.
    controller = FakeController(pending=["a", "b"])
    queue_nav, history_nav = navigator_pair(controller)

    queue_nav.up("")  # recalls "b"
    queue_nav.up("b2")  # edit b -> b2, recalls "a"

    # "a" is recalled unedited; the queue is now exhausted.
    result = fallback_to_history(queue_nav, history_nav, "a")

    assert store.load() == [
        "ancient",
        "a",
        "an unrelated command typed in between",
        "b",
        "b2",
    ]
    assert result == "an unrelated command typed in between", (
        "the interleaved entry breaks contiguity and must surface, even "
        "though it means 'a' isn't suppressed in this exact walk -- never "
        "skip past unrelated history to keep hunting for queue echoes"
    )


def test_older_deliberate_duplicate_submission_is_not_deleted(store, navigator_pair):
    """A genuinely older, independent submission that happens to share text
    with a queued item must stay fully visible -- the bounded match may
    only ever consume exactly the entries this navigation produced.
    """
    store.append("start")
    store.append("a")  # deliberate, unrelated, earlier submission
    store.append("a")  # the queue's own captured-at-insertion original
    controller = FakeController(pending=["a"])
    queue_nav, history_nav = navigator_pair(controller)

    queue_nav.up("")  # recalls "a" (the queue's copy)
    result = fallback_to_history(queue_nav, history_nav, "a2")  # edit, then exhaust

    assert store.load() == ["start", "a", "a", "a2"]
    assert result == "a", (
        "the bounded suppression must stop after consuming exactly the "
        "fresh edit echo and the queue's own original, leaving the older "
        "deliberate duplicate fully intact and reachable"
    )

    older_still_reachable = history_nav.up(result)
    assert older_still_reachable == "start"


# =========================================================================
# Historical recall continues correctly after the queue hand-off
# =========================================================================


def test_history_recall_continues_past_the_suppressed_tail(store, navigator_pair):
    store.append("ancient")
    store.append("old")
    store.append("a")
    controller = FakeController(pending=["a"])
    queue_nav, history_nav = navigator_pair(controller)

    queue_nav.up("")
    first = fallback_to_history(queue_nav, history_nav, "a2")
    assert first == "old"

    second = history_nav.up("old")
    assert second == "ancient"


# =========================================================================
# Working-draft restoration: Down back out of the queue without exhausting
# =========================================================================


def test_down_restores_working_draft_unedited(store, navigator_pair):
    controller = FakeController(pending=["a"])
    queue_nav, _ = navigator_pair(controller)

    handled, text, _ = queue_nav.up("my in-progress draft")
    assert (handled, text) == (True, "a")

    handled, text = queue_nav.down("a")  # recall unedited
    assert (handled, text) == (True, "my in-progress draft")
    assert not queue_nav.active
    assert controller.restored_oldest_first[-1] == ["a"]


def test_down_restores_working_draft_and_persists_edit(store, navigator_pair):
    store.append("a")
    controller = FakeController(pending=["a"])
    queue_nav, _ = navigator_pair(controller)

    queue_nav.up("working draft")
    handled, text = queue_nav.down("a2")  # edited before backing out

    assert (handled, text) == (True, "working draft")
    assert store.load() == ["a", "a2"]
    assert controller.restored_oldest_first[-1] == ["a2"]
