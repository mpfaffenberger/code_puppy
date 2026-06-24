"""Unit tests for the LivePrinterWriter file-like adapter.

The writer buffers partial lines and emits complete ones via the active
spinner's ``print_above``, so streamed termflow text scrolls above the
pinned footer instead of racing with the Live refresh thread.
"""

from __future__ import annotations

from rich.text import Text

from code_puppy.messaging.live_printer_writer import LivePrinterWriter


class _CaptureSpinner:
    """Minimal spinner stub capturing every print_above call."""

    def __init__(self) -> None:
        self.calls: list = []

    def print_above(
        self, renderable, *, soft_wrap: bool = True, end: str = "\n"
    ) -> None:
        # The streaming writer passes end="" because its chunks carry their
        # own newlines; record it so tests can assert the no-double-newline
        # contract if they want.
        self.last_end = end
        self.calls.append(renderable)


def _ref_factory(spinner):
    return lambda: spinner


def test_partial_line_is_buffered_until_newline():
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    writer.write("Hello, ")
    writer.write("world")
    assert spinner.calls == [], "no newline yet → nothing emitted"

    writer.write("!\n")
    assert len(spinner.calls) == 1, "newline flushes the line"
    emitted = spinner.calls[0]
    assert isinstance(emitted, Text)
    assert emitted.plain == "Hello, world!\n"


def test_multiple_lines_in_single_write():
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    writer.write("line1\nline2\nline3")
    # The writer finds the last newline in the buffer and emits everything
    # up to it as a single chunk (fewer print_above calls than lines).
    # "line3" with no trailing newline stays buffered.
    assert len(spinner.calls) == 1
    assert spinner.calls[0].plain == "line1\nline2\n"

    writer.flush()
    assert len(spinner.calls) == 2
    assert spinner.calls[1].plain == "line3"


def test_flush_emits_trailing_partial_line():
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    writer.write("trailing partial")
    assert spinner.calls == []
    writer.flush()
    assert len(spinner.calls) == 1
    assert spinner.calls[0].plain == "trailing partial"


def test_close_drops_remaining_buffer():
    """``close`` flushes the tail so streaming output never gets stuck."""
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    writer.write("unfinished")
    writer.close()
    assert len(spinner.calls) == 1
    assert spinner.calls[0].plain == "unfinished"
    # Subsequent writes after close are dropped.
    writer.write("after-close\n")
    assert len(spinner.calls) == 1


def test_no_active_spinner_silently_drops():
    """When there's no spinner (e.g., pre-boot or non-TTY), writes are safe
    no-ops — the caller's streaming path isn't broken."""
    writer = LivePrinterWriter(spinner_ref=lambda: None)
    writer.write("this should not crash\n")
    writer.flush()


def test_ansi_codes_preserved_as_text_styling():
    """ANSI escape sequences are parsed into Rich Text spans so colors /
    bold / etc. survive the trip through ``print_above``."""
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    # Red text ANSI escape.
    writer.write("\x1b[31mred\x1b[0m\n")
    assert len(spinner.calls) == 1
    emitted = spinner.calls[0]
    assert isinstance(emitted, Text)
    # Plain text contains the visible chars only (escapes stripped).
    assert emitted.plain == "red\n"
    # And at least one span carries the parsed red color.
    styles = {str(span.style) for span in emitted.spans}
    assert any("red" in s or "31" in s or "color(" in s for s in styles), styles


def test_excessive_blank_lines_are_collapsed():
    """Models emit 2-5 trailing newlines between sections; in scrollback
    that renders as 2-5 empty lines. ``_collapse_blank_lines`` must reduce
    any run of 3+ newlines to a single blank line (i.e. \\n\\n) so the
    rendered output has at most one blank line between paragraphs."""
    from code_puppy.messaging.live_printer_writer import _collapse_blank_lines

    # 6 newlines between a and b -> 2 newlines (one blank line)
    assert _collapse_blank_lines("a\n\n\n\n\n\nb") == "a\n\nb"
    # 3 newlines -> 2 newlines
    assert _collapse_blank_lines("a\n\n\nb") == "a\n\nb"
    # Already 1 blank line stays
    assert _collapse_blank_lines("a\n\nb") == "a\n\nb"
    # No blank line stays
    assert _collapse_blank_lines("a\nb") == "a\nb"
    # Empty input
    assert _collapse_blank_lines("") == ""
    # Mixed: paragraph breaks preserved, extras collapsed
    assert _collapse_blank_lines("a\n\nb\n\n\nc") == "a\n\nb\n\nc"
    # Single trailing newline preserved (normal end-of-line)
    assert _collapse_blank_lines("hello\n") == "hello\n"


def test_excessive_blank_lines_collapsed_in_emitted_output():
    """End-to-end: when termflow writes 6 newlines between sections, the
    spinner should only receive 2 (one blank line)."""
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    writer.write("section one\n\n\n\n\n\nsection two\n")
    assert len(spinner.calls) == 1
    emitted = spinner.calls[0]
    assert isinstance(emitted, Text)
    # Exactly one blank line between sections in the rendered text.
    assert emitted.plain == "section one\n\nsection two\n"


def test_blank_line_chunks_collapsed_across_writes():
    """Models sometimes stream blank lines as their own writes (one ``\\n``
    per write). Per-chunk collapse alone still allows 2-5 empty lines in
    scrollback. The writer must track state across writes so a run of
    blank-line writes collapses to a single blank line in total."""
    spinner = _CaptureSpinner()
    writer = LivePrinterWriter(spinner_ref=_ref_factory(spinner))

    # "a\n" then 6 standalone "\n" writes then "b\n"
    writer.write("a\n")
    for _ in range(6):
        writer.write("\n")
    writer.write("b\n")
    writer.flush()

    combined = "".join(
        c.plain if isinstance(c, Text) else str(c) for c in spinner.calls
    )
    # Single blank line between the two content lines, regardless of how
    # many blank-line writes came in between.
    assert combined == "a\n\nb\n", f"Got: {repr(combined)}"


def test_blank_line_collapse_works_when_no_spinner_active():
    """In compact mode without a registered spinner, termflow output is
    routed through ``BlankLineCollapsingFile`` (a file-like wrapper
    around ``console.file``). The wrapper must also collapse across
    writes — same state machine as the spinner path."""
    import io

    from code_puppy.messaging.live_printer_writer import BlankLineCollapsingFile

    sink = io.StringIO()
    writer = BlankLineCollapsingFile(sink)

    writer.write("a\n")
    for _ in range(6):
        writer.write("\n")
    writer.write("b\n")
    writer.flush()

    assert sink.getvalue() == "a\n\nb\n", f"Got: {repr(sink.getvalue())}"


def test_chunk_ends_with_blank_distinguishes_terminator_from_blank():
    """``_chunk_ends_with_blank`` must NOT classify a single trailing
    newline (e.g. ``"abc\\n"``) as a blank line — that's just the
    terminator of the last content line. Only ``"abc\\n\\n"`` (one
    content line followed by an empty line) is a blank line at the end."""
    from code_puppy.messaging.live_printer_writer import _chunk_ends_with_blank

    assert _chunk_ends_with_blank("abc\n") is False
    assert _chunk_ends_with_blank("abc\n\n") is True
    assert _chunk_ends_with_blank("abc\ndef\n") is False
    assert _chunk_ends_with_blank("abc\ndef\n\n") is True
    assert _chunk_ends_with_blank("\n") is True
    assert _chunk_ends_with_blank("\n\n") is True
    assert _chunk_ends_with_blank("") is False
