"""Resize ghost-clearing: re-establish erases the OLD reserved band.

Without the erase, the bar rows painted at the previous geometry linger
as duplicates ("multiples of UI elements appear where they were and now
where they are") after a terminal resize.
"""

import io

import pytest

from code_puppy.messaging.bar_rendering import CLEAR_LINE, RESET_REGION
from code_puppy.messaging.bottom_bar import BottomBar


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class MutableSize:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows

    def __call__(self):
        return (self.cols, self.rows)


def drain(stream):
    value = stream.getvalue()
    stream.truncate(0)
    stream.seek(0)
    return value


def _bar(rows=24):
    tty = FakeTTY()
    size = MutableSize(80, rows)
    bar = BottomBar(stream=tty, get_size=size)
    return bar, tty, size


def test_fresh_start_has_no_ghost_clear():
    bar, tty, _ = _bar()
    bar.start()
    # First establish: nothing painted before -> no reset-region erase pass.
    assert RESET_REGION not in drain(tty)


def test_grow_clears_old_reserved_band():
    bar, tty, size = _bar(rows=24)
    bar.start()
    old_reserved = bar._reserved
    assert old_reserved > 0
    drain(tty)

    size.rows = 40  # terminal got taller
    bar.set_prompt_text("> ", "hi", 2)  # any repaint re-polls geometry
    out = drain(tty)

    assert RESET_REGION in out
    # Every row of the OLD band (bottom of the 24-row screen) is erased.
    for row in range(24 - old_reserved + 1, 25):
        assert f"\x1b[{row};1H{CLEAR_LINE}" in out
    # And the new region is established at the new height.
    assert f"\x1b[1;{40 - bar._reserved}r" in out


def test_shrink_reestablishes_without_out_of_bounds_clears():
    bar, tty, size = _bar(rows=40)
    bar.start()
    old_reserved = bar._reserved
    drain(tty)

    size.rows = 24  # terminal got shorter
    bar.set_prompt_text("> ", "hi", 2)
    out = drain(tty)

    # Old band rows (37..40) are off-screen now — no erase beyond row 24.
    for row in range(40 - old_reserved + 1, 41):
        assert f"\x1b[{row};1H{CLEAR_LINE}" not in out
    assert f"\x1b[1;{24 - bar._reserved}r" in out


@pytest.mark.parametrize("guard_scroll_fix", [False, True])
def test_width_only_resize_repaints_in_place(guard_scroll_fix):
    bar, tty, size = _bar(rows=24)
    bar._guard_scroll_fix = guard_scroll_fix
    bar.start()
    old_reserved = bar._reserved
    drain(tty)

    size.cols = 120  # width change only
    bar.set_prompt_text("> ", "hi", 2)
    out = drain(tty)

    # Same rows: repaint clears the existing band without allocating it
    # again. In particular, horizontal resizing must not emit scrolling LFs.
    assert "\n" not in out
    assert RESET_REGION not in out
    for row in range(24 - old_reserved + 1, 25):
        assert f"\x1b[{row};1H{CLEAR_LINE}" in out


def test_repeated_narrowing_does_not_scroll_footer_into_transcript():
    from tests.messaging.test_bottom_bar_screen import Tap, VTScreen, VTStream

    screen = VTScreen(120, 24)
    terminal = VTStream(screen)
    size = MutableSize(120, 24)
    bar = BottomBar(stream=Tap(terminal.feed), get_size=size)
    bar.start()
    try:
        bar.set_status("Idle")
        bar.set_prompt_text("Boodler [agent] [model] (~/project) >>> ", "", 0)
        with bar.output_transaction():
            terminal.feed("KEEP THIS TRANSCRIPT\r\n")
        before = screen.display.index(
            next(row for row in screen.display if "KEEP THIS TRANSCRIPT" in row)
        )
        for width in (100, 80, 60, 40, 30, 50, 90, 120):
            screen.resize(columns=width)
            size.cols = width
            bar.set_status("Idle")
            assert "KEEP THIS TRANSCRIPT" in screen.display[before]
            assert sum("Boodler" in row for row in screen.display) == 1
            assert "Boodler" in screen.display[-2]
            assert "Idle" in screen.display[-1]
    finally:
        bar.stop()


def test_no_resize_no_reestablish():
    bar, tty, _ = _bar()
    bar.start()
    drain(tty)
    bar.set_prompt_text("> ", "hi", 2)
    # Stable geometry: plain repaint, no region reset.
    assert RESET_REGION not in drain(tty)
