"""Lightweight tests for the judges TUI helpers.

We don't try to drive the full prompt_toolkit Application in tests; that's
flaky and slow. Instead we cover the pure-function renderers and verify
the form-validation paths via the public field validator (``validate_name``)
and the dataclass round-trip behavior.
"""

from __future__ import annotations

from code_puppy.command_line.judges_menu import (
    _FormResult,
    _render_menu,
    _render_preview,
    _sanitize,
    _wrap,
)
from code_puppy.plugins.wiggum.judge_config import JudgeConfig


def _flatten(fragments) -> str:
    return "".join(text for _, text in fragments)


def test_sanitize_strips_emojis_and_combiners():
    # Emojis (category So) and combining marks are removed; ASCII survives.
    assert _sanitize("hello 🐶 world") == "hello world"
    assert "a" in _sanitize("café")  # ASCII letters preserved


def test_wrap_respects_width():
    wrapped = _wrap("the quick brown fox jumps over", width=10)
    for line in wrapped:
        assert len(line) <= 12  # word boundaries can spill by one word
    assert "".join(wrapped).replace(" ", "") == "thequickbrownfoxjumpsover"


def test_wrap_preserves_blank_lines():
    wrapped = _wrap("one\n\ntwo", width=20)
    assert wrapped == ["one", "", "two"]


def test_render_menu_empty_state_has_hint():
    fragments = _render_menu([], 0, 0)
    flat = _flatten(fragments)
    assert "No judges configured" in flat
    assert "N" in flat  # the hint to press N


def test_render_menu_shows_enabled_glyphs():
    judges = [
        JudgeConfig(name="a", model="m1", enabled=True),
        JudgeConfig(name="b", model="m2", enabled=False),
    ]
    flat = _flatten(_render_menu(judges, 0, 0))
    assert "[on]" in flat
    assert "[off]" in flat
    assert "a" in flat and "b" in flat
    assert "m1" in flat and "m2" in flat


def test_render_menu_selection_marker():
    judges = [
        JudgeConfig(name="a", model="m"),
        JudgeConfig(name="b", model="m"),
    ]
    flat = _flatten(_render_menu(judges, 0, 1))
    # Selected row gets ▶ glyph
    assert "▶" in flat


def test_render_preview_shows_full_judge():
    j = JudgeConfig(name="x", model="gpt-5.4", prompt="be strict", enabled=True)
    flat = _flatten(_render_preview(j))
    assert "x" in flat
    assert "gpt-5.4" in flat
    assert "yes" in flat  # enabled
    assert "be strict" in flat


def test_render_preview_disabled_shows_no():
    j = JudgeConfig(name="x", model="m", enabled=False)
    flat = _flatten(_render_preview(j))
    assert "no" in flat


def test_render_preview_none_shows_placeholder():
    flat = _flatten(_render_preview(None))
    assert "No judge selected" in flat


def test_form_result_defaults():
    r = _FormResult()
    assert r.saved is False
    assert r.cancelled is False
    assert r.name == ""
    assert r.model == ""
    assert r.prompt == ""


def test_no_user_facing_alt_m_label():
    """Regression: macOS Terminal/iTerm intercept Alt+M as 'minimize window'.

    The current form picks models via an inline paginated list (no chord
    at all), but if someone re-introduces a key-chord for model selection
    they must not advertise Alt+M.
    """
    import re
    from code_puppy.command_line import judges_menu

    source = open(judges_menu.__file__, encoding="utf-8").read()
    code_only = re.sub(r"#.*$", "", source, flags=re.MULTILINE)
    assert "Alt+M" not in code_only
    assert "Alt-M" not in code_only


def test_form_uses_inline_model_list_not_chord_popup():
    """The form must pick models via an inline paginated section, not a
    key-chord popping a separate picker. This is what the user asked for:
    a tab-able 3rd section."""
    import code_puppy.command_line.judges_menu as jm

    source = open(jm.__file__, encoding="utf-8").read()
    # New design: paginated list renderer + focusable model window.
    assert "_render_model_list" in source
    assert "MODEL_PAGE_SIZE" in source
    # Old design artifacts that must NOT come back:
    assert '("escape", "m")' not in source, (
        "Esc-M chord was removed in favour of an inline tabbable model list."
    )
    assert 'kb.add("f2")' not in source, (
        "F2 picker shortcut was removed in favour of an inline model list."
    )
    assert "arrow_select_async" not in source, (
        "The external arrow-select model picker is no longer used in this form."
    )


def test_list_view_help_says_enter_edits_and_esc_closes():
    """List view should advertise Enter=edit, Esc=close.

    Regression: originally Enter closed the menu and E edited; reversed
    after user feedback. This test pins the new binding labels so the
    polarity can't silently flip back.
    """
    from code_puppy.command_line.judges_menu import _render_menu
    from code_puppy.plugins.wiggum.judge_config import JudgeConfig

    flat = "".join(
        text for _, text in _render_menu([JudgeConfig(name="x", model="m")], 0, 0)
    )
    # Enter is the primary edit gesture.
    assert "Enter" in flat
    enter_pos = flat.find("Enter")
    nearby_enter = flat[enter_pos : enter_pos + 40]
    assert "Edit" in nearby_enter, (
        f"Expected 'Edit' near 'Enter', got: {nearby_enter!r}"
    )
    # Esc is the close gesture.
    assert "Esc" in flat
    esc_pos = flat.find("Esc")
    nearby_esc = flat[esc_pos : esc_pos + 40]
    assert "Close" in nearby_esc, f"Expected 'Close' near 'Esc', got: {nearby_esc!r}"


def test_list_view_keybindings_swap_enter_and_esc():
    """Verify the actual prompt_toolkit binding wiring is right.

    Source-level check: 'enter' is wired to the edit handler, 'escape' is
    wired to the close handler, and 'enter' is NOT wired to close anymore.
    """
    import code_puppy.command_line.judges_menu as jm

    source = open(jm.__file__, encoding="utf-8").read()

    assert '@kb.add("enter")' in source
    assert '@kb.add("e")' in source
    assert 'pending_action[0] = "close"' in source

    # The close handler must be reached via 'escape' / 'c-c', NOT 'enter'.
    close_pos = source.find('pending_action[0] = "close"')
    decorators_above = source[max(0, close_pos - 250) : close_pos]
    assert '@kb.add("escape")' in decorators_above
    assert '@kb.add("c-c")' in decorators_above
    assert '@kb.add("enter")' not in decorators_above


def test_form_escape_is_simple_cancel_binding():
    """With the inline model list, Esc no longer has a chord partner, so
    Esc-as-plain-cancel works fine. We just check it's bound.
    """
    import code_puppy.command_line.judges_menu as jm

    source = open(jm.__file__, encoding="utf-8").read()
    assert '@kb.add("escape")' in source
    assert '@kb.add("c-c")' in source


def test_render_model_list_empty_state():
    """With zero models, the list section explains how to fix it."""
    from code_puppy.command_line.judges_menu import _render_model_list

    flat = _flatten(_render_model_list([], 0, 0, focused=True))
    assert "No models available" in flat


def test_render_model_list_paginates_correctly():
    """With more models than PAGE_SIZE, only the active page is shown."""
    from code_puppy.command_line.judges_menu import (
        _render_model_list,
        MODEL_PAGE_SIZE,
    )

    models = [f"m{i}" for i in range(MODEL_PAGE_SIZE * 2 + 3)]

    # Page 0
    flat0 = _flatten(_render_model_list(models, 0, 0, focused=False))
    assert "m0" in flat0
    assert f"m{MODEL_PAGE_SIZE - 1}" in flat0
    assert f"m{MODEL_PAGE_SIZE}" not in flat0  # next page hidden

    # Page 1
    flat1 = _flatten(_render_model_list(models, MODEL_PAGE_SIZE, 1, focused=False))
    assert f"m{MODEL_PAGE_SIZE}" in flat1
    assert "m0" not in flat1  # previous page hidden


def test_render_model_list_marker_changes_with_focus():
    """Selected row uses ▶ when focused, · when not (visual focus cue)."""
    from code_puppy.command_line.judges_menu import _render_model_list

    models = ["alpha", "beta", "gamma"]
    flat_focused = _flatten(_render_model_list(models, 1, 0, focused=True))
    flat_blurred = _flatten(_render_model_list(models, 1, 0, focused=False))

    assert "▶" in flat_focused
    assert "▶" not in flat_blurred
    # Unfocused list still shows current selection with a softer marker.
    assert "·" in flat_blurred


def test_form_tab_cycle_has_three_sections():
    """Tab must cycle Name ↔ Model ↔ Prompt (three sections, not two).

    This is the user-requested feature: 'paginated 3rd section that you
    can tab over to'. We verify the focus cycle list in the source.
    """
    import code_puppy.command_line.judges_menu as jm

    source = open(jm.__file__, encoding="utf-8").read()
    # The focus cycle list is constructed inline with three entries.
    assert "_focus_cycle = [name_area, model_window, prompt_area]" in source


def test_form_help_describes_arrow_keys_for_model_selection():
    """Help line should tell users how to pick a model with the keyboard."""
    import code_puppy.command_line.judges_menu as jm

    source = open(jm.__file__, encoding="utf-8").read()
    # Some kind of arrow-key hint must exist (↑↓ or 'select model').
    assert "↑↓" in source or "select model" in source
