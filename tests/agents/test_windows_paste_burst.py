"""Windows console paste coalescing (_key_listeners burst helpers).

The console input queue has no bracketed paste: a paste arrives as a
flood of individual chars. The old one-char-per-50ms-tick loop rendered
it like slow typing and submitted a prompt per pasted newline. The
listener now drains the whole burst per tick and wraps large all-text
bursts in a synthesized bracketed paste.
"""

from code_puppy.agents._key_listeners import (
    _WIN_BURST_CAP,
    _WIN_PASTE_MIN_CHARS,
    _coalesce_paste_burst,
    _drain_windows_burst,
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
