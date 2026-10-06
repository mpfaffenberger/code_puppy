"""Virtual-terminal coverage for the third pinned statistics row."""

from io import StringIO

import pytest
from rich.cells import cell_len
from rich.text import Text

from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.inline_bar import InlineBottomBar
from tests.messaging.test_bottom_bar_screen import VTScreen, VTStream


class TerminalOutput(StringIO):
    def __init__(self, screen):
        super().__init__()
        self.emulator = VTStream(screen)

    def isatty(self):
        return True

    def write(self, text):
        self.emulator.feed(text)
        return super().write(text)


@pytest.fixture
def terminal():
    size = [120, 24]
    screen = VTScreen(*size)
    output = TerminalOutput(screen)
    bar = BottomBar(stream=output, get_size=lambda: tuple(size))
    bar.start()
    bar.set_prompt_text("[model] code-puppy >>> ", "", 0)
    bar.set_status("Context 100/1000 | Idle")
    try:
        yield bar, screen, output, size
    finally:
        bar.stop()


def test_row_sits_immediately_above_identity_and_context(terminal):
    bar, screen, output, _ = terminal
    original = bar._reserved
    bar.set_speculation_status("Spec | hits 2 | misses 1 | wasted 0")
    assert bar._reserved == original + 1
    assert screen.display[-3].strip() == "Spec | hits 2 | misses 1 | wasted 0"
    assert screen.display[-2].strip() == "[model] code-puppy"
    assert screen.display[-1].strip() == "Context 100/1000 | Idle"
    assert screen.display[-4].startswith(">>>")
    with bar.output_transaction():
        output.write("response text\r\n")
    assert screen.display[-3].startswith("Spec | hits 2")
    assert any("response text" in row for row in screen.display[:-4])
    assert screen.margins.bottom == 24 - bar._reserved - 1


def test_styled_text_row_keeps_program_styles_and_drops_smuggled_escapes(terminal):
    bar, screen, output, _ = terminal
    row = Text()
    row.append("spec", style="bold bright_blue")
    row.append("  ")
    row.append("3 hits", style="bold bright_green")
    row.append("\x1b[31mEVIL", style="bright_black")
    before = len(output.getvalue())
    bar.set_speculation_status(row)
    painted = output.getvalue()[before:]
    assert screen.display[-3].strip() == "spec  3 hits[31mEVIL"
    assert "\x1b[1;92m" in painted or "\x1b[1m\x1b[92m" in painted or "92m" in painted
    assert "\x1b[31m" not in painted
    # Same content again is a no-op; a plain string still paints dim.
    bar.set_speculation_status(row.copy())
    assert output.getvalue()[before:] == painted
    bar.set_speculation_status("plain fallback")
    assert screen.display[-3].strip() == "plain fallback"
    assert "\x1b[2mplain fallback" in output.getvalue()


def test_hiding_row_restores_two_bottom_rows_without_ghosts(terminal):
    bar, screen, _, _ = terminal
    original = bar._reserved
    bar.set_speculation_status("UNIQUE_STATS")
    bar.set_speculation_status(None)
    assert bar._reserved == original
    assert not any("UNIQUE_STATS" in row for row in screen.display)
    assert screen.display[-2].strip() == "[model] code-puppy"
    assert screen.display[-1].strip() == "Context 100/1000 | Idle"


def test_unchanged_stats_do_not_repaint_per_stream_delta(terminal):
    bar, _, output, _ = terminal
    bar.set_speculation_status("hits 1")
    before = output.getvalue()
    for _ in range(50):
        bar.set_speculation_status("hits 1")
    assert output.getvalue() == before


def test_resize_and_popup_keep_stats_in_place(terminal):
    bar, screen, _, size = terminal
    bar.set_speculation_status("Spec stats")
    size[:] = [90, 10]
    screen.resize(lines=10, columns=90)
    bar.set_popup_lines(["choice"] * 12)
    assert bar._region_up
    assert bar._reserved < 10
    assert screen.display[-3].strip() == "Spec stats"
    assert screen.display[-2].strip() == "[model] code-puppy"
    assert screen.display[-1].strip() == "Context 100/1000 | Idle"
    assert sum("Spec stats" in row for row in screen.display) == 1


def test_suspend_resume_and_stop_clear_stats(terminal):
    bar, screen, _, _ = terminal
    bar.set_speculation_status("UNIQUE_STATS")
    with bar.suspended():
        assert not any("UNIQUE_STATS" in row for row in screen.display)
    assert screen.display[-3].strip() == "UNIQUE_STATS"
    bar.stop()
    assert not any("UNIQUE_STATS" in row for row in screen.display)


@pytest.mark.parametrize("bar_type", [BottomBar, InlineBottomBar])
def test_wide_text_is_clipped_and_controls_are_stripped(bar_type):
    bar = bar_type(stream=StringIO(), get_size=lambda: (30, 24))
    bar.set_speculation_status("hits\x1b[31m 1\n" + "界" * 40)
    text = Text.from_ansi(bar._render_speculation_line(30)).plain
    assert cell_len(text) <= 30
    assert "\n" not in text
    assert "\x1b" not in text


def test_inline_fallback_places_stats_before_identity():
    bar = InlineBottomBar(stream=StringIO(), get_size=lambda: (120, 24))
    bar._cols, bar._rows = 120, 24
    bar.set_prompt_text("[model] code-puppy >>> ", "", 0)
    bar.set_status("Context | Idle")
    bar.set_speculation_status("Spec stats")
    lines = [Text.from_ansi(line).plain for line in bar._inline_lines()]
    assert lines[-3:] == ["Spec stats", "[model] code-puppy", "Context | Idle"]
    bar.set_speculation_status(None)
    assert len(bar._inline_lines()) == len(lines) - 1
