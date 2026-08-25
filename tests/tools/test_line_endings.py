"""Unit tests for ``code_puppy.tools.line_endings.split_lines``.

Round-1 through round-6 review of the Phase 3 Anthropic editor adapter
exercised ``split_lines`` only indirectly (via the ``view``/``insert``
commands). This file gives it direct coverage: it is a small, brand-new
shared helper that ``view`` and ``insert`` both depend on to agree about
line numbers (see the module docstring), so a regression here silently
breaks native-editor line addressing for both commands at once.
"""

from code_puppy.tools.line_endings import split_lines


def test_empty_string_returns_no_lines():
    assert split_lines("") == []
    assert split_lines("", keepends=True) == []


def test_no_terminator_returns_single_line():
    assert split_lines("hello world") == ["hello world"]
    assert split_lines("hello world", keepends=True) == ["hello world"]


def test_lf_only():
    assert split_lines("a\nb\nc") == ["a", "b", "c"]
    assert split_lines("a\nb\nc", keepends=True) == ["a\n", "b\n", "c"]


def test_crlf_only():
    assert split_lines("a\r\nb\r\nc") == ["a", "b", "c"]
    assert split_lines("a\r\nb\r\nc", keepends=True) == ["a\r\n", "b\r\n", "c"]


def test_cr_only():
    assert split_lines("a\rb\rc") == ["a", "b", "c"]
    assert split_lines("a\rb\rc", keepends=True) == ["a\r", "b\r", "c"]


def test_mixed_terminators_in_one_file():
    text = "unix\nwindows\r\nold-mac\rend"
    assert split_lines(text) == ["unix", "windows", "old-mac", "end"]
    assert split_lines(text, keepends=True) == [
        "unix\n",
        "windows\r\n",
        "old-mac\r",
        "end",
    ]


def test_trailing_terminator_yields_no_extra_empty_line():
    # Matches str.splitlines()'s own convention: a trailing newline does not
    # produce a spurious final empty element.
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\nb\n", keepends=True) == ["a\n", "b\n"]


def test_lone_terminator_is_one_empty_line():
    assert split_lines("\n") == [""]
    assert split_lines("\n", keepends=True) == ["\n"]


def test_consecutive_terminators_yield_empty_lines():
    assert split_lines("a\n\nb") == ["a", "", "b"]
    assert split_lines("a\r\n\r\nb") == ["a", "", "b"]


def test_crlf_pair_never_splits_into_dangling_cr_lf():
    # A char-by-char scanner that checks LF/CR independently before CRLF
    # would double-count a "\r\n" pair as two terminators; this pins the
    # correct precedence (CRLF checked first).
    assert split_lines("a\r\nb", keepends=True) == ["a\r\n", "b"]
    assert len(split_lines("\r\n")) == 1


def test_does_not_break_on_characters_str_splitlines_treats_as_newlines():
    # Deliberately narrower than str.splitlines(): form feed, vertical tab,
    # unit/record/group separators, and the Unicode line/paragraph
    # separators are NOT terminators here -- see the module docstring for
    # why (they occur in ordinary text without meaning "new line" there).
    for exotic in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\u2028", "\u2029"):
        text = f"a{exotic}b"
        assert split_lines(text) == [text]
        assert split_lines(text, keepends=True) == [text]


def test_keepends_round_trip_reconstructs_original_text():
    for text in (
        "",
        "a",
        "a\nb\r\nc\rd",
        "\n\n\r\r\r\n",
        "no newline at all",
        "trailing\n",
    ):
        assert "".join(split_lines(text, keepends=True)) == text


def test_view_and_insert_agree_on_line_numbers_for_mixed_endings():
    # The scenario the module docstring calls out by name: view() numbers
    # lines with split_lines(), insert() maps a line number back with the
    # same function -- they must never disagree about what line N is.
    text = "first\r\nsecond\rthird\nfourth"
    view_lines = split_lines(text)
    insert_lines = split_lines(text, keepends=True)
    assert view_lines == ["first", "second", "third", "fourth"]
    assert len(view_lines) == len(insert_lines)
    assert "".join(insert_lines) == text
