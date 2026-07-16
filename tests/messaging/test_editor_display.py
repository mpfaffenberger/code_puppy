"""Attachment display tags for the persistent editor (editor_display).

Classic parity: recognised attachment paths render as ``[png image]``
tags in the prompt row (AttachmentPlaceholderProcessor behavior) while
the REAL buffer keeps the path for submit-time resolution.
"""

from code_puppy.messaging.editor_display import (
    MAX_TEXT_LENGTH_FOR_REALTIME,
    to_display,
)


def _make_png(tmp_path, name="shot.png"):
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return p


class TestToDisplayBasics:
    def test_plain_text_unchanged(self):
        assert to_display("hello world", 5) == ("hello world", 5)

    def test_empty_text_unchanged(self):
        assert to_display("", 0) == ("", 0)

    def test_no_separator_short_circuits(self, tmp_path):
        # No / or \ anywhere -> detection skipped entirely.
        assert to_display("look at shot.png", 16) == ("look at shot.png", 16)

    def test_long_text_skipped(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"{png} " + "x" * MAX_TEXT_LENGTH_FOR_REALTIME
        assert to_display(text, 0) == (text, 0)

    def test_nonexistent_path_unchanged(self):
        text = "/nonexistent/path/to/nothing.png"
        display, cursor = to_display(text, len(text))
        assert display == text
        assert cursor == len(text)


class TestToDisplayTags:
    def test_image_path_renders_png_tag(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"look at {png}"
        display, _ = to_display(text, len(text))
        assert "[png image]" in display
        assert str(png) not in display
        assert display.startswith("look at ")

    def test_unsupported_extension_no_tag(self, tmp_path):
        # .txt is neither image nor document: detection marks it
        # unsupported -> has_path() False -> no tag (classic parity).
        f = tmp_path / "notes.txt"
        f.write_text("hi")
        text = f"read {f}"
        display, _ = to_display(text, len(text))
        assert display == text

    def test_multiple_images_all_tagged(self, tmp_path):
        a = _make_png(tmp_path, "a.png")
        b = _make_png(tmp_path, "b.png")
        text = f"{a} vs {b}"
        display, _ = to_display(text, len(text))
        assert display.count("[png image]") == 2

    def test_quoted_path_renders_tag(self, tmp_path):
        # Windows terminals paste copied files as quoted paths.
        png = _make_png(tmp_path)
        text = f'"{png}" describe'
        display, _ = to_display(text, len(text))
        assert "[png image]" in display
        assert str(png) not in display


class TestToDisplayCursor:
    def test_cursor_before_span_identity(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"look at {png}"
        display, cursor = to_display(text, 4)
        assert cursor == 4
        assert display[:8] == "look at "

    def test_cursor_at_end_maps_to_display_end(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"look at {png}"
        display, cursor = to_display(text, len(text))
        assert cursor == len(display)

    def test_cursor_inside_span_maps_to_tag_start(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"look at {png}"
        span_start = len("look at ")
        display, cursor = to_display(text, span_start + 3)
        assert cursor == span_start  # classic: in-span -> tag start

    def test_cursor_after_span_offsets_by_delta(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"{png} tail"
        display, cursor = to_display(text, len(text) - 2)
        assert display[cursor:] == "il"

    def test_cursor_never_out_of_bounds(self, tmp_path):
        png = _make_png(tmp_path)
        text = f"x {png}"
        for pos in range(len(text) + 1):
            display, cursor = to_display(text, pos)
            assert 0 <= cursor <= len(display)


class TestNeverRaises:
    def test_detection_failure_falls_back(self, monkeypatch):
        import code_puppy.messaging.editor_display as mod

        def boom(text):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(mod, "_find_spans", boom)
        assert to_display("a/b", 1) == ("a/b", 1)
