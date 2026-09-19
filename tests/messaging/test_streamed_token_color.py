"""Only the streamed number uses the theme's agent accent."""

import pytest
from rich.console import Console
from rich.text import Text

from code_puppy.messaging.status_line import render_status_line


@pytest.mark.parametrize("suffix", ["", " (1 queued)"])
@pytest.mark.parametrize("activity", ["Working", "Calling grep"])
def test_only_streamed_digits_and_commas_are_accented(suffix, activity):
    body = f"120/500 tokens | Streamed ~3,209 tokens | {activity}"
    text = Text.from_ansi(render_status_line(body, suffix, 120))
    console = Console()
    start = text.plain.index("3,209")
    for offset in range(start, start + 5):
        style = text.get_style_at_offset(console, offset)
        assert style.color.number == 4
        assert not style.dim
    for marker in ("120", "Streamed", "~", " tokens |"):
        style = text.get_style_at_offset(console, text.plain.index(marker))
        assert style.dim
        assert style.color is None or style.color.is_default
    assert text.plain == body + suffix


@pytest.mark.parametrize("width", [1, 20, 25, 30, 40])
def test_coloring_does_not_change_clipping(width):
    text = Text.from_ansi(
        render_status_line("Streamed ~1,234 tokens | Working", "", width)
    )
    assert text.cell_len <= width
