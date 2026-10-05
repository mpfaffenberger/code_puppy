"""Metadata belongs immediately above status, not in the editable prompt."""

import io

import pytest
from rich.cells import cell_len
from rich.text import Text

from code_puppy.messaging.bar_rendering import elide_middle
from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.identity_line import split_identity
from code_puppy.messaging.inline_bar import InlineBottomBar
from tests.messaging.test_bottom_bar_screen import Term


@pytest.mark.parametrize("suffix", [">>> ", ">>> \n"])
def test_split_keeps_highlights_and_neutral_punctuation(suffix):
    prefix = "Boodler [agent] [model] (~) " + suffix
    prompt, colors, identity, highlights = split_identity(prefix, ["96"] * len(prefix))
    assert prompt == ">>> "
    assert identity == "Boodler [agent] [model] (~)"
    assert highlights[0] == "96"
    assert highlights[8] == "90"


def test_custom_prompt_unchanged():
    assert split_identity("custom> ", []) == ("custom> ", [], "", [])


def test_vt_identity_above_status_and_below_input():
    term = Term()
    bar = term.bar
    bar.start()
    try:
        bar.set_status("Idle")
        bar.set_prompt_text("Boodler [agent] [model] (~) >>> ", "hello", 5)
        rows = term.rows()
        assert rows[22].startswith(">>> hello")
        assert rows[23] == "Boodler [agent] [model] (~)"
        assert "Idle" in rows[24]
        bar.set_prompt_text("Boodler [other] [model] (~) >>> ", "", 0)
        assert "other" in term.rows()[23]
        bar.set_prompt_text(">>> ", "", 0)
        assert not any("Boodler" in row for row in term.rows().values())
    finally:
        bar.stop()


def test_inline_identity_above_status():
    bar = InlineBottomBar(stream=io.StringIO(), get_size=lambda: (80, 24))
    bar._ensure_inline_geometry()
    bar.set_status("Idle")
    bar.set_prompt_text("Boodler [agent] [model] (~) >>> ", "hello", 5)
    rows = [Text.from_ansi(row).plain for row in bar._inline_lines()]
    assert rows[0].startswith(">>> hello")
    assert rows[-2] == "Boodler [agent] [model] (~)"
    assert "Idle" in rows[-1]


def test_identity_clipped_to_one_row():
    bar = BottomBar(stream=io.StringIO(), get_size=lambda: (20, 24))
    bar.set_prompt_text("Boodler [agent] [very-long-model] (~) >>> ", "", 0)
    assert cell_len(Text.from_ansi(bar._render_identity_line(20)).plain) <= 20
    assert bar._identity_row_count() == 1
    assert bar._prompt_row_count() == 1


def test_narrow_identity_elides_middle_and_keeps_both_ends():
    """A head chop hides the cwd, the half of the row people scan for."""
    bar = BottomBar(stream=io.StringIO(), get_size=lambda: (28, 24))
    prefix = "Boodler [agent] [very-long-model-name] (~/code/puppy) >>> "
    bar.set_prompt_text(prefix, "", 0)
    row = Text.from_ansi(bar._render_identity_line(28)).plain
    assert cell_len(row) <= 28
    assert "\u2026" in row
    assert row.startswith("Boodler")
    assert row.endswith("(~/code/puppy)")


def test_wide_identity_elision_never_splits_a_wide_glyph():
    bar = BottomBar(stream=io.StringIO(), get_size=lambda: (11, 24))
    bar.set_prompt_text("\u754c\u754c [agent] [model] (~/code) >>> ", "", 0)
    row = Text.from_ansi(bar._render_identity_line(11)).plain
    assert cell_len(row) <= 11


@pytest.mark.parametrize("width", [0, 1, 2, 3])
def test_elide_middle_degenerate_widths_stay_in_budget(width):
    elided, keep = elide_middle("Boodler [agent] (~/code)", width)
    assert cell_len(elided) <= width
    assert len(keep) == len(elided)


def test_elide_middle_is_identity_when_it_fits():
    text = "Boodler (~/code)"
    assert elide_middle(text, 40) == (text, list(range(len(text))))
