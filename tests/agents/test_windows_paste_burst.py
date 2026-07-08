"""Windows console paste coalescing (_key_listeners burst helpers).

The console input queue has no bracketed paste: a paste arrives as a
flood of individual chars. The old one-char-per-50ms-tick loop rendered
it like slow typing and submitted a prompt per pasted newline. The
listener now drains the whole burst per tick and wraps large all-text
bursts in a synthesized bracketed paste.
"""

import pytest

from code_puppy.agents._key_listeners import (
    _PASTE_CLOSE,
    _PASTE_OPEN,
    _SHIFT_ENTER_SEQ,
    _WIN_BURST_CAP,
    _WIN_PASTE_MIN_CHARS,
    _coalesce_paste_burst,
    _drain_windows_burst,
    _route_windows_burst,
    _windows_char_to_seq,
    set_line_editor,
)


class FakeMsvcrt:
    """Scripted console input queue."""

    def __init__(self, keys):
        self.keys = list(keys)

    def kbhit(self):
        return bool(self.keys)

    def getwch(self):
        return self.keys.pop(0)


class TestDrain:
    def test_drains_entire_pending_burst(self):
        fake = FakeMsvcrt(list("hello"))
        items = _drain_windows_burst(fake)
        assert items == [("char", c) for c in "hello"]
        assert fake.keys == []  # nothing left for the next tick

    def test_extended_key_pair_translates_to_seq(self):
        fake = FakeMsvcrt(["\xe0", "H"])  # Up arrow
        assert _drain_windows_burst(fake) == [("seq", "\x1b[A")]

    def test_unknown_extended_pair_swallowed(self):
        fake = FakeMsvcrt(["\x00", "\x3b"])  # F1 — unmapped
        assert _drain_windows_burst(fake) == []

    def test_mixed_burst_preserves_order(self):
        fake = FakeMsvcrt(["a", "\xe0", "K", "b"])
        assert _drain_windows_burst(fake) == [
            ("char", "a"),
            ("seq", "\x1b[D"),
            ("char", "b"),
        ]

    def test_burst_cap_leaves_remainder_queued(self):
        fake = FakeMsvcrt(["x"] * (_WIN_BURST_CAP + 10))
        items = _drain_windows_burst(fake)
        assert len(items) == _WIN_BURST_CAP
        assert len(fake.keys) == 10

    def test_first_key_read_despite_kbhit_lie(self):
        """The caller consumed the only kbhit() True; the drain must still
        read the first key (and its pushback-buffered pair tail)
        unconditionally — kbhit() cannot see either of them."""

        class LyingMsvcrt:
            def __init__(self, keys):
                self.keys = list(keys)

            def kbhit(self):
                return False  # the lie: data pending but queue looks empty

            def getwch(self):
                return self.keys.pop(0)

        items = _drain_windows_burst(LyingMsvcrt(["\xe0", "K"]))
        assert items == [("seq", "\x1b[D")]


class TestCoalesce:
    def test_single_char_is_not_paste(self):
        assert _coalesce_paste_burst([("char", "a")]) is None

    def test_typing_roll_below_threshold_is_not_paste(self):
        # 'i' + Enter landing inside one poll tick must still SUBMIT.
        items = [("char", "i"), ("char", "\r")]
        assert len(items) < _WIN_PASTE_MIN_CHARS
        assert _coalesce_paste_burst(items) is None

    def test_large_text_burst_is_paste(self):
        items = [("char", c) for c in "line one\rline two"]
        assert _coalesce_paste_burst(items) == "line one\rline two"

    def test_burst_with_extended_key_is_typing(self):
        items = [("char", "a"), ("seq", "\x1b[A"), ("char", "b"), ("char", "c")]
        assert _coalesce_paste_burst(items) is None

    def test_min_chars_boundary(self):
        items = [("char", c) for c in "abc"]
        assert len(items) == _WIN_PASTE_MIN_CHARS
        assert _coalesce_paste_burst(items) == "abc"


class TestCoalesceVtInput:
    """With ENABLE_VIRTUAL_TERMINAL_INPUT, special keys arrive as VT
    escape sequences (3+ chars in one tick) — they must classify as
    typing, not paste, or arrows insert literal ESC garbage. Terminal
    pastes are always bracketed while ?2004h is armed, so the markers
    stay the paste discriminator."""

    def test_single_arrow_seq_is_typing(self):
        assert _coalesce_paste_burst([("char", c) for c in "\x1b[A"]) is None

    def test_key_repeat_arrow_flood_is_typing(self):
        items = [("char", c) for c in "\x1b[B" * 20]
        assert _coalesce_paste_burst(items) is None

    def test_chars_then_arrow_in_one_tick_is_typing(self):
        items = [("char", c) for c in "ab\x1b[D"]
        assert _coalesce_paste_burst(items) is None

    def test_bracketed_burst_with_markers_still_coalesces(self):
        wire = _PASTE_OPEN + "hello" + _PASTE_CLOSE
        assert _coalesce_paste_burst([("char", c) for c in wire]) == wire

    def test_empty_bracketed_paste_still_coalesces(self):
        # The image-only Ctrl+V payload — must reach the editor verbatim.
        wire = _PASTE_OPEN + _PASTE_CLOSE
        assert _coalesce_paste_burst([("char", c) for c in wire]) == wire


class TestShiftEnter:
    """Classic console input encodes Shift+Enter as a bare \\r — the
    listener disambiguates via the live Shift state and synthesizes the
    CSI-u sequence the editor already maps to newline."""

    def test_shift_enter_becomes_csi_u_newline_seq(self):
        assert _windows_char_to_seq("\r", shift_is_down=lambda: True) == (
            _SHIFT_ENTER_SEQ
        )

    def test_plain_enter_stays_a_regular_keystroke(self):
        assert _windows_char_to_seq("\r", shift_is_down=lambda: False) is None

    def test_shift_with_ordinary_char_is_untouched(self):
        # Shift+A arrives as 'A' already — no translation wanted.
        assert _windows_char_to_seq("A", shift_is_down=lambda: True) is None

    def test_seq_maps_to_editor_newline_action(self):
        """End-to-end contract: the synthesized body is a known newline."""
        from code_puppy.messaging.editor_keys import classify_csi

        assert _SHIFT_ENTER_SEQ.startswith("\x1b[")
        assert classify_csi(_SHIFT_ENTER_SEQ[2:]) == "newline"

    def test_default_shift_checker_never_raises(self):
        """On non-Windows there is no user32 — must degrade to False
        (plain Enter) instead of raising into the listener loop."""
        from code_puppy.agents._key_listeners import _win_shift_is_down

        assert _win_shift_is_down() in (True, False)


def _chars(wire: str) -> list:
    return [("char", c) for c in wire]


def _route(items: list) -> None:
    _route_windows_burst(items, lambda: None, None, None)


class TestRouteBurst:
    """Terminal-bracketed pastes must pass through VERBATIM.

    Windows Terminal honors the ?2004h arming the bottom bar emits and
    ConPTY flattens the ESC[200~/201~ markers into the char flood. The
    old lane re-wrapped that flood in a SECOND pair of markers, so the
    editor's paste payload became the literal inner opener — classified
    as "text", never as the empty payload that triggers clipboard-image
    capture. That was the Windows-only Ctrl+V image-paste regression.
    """

    @pytest.fixture
    def editor(self):
        from code_puppy.messaging.line_editor import RunningLineEditor

        ed = RunningLineEditor()
        set_line_editor(ed)
        try:
            yield ed
        finally:
            set_line_editor(None)

    @pytest.fixture
    def clipboard_image(self, monkeypatch):
        """Fake an image-bearing clipboard (never shell out in CI)."""
        placeholder = "[ clipboard image 1]"
        monkeypatch.setattr(
            "code_puppy.command_line.clipboard.capture_clipboard_image_to_pending",
            lambda: placeholder,
        )
        return placeholder

    def test_image_only_paste_captures_clipboard_image(self, editor, clipboard_image):
        # WT pastes an image-only clipboard as an EMPTY bracketed paste.
        _route(_chars(_PASTE_OPEN + _PASTE_CLOSE))
        assert editor._buffer == clipboard_image + " "

    def test_bracketed_text_paste_is_not_double_wrapped(self, editor):
        _route(_chars(_PASTE_OPEN + "hello world" + _PASTE_CLOSE))
        assert editor._buffer == "hello world"
        assert "\x1b" not in editor._buffer

    def test_raw_flood_still_gets_synthesized_wrap(self, editor):
        # Legacy conhost lane: no markers → newlines stay in the buffer.
        _route(_chars("line one\rline two"))
        assert editor._buffer == "line one\nline two"

    def test_split_bracketed_paste_across_poll_ticks(self, editor):
        _route(_chars(_PASTE_OPEN + "first "))
        assert editor.paste_active
        _route(_chars("second" + _PASTE_CLOSE))
        assert not editor.paste_active
        assert editor._buffer == "first second"

    def test_small_typing_burst_dispatches_per_key(self, editor):
        _route(_chars("a"))
        assert editor._buffer == "a"

    def test_vt_arrow_burst_moves_cursor_instead_of_pasting(self, editor):
        # VT-input arrows arrive as a char burst; they must reach the
        # editor's CSI state machine, not the buffer as literal text.
        _route(_chars("ab"))
        _route(_chars("\x1b[D\x1b[D"))
        _route(_chars("X"))
        assert editor._buffer == "Xab"
        assert "\x1b" not in editor._buffer
