"""Tests for ``code_puppy.plugins.prune.prune_menu.PruneMenu``.

Covers menu construction, selection toggling, lock invariants surfaced at
the UI layer, ``PruneSelection`` shape, and viewport scrolling math. Pure
state — no live TTY involved.
"""

from __future__ import annotations

import pytest

from code_puppy.plugins.prune.prune_menu import PruneMenu
from code_puppy.plugins.prune.prune_model import (
    ContextBudget,
    build_message_entries,
)

from ._helpers import (
    _assistant_text,
    _menu_with_history,
    _system_plus_user_msg,
    _user_msg,
)


# ───────────────────────────────────────────────────────────────────────────
# Init / row ordering
# ───────────────────────────────────────────────────────────────────────────


class TestPruneMenuInit:
    def test_rejects_empty_entries(self):
        with pytest.raises(ValueError):
            PruneMenu(entries=[])

    def test_pure_tool_returns_hidden_from_rows(self):
        menu, entries, _ = _menu_with_history()
        # Tool-return messages must not appear as their own rows; they
        # live underneath their parent assistant message's tool-call list.
        assert all(not entries[r.message_idx].is_pure_tool_return for r in menu.rows)

    def test_rows_are_ordered_newest_first(self):
        """The newest message must be at the top of the list (row 0) so
        the cursor lands on the most recent context first."""
        menu, entries, _ = _menu_with_history()
        # History indices should strictly decrease (newest → oldest)
        # because pure-tool-return entries are filtered out.
        history_idx_seq = [entries[r.message_idx].history_index for r in menu.rows]
        assert history_idx_seq == sorted(history_idx_seq, reverse=True)


# ───────────────────────────────────────────────────────────────────────────
# Selection toggling + lock invariants
# ───────────────────────────────────────────────────────────────────────────


class TestPruneMenuSelection:
    def test_toggle_message_adds_and_removes(self):
        menu, _, _ = _menu_with_history()
        menu.cursor = 0
        menu._toggle_current()
        assert menu.rows[0].message_idx in menu.selected_messages
        menu._toggle_current()
        assert menu.rows[0].message_idx not in menu.selected_messages

    def test_system_row_is_not_toggleable(self):
        """Pressing space on a system row must be a no-op so the user
        cannot accidentally select the agent's identity for removal.
        """
        history = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        budget = ContextBudget()
        menu = PruneMenu(entries=entries, budget=budget)
        # Find the system row's index and put cursor on it.
        sys_row_idx = next(
            i
            for i, r in enumerate(menu.rows)
            if menu.entries[r.message_idx].role == "system"
        )
        menu.cursor = sys_row_idx
        menu._toggle_current()
        # System message_idx must NOT appear in selected_messages.
        sys_msg_idx = menu.rows[sys_row_idx].message_idx
        assert sys_msg_idx not in menu.selected_messages

    def test_select_all_skips_system_rows(self):
        history = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries)
        menu._select_all()
        # Find system entry's msg_idx — it must be excluded.
        sys_msg_idx = next(i for i, e in enumerate(menu.entries) if e.role == "system")
        assert sys_msg_idx not in menu.selected_messages

    def test_history_index_0_pure_user_message_is_toggleable(self):
        """On non-Anthropic transports history[0] is a pure UserPromptPart
        (the system prompt is carried out-of-band). The user must be
        able to prune their first turn — previously this was locked by
        a blunt index-0 check.
        """
        history = [
            _user_msg("first user turn on a non-anthropic provider"),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries)
        idx0_row = next(
            i
            for i, r in enumerate(menu.rows)
            if menu.entries[r.message_idx].history_index == 0
        )
        menu.cursor = idx0_row
        menu._toggle_current()
        idx0_msg_idx = menu.rows[idx0_row].message_idx
        # New behavior: toggling the first user message DOES select it.
        assert idx0_msg_idx in menu.selected_messages
        # And select-all also picks it up.
        menu._clear_all()
        menu._select_all()
        assert idx0_msg_idx in menu.selected_messages

    def test_history_index_0_system_bundle_remains_non_toggleable(self):
        """Anthropic-style bundle (SystemPromptPart + UserPromptPart at
        history[0]) must still be locked. The lock now keys off content
        (role == "system") rather than position.
        """
        history = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries)
        bundle_row = next(
            i
            for i, r in enumerate(menu.rows)
            if menu.entries[r.message_idx].role == "system"
        )
        menu.cursor = bundle_row
        menu._toggle_current()
        bundle_msg_idx = menu.rows[bundle_row].message_idx
        assert bundle_msg_idx not in menu.selected_messages
        menu._select_all()
        assert bundle_msg_idx not in menu.selected_messages

    def test_clear_all(self):
        menu, _, _ = _menu_with_history()
        menu.selected_messages.add(0)
        menu._clear_all()
        assert menu.selected_messages == set()

    def test_row_is_checked_returns_bool(self):
        menu, _, _ = _menu_with_history()
        msg_row = menu.rows[0]
        assert menu._row_is_checked(msg_row) is False
        menu.selected_messages.add(msg_row.message_idx)
        assert menu._row_is_checked(msg_row) is True

    def test_selection_has_side_effects_via_message(self):
        menu, _, _ = _menu_with_history()
        # Both tool calls in our fixture are side-effecting (shell + write).
        # Selecting any assistant message should trip the flag.
        msg_row = next(r for r in menu.rows if menu.entries[r.message_idx].tool_calls)
        menu.selected_messages.add(msg_row.message_idx)
        assert menu._selection_has_side_effects() is True


# ───────────────────────────────────────────────────────────────────────────
# _build_selection — model layer the runner consumes
# ───────────────────────────────────────────────────────────────────────────


class TestPruneMenuBuildSelection:
    def test_maps_message_idx_to_history_index(self):
        menu, entries, _ = _menu_with_history()
        first_msg_row = menu.rows[0]
        menu.selected_messages.add(first_msg_row.message_idx)
        sel = menu._build_selection()
        assert (
            entries[first_msg_row.message_idx].history_index
            in sel.history_indices_to_drop
        )

    def test_selection_only_has_history_indices(self):
        """PruneSelection no longer carries ``tool_call_ids_to_drop`` —
        whole-message removal is the only path.
        """
        menu, _, _ = _menu_with_history()
        menu.selected_messages.add(menu.rows[0].message_idx)
        sel = menu._build_selection()
        assert hasattr(sel, "history_indices_to_drop")
        assert not hasattr(sel, "tool_call_ids_to_drop")


# ───────────────────────────────────────────────────────────────────────────
# Viewport scrolling math
# ───────────────────────────────────────────────────────────────────────────


class TestPruneMenuViewport:
    def test_scroll_into_view_clamps_top(self):
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 2
        menu.cursor = len(menu.rows) - 1
        menu._scroll_into_view()
        assert menu.viewport_top + menu._visible_rows >= menu.cursor + 1

    def test_scroll_into_view_jumps_up_when_cursor_above(self):
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 2
        menu.viewport_top = 3
        menu.cursor = 0
        menu._scroll_into_view()
        assert menu.viewport_top == 0
