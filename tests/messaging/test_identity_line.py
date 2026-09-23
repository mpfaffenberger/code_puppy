"""Metadata belongs immediately above status, not in the editable prompt."""

import io

import pytest
from rich.cells import cell_len
from rich.text import Text

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
