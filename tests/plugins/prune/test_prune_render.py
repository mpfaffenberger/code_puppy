"""Tests for ``code_puppy.plugins.prune.prune_render``.

Covers small formatting helpers (``ctx_indicator``, ``tokens_str``,
``format_args_full``), the budget footer line, the legend, and full
list/detail render smoke tests over a representative menu.
"""

from __future__ import annotations

from code_puppy.plugins.prune import prune_model
from code_puppy.plugins.prune.prune_menu import PruneMenu
from code_puppy.plugins.prune.prune_model import (
    ContextBudget,
    MessageEntry,
    build_message_entries,
)
from code_puppy.plugins.prune.prune_render import (
    ctx_detail_text,
    ctx_indicator,
    format_args_full,
    render_budget_line,
    render_detail,
    render_legend,
    render_list,
    tokens_str,
)

from ._helpers import (
    _assistant_with_thinking,
    _menu_with_history,
    _user_msg,
)


def _flatten(formatted) -> str:
    """Collapse a prompt_toolkit-style [(style, text), ...] list to a string."""
    return "".join(text for _style, text in formatted)


# ───────────────────────────────────────────────────────────────────────────
# Small formatting helpers
# ───────────────────────────────────────────────────────────────────────────


class TestCtxIndicator:
    def test_in_context(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=True
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "●"

    def test_out_of_context(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=False
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "○"

    def test_unknown(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=None
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "·"


class TestTokensStr:
    def test_none(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", tokens=None
        )
        assert tokens_str(e) == ""

    def test_value(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", tokens=42
        )
        assert tokens_str(e) == "~42t"


class TestFormatArgsFull:
    def test_empty_uses_fallback(self):
        assert format_args_full({}, "fb") == ["fb"]
        assert format_args_full({}, "") == ["<no args>"]

    def test_non_dict_falls_back(self):
        assert format_args_full([1, 2, 3], "fb") == ["fb"]  # type: ignore[arg-type]

    def test_inline_scalars(self):
        out = format_args_full({"a": 1, "b": "short"}, "")
        assert out == ["a: 1", "b: short"]

    def test_multiline_string_block_scalar(self):
        out = format_args_full({"code": "line1\nline2"}, "")
        assert out[0] == "code: |"
        assert "line1" in out[1]
        assert "line2" in out[2]

    def test_nested_dict_recurses(self):
        out = format_args_full({"outer": {"inner": "val"}}, "")
        assert out[0] == "outer:"
        # Nested key indented under the parent
        assert any("inner: val" in line for line in out[1:])

    def test_list_renders_with_dash(self):
        out = format_args_full({"items": [1, 2, 3]}, "")
        assert out[0] == "items:"
        assert any(line.lstrip().startswith("- 1") for line in out[1:])


# ───────────────────────────────────────────────────────────────────────────
# Budget footer line
# ───────────────────────────────────────────────────────────────────────────


class TestRenderBudgetLine:
    def test_unavailable(self):
        b = ContextBudget(available=False)
        out = render_budget_line(b)
        assert "unavailable" in out[0][1]

    def test_green_under_70(self):
        b = ContextBudget(
            used_tokens=10, overhead_tokens=10, context_length=100, available=True
        )  # 20% used
        out = render_budget_line(b)
        # Style is "fg:ansigreen" (matches C_FOOTER_OK)
        assert out[0][0] == prune_model.C_FOOTER_OK

    def test_yellow_70_to_90(self):
        b = ContextBudget(
            used_tokens=40, overhead_tokens=40, context_length=100, available=True
        )  # 80%
        out = render_budget_line(b)
        assert out[0][0] == prune_model.C_FOOTER_WARN

    def test_red_over_90(self):
        b = ContextBudget(
            used_tokens=50, overhead_tokens=45, context_length=100, available=True
        )  # 95%
        out = render_budget_line(b)
        assert out[0][0] == prune_model.C_SHELL

    def test_shows_overflow_when_messages_dont_fit(self):
        b = ContextBudget(
            used_tokens=70,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=500,
            out_of_context_messages=3,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        assert "out of context" in flat
        assert "500" in flat
        assert "3 older" in flat
        # Must not imply messages are destroyed.
        assert "dropped" not in flat.lower()
        assert "removed" not in flat.lower()

    def test_overflow_is_on_its_own_line(self):
        """Long overflow line shouldn't crowd the main context counter."""
        b = ContextBudget(
            used_tokens=70,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=12345,
            out_of_context_messages=9,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        # Two newlines total: one after the main line, one after overflow.
        assert flat.count("\n") == 2
        # The overflow segment must come AFTER a newline (own line).
        main_line, _, rest = flat.partition("\n")
        assert "older msg" not in main_line
        assert "older msg" in rest

    def test_hides_overflow_when_everything_fits(self):
        b = ContextBudget(
            used_tokens=30,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=0,
            out_of_context_messages=0,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        assert "overflow" not in flat


# ───────────────────────────────────────────────────────────────────────────
# Legend
# ───────────────────────────────────────────────────────────────────────────


class TestRenderLegend:
    def test_legend_lists_all_three_glyphs(self):
        flat = "".join(text for _style, text in render_legend())
        assert "●" in flat
        assert "○" in flat
        assert "·" in flat
        assert "in context" in flat
        assert "out of context" in flat

    def test_legend_does_not_falsely_imply_overflow_is_prunable_or_gone(self):
        """Pruning ○ messages doesn't free up budget — they're already
        being skipped by the model. Conversely, they're NOT destroyed:
        if newer messages get pruned, older ○ ones slide back in. The
        legend must convey neither false implication.
        """
        flat = "".join(text for _style, text in render_legend()).lower()
        assert "drop candidate" not in flat
        assert "dropped" not in flat
        assert "removed" not in flat
        assert "gone" not in flat

    def test_legend_uses_in_context_color_for_filled_dot(self):
        out = render_legend()
        green_segments = [seg for seg in out if "●" in seg[1]]
        assert green_segments, "Expected a segment containing the green dot"
        assert green_segments[0][0] == prune_model.C_FOOTER_OK


# ───────────────────────────────────────────────────────────────────────────
# render_list smoke
# ───────────────────────────────────────────────────────────────────────────


class TestRenderListSmoke:
    def test_renders_title_and_rows(self):
        menu, _entries, _ = _menu_with_history()
        out = render_list(menu)
        flat = _flatten(out)
        assert "prune" in flat
        # Each visible message row prefixes its history index.
        assert "user" in flat or "asst" in flat

    def test_renders_legend_under_budget(self):
        menu, _, _ = _menu_with_history()
        flat = _flatten(render_list(menu))
        assert "legend:" in flat
        assert "in context" in flat

    def test_renders_with_selection(self):
        menu, _, _ = _menu_with_history()
        menu.selected_messages.add(menu.rows[0].message_idx)
        flat = _flatten(render_list(menu))
        # Footer should reflect the selection count.
        assert "1 message" in flat

    def test_renders_when_viewport_clipped(self):
        """Force hidden-above/below indicators to appear."""
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 1
        menu.cursor = len(menu.rows) - 1
        menu._scroll_into_view()
        flat = _flatten(render_list(menu))
        assert "more above" in flat


# ───────────────────────────────────────────────────────────────────────────
# render_detail smoke
# ───────────────────────────────────────────────────────────────────────────


class TestRenderDetailSmoke:
    def test_message_detail(self):
        menu, _, _ = _menu_with_history()
        menu.cursor = 0
        flat = _flatten(render_detail(menu))
        assert "message" in flat
        assert "history index" in flat

    def test_message_detail_lists_tool_calls_inline(self):
        """Tool calls live inside the message detail pane now — they
        aren't separately selectable rows anymore.
        """
        menu, _, _ = _menu_with_history()
        menu.cursor = next(
            i for i, r in enumerate(menu.rows) if menu.entries[r.message_idx].tool_calls
        )
        flat = _flatten(render_detail(menu))
        assert "tool calls" in flat
        assert "will go with message" in flat

    def test_message_detail_surfaces_thinking_block_count(self):
        """When an assistant turn carried thinking content, the metadata
        line should call it out so the user can find it in full_text.
        """
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="answer", thinking="reasoning here"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries)
        # Put cursor on the assistant row.
        menu.cursor = next(
            i
            for i, r in enumerate(menu.rows)
            if menu.entries[r.message_idx].role == "assistant"
        )
        flat = _flatten(render_detail(menu))
        assert "thinking block" in flat
        # And the full text section must include the fenced reasoning.
        assert "reasoning here" in flat

    def test_side_effect_warning_when_selected(self):
        menu, _, _ = _menu_with_history()
        # Select an assistant message containing a side-effecting tool call.
        for r in menu.rows:
            if menu.entries[r.message_idx].tool_calls:
                menu.selected_messages.add(r.message_idx)
                menu.cursor = next(i for i, rr in enumerate(menu.rows) if rr is r)
                break
        flat = _flatten(render_detail(menu))
        assert "side-effecting" in flat

    def test_ctx_detail_text_branches(self):
        e_in = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=True
        )
        e_out = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=False
        )
        e_unknown = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=None
        )
        assert "in context" in ctx_detail_text(e_in)
        assert "out of context" in ctx_detail_text(e_out)
        # Out-of-context wording must not imply messages are gone.
        out_lower = ctx_detail_text(e_out).lower()
        assert "dropped" not in out_lower
        assert "removed" not in out_lower
        assert ctx_detail_text(e_unknown) == ""
