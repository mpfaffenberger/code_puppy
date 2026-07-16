"""Hard newlines in the prompt PREFIX (the prompt_newline plugin contract).

The plugin appends a ``("", "\\n")`` fragment to the prompt chrome so
typed input starts on a fresh row. On the persistent bottom bar that
newline must survive two stages that otherwise sanitize it away:

* ``prompt_prefix_style.flatten_prompt_fragments`` keeps ``\\n`` (with an
  SGR slot for index alignment);
* ``bar_rendering._prompt_visual_rows`` renders leading prefix lines as
  chrome rows ABOVE the input line.
"""

from code_puppy.messaging.bar_rendering import (
    REVERSE_ON,
    count_prompt_rows,
    render_prompt_block,
)
from code_puppy.messaging.prompt_prefix_style import flatten_prompt_fragments


class TestFlattenKeepsNewlines:
    def test_trailing_newline_fragment_survives(self):
        plain, sgrs = flatten_prompt_fragments(
            [("ansimagenta", ">>> "), ("", "\n")], {}
        )
        assert plain == ">>> \n"
        assert len(sgrs) == len(plain)  # the newline owns an SGR slot

    def test_sgr_alignment_across_newline(self):
        plain, sgrs = flatten_prompt_fragments(
            [("ansimagenta", "chrome\n"), ("ansicyan", "tail")], {}
        )
        assert plain == "chrome\ntail"
        assert sgrs[0] == "35"  # chrome chars styled
        assert sgrs[plain.index("tail")] == "36"  # tail still index-aligned

    def test_other_control_chars_still_stripped(self):
        # sanitize() strips control BYTES (ESC, tabs, C1...) — the
        # newline is the one control char flatten deliberately keeps.
        plain, _ = flatten_prompt_fragments([("", "a\x1b\tb\x85\n")], {})
        assert plain == "ab\n"


class TestPrefixNewlineRows:
    def test_newline_prefix_yields_chrome_plus_input_rows(self):
        assert count_prompt_rows(">>> \n", "", 0, 80) == 2

    def test_single_line_prefix_unchanged(self):
        assert count_prompt_rows(">>> ", "hello", 5, 80) == 1

    def test_cursor_paints_on_input_row(self):
        rows, cursor_row = render_prompt_block(">>> \n", "hi", 2, 80, 6)
        assert rows[0] == ">>> "  # chrome row: no pseudo-cursor
        assert REVERSE_ON not in rows[0]
        assert REVERSE_ON in rows[1]  # cursor lives on the input row
        assert cursor_row == 1

    def test_chrome_row_keeps_prefix_styling(self):
        # ">>" styled, "\n" slot, buffer unstyled.
        sgrs = ["35", "35", ""]
        rows, _ = render_prompt_block(">>\n", "x", 1, 80, 6, prefix_sgrs=sgrs)
        assert "\x1b[35m" in rows[0]
        assert "\x1b[35m" not in rows[1]

    def test_long_chrome_line_soft_wraps(self):
        # 10-cell chrome in a 4-cell terminal: 3 chrome rows + input row.
        assert count_prompt_rows("0123456789\n", "", 0, 4) == 4

    def test_buffer_newlines_still_work_below_chrome(self):
        rows, cursor_row = render_prompt_block("c\n", "ab\ncd", 5, 80, 6)
        assert len(rows) == 3  # chrome + two buffer lines
        assert rows[0] == "c"
        assert rows[1] == "ab"
        assert rows[2].startswith("cd")  # pseudo-cursor appended after 'cd'
        assert REVERSE_ON in rows[2]
        assert cursor_row == 2  # cursor at end of second buffer line
