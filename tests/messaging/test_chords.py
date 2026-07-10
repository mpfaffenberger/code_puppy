"""Ctrl+X chord registry: registration, dispatch, hints."""

import pytest

from code_puppy.messaging import chords

KEYS = ["\x05", "\x18", "\x02", "\x14"]


@pytest.fixture(autouse=True)
def _clean_registry():
    for key in KEYS:
        chords.unregister_chord(key)
    yield
    for key in KEYS:
        chords.unregister_chord(key)


def test_register_and_dispatch():
    calls = []
    chords.register_chord("\x05", lambda: calls.append(1), "Ctrl+E edit")
    assert chords.dispatch_chord("\x05") is True
    assert calls == [1]


def test_dispatch_unbound_returns_false():
    assert chords.dispatch_chord("\x05") is False


def test_unregister_removes_binding():
    chords.register_chord("\x18", lambda: None, "Ctrl+X kill")
    chords.unregister_chord("\x18")
    assert chords.get_chord("\x18") is None
    assert chords.dispatch_chord("\x18") is False


def test_register_replaces_existing_binding():
    first, second = [], []
    chords.register_chord("\x02", lambda: first.append(1), "old")
    chords.register_chord("\x02", lambda: second.append(1), "new")
    chords.dispatch_chord("\x02")
    assert first == []
    assert second == [1]


def test_callback_exception_is_swallowed():
    def boom():
        raise RuntimeError("chord exploded")

    chords.register_chord("\x14", boom, "Ctrl+T boom")
    assert chords.dispatch_chord("\x14") is True  # bound, even though it raised


def test_hint_lists_bindings_in_registration_order():
    chords.register_chord("\x05", lambda: None, "Ctrl+E edit in $EDITOR")
    chords.register_chord("\x18", lambda: None, "Ctrl+X kill shells")
    hint = chords.chord_hint()
    assert hint.startswith("Ctrl+X chord: ")
    assert hint.endswith(" · Esc cancel")
    assert hint.index("Ctrl+E edit") < hint.index("Ctrl+X kill")


def test_hint_empty_without_bindings():
    assert chords.chord_hint() == ""


def test_hint_paint_and_clear_never_raise():
    chords.register_chord("\x05", lambda: None, "Ctrl+E edit")
    chords.show_chord_hint()  # best-effort, must not raise headless
    chords.clear_chord_hint()


# =========================================================================
# Status-row save/restore (the hint must not eat the token/context line)
# =========================================================================


@pytest.fixture
def bar():
    from code_puppy.messaging.bottom_bar import get_bottom_bar

    bar = get_bottom_bar()
    original = bar.get_status()
    yield bar
    bar.set_status(original)
    chords.clear_chord_hint()  # drop any leftover snapshot state


def test_hint_restores_displaced_status(bar):
    bar.set_status("5.5k/500k tokens")
    chords.register_chord("\x05", lambda: None, "Ctrl+E edit")
    chords.show_chord_hint()
    assert bar.get_status().startswith("Ctrl+X chord: ")
    chords.clear_chord_hint()
    assert bar.get_status() == "5.5k/500k tokens"  # context line survives Esc


def test_hint_clear_keeps_newer_status(bar):
    """If the status display repainted mid-chord, newest text wins."""
    bar.set_status("old tokens")
    chords.register_chord("\x05", lambda: None, "Ctrl+E edit")
    chords.show_chord_hint()
    bar.set_status("new tokens")  # periodic status tick during the chord
    chords.clear_chord_hint()
    assert bar.get_status() == "new tokens"  # stale snapshot NOT restored


def test_clear_without_show_is_a_noop(bar):
    bar.set_status("precious status")
    chords.clear_chord_hint()  # e.g. Ctrl+C disarm with no hint painted
    assert bar.get_status() == "precious status"


def test_show_with_no_bindings_paints_nothing(bar):
    bar.set_status("precious status")
    chords.show_chord_hint()  # empty registry -> no hint
    assert bar.get_status() == "precious status"
    chords.clear_chord_hint()
    assert bar.get_status() == "precious status"
