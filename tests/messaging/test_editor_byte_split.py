"""Regression tests for the live 'arrows don't work' bug.

Root cause was in the POSIX listener (buffered ``stdin.read(1)`` vs
``select()`` on the raw fd — see ``_read_chunk``), but this battery also
locks down the editor's ESC state machine under byte-at-a-time delivery:
every sequence family fed one char per ``feed()`` call, with
``check_timeout()`` ticks interleaved at every split point (fake clock,
inside the disambiguation window — ticks must NOT expire a live ESC).
"""

import io
import os

import pytest

from code_puppy.messaging.line_editor import RunningLineEditor


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def __init__(self):
        self.ups = 0
        self.downs = 0

    def up(self, _t):
        self.ups += 1
        return f"history-{self.ups}"

    def down(self, _t):
        self.downs += 1
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    active = False

    def cancel(self):
        pass


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def editor(clock):
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        now=clock,
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def feed_split(editor, seq, tick_between=False):
    """Feed ``seq`` one char per feed() call, optionally ticking between."""
    for ch in seq:
        editor.feed(ch)
        if tick_between:
            editor.check_timeout()


# =========================================================================
# Byte-at-a-time sequence families (with + without interleaved ticks)
# =========================================================================


@pytest.mark.parametrize("tick", [False, True])
def test_csi_up_byte_at_a_time_navigates_history(editor, tick):
    feed_split(editor, "\x1b[A", tick_between=tick)
    assert editor._history.ups == 1
    assert editor.buffer == "history-1"


@pytest.mark.parametrize("tick", [False, True])
def test_ss3_up_byte_at_a_time_navigates_history(editor, tick):
    """Application cursor mode: some terminals send ESC O A for Up!"""
    feed_split(editor, "\x1bOA", tick_between=tick)
    assert editor._history.ups == 1


@pytest.mark.parametrize("tick", [False, True])
def test_csi_down_byte_at_a_time(editor, tick):
    feed_split(editor, "\x1b[B", tick_between=tick)
    assert editor._history.downs == 1


@pytest.mark.parametrize(
    "seq,expected_cursor",
    [("\x1b[D", 1), ("\x1b[C", 2), ("\x1b[H", 0), ("\x1b[F", 2)],
)
@pytest.mark.parametrize("tick", [False, True])
def test_csi_cursor_moves_byte_at_a_time(editor, seq, expected_cursor, tick):
    for ch in "ab":
        editor.feed(ch)
    if seq == "\x1b[C":  # start from home so Right has room
        feed_split(editor, "\x1b[H")
        feed_split(editor, "\x1b[C" * 0)
        editor._cursor = 1
    feed_split(editor, seq, tick_between=tick)
    assert editor.cursor == expected_cursor


@pytest.mark.parametrize("tick", [False, True])
def test_alt_arrow_word_jump_byte_at_a_time(editor, tick):
    for ch in "two words":
        editor.feed(ch)
    feed_split(editor, "\x1b[1;3D", tick_between=tick)
    assert editor.cursor == 4


@pytest.mark.parametrize("tick", [False, True])
def test_meta_b_byte_at_a_time(editor, tick):
    for ch in "alpha beta":
        editor.feed(ch)
    feed_split(editor, "\x1bb", tick_between=tick)
    assert editor.cursor == 6


@pytest.mark.parametrize("tick", [False, True])
def test_f2_ss3_byte_at_a_time(editor, tick):
    feed_split(editor, "\x1bOQ", tick_between=tick)
    assert editor.multiline is True


@pytest.mark.parametrize("tick", [False, True])
def test_f2_csi_byte_at_a_time(editor, tick):
    feed_split(editor, "\x1b[12~", tick_between=tick)
    assert editor.multiline is True


@pytest.mark.parametrize("tick", [False, True])
def test_alt_enter_byte_at_a_time(editor, tick):
    submitted = []
    editor.set_submit_router(lambda text, mode: submitted.append((text, mode)))
    for ch in "queue me":
        editor.feed(ch)
    editor.feed("\x1b")
    if tick:
        editor.check_timeout()
    editor.feed("\r")
    assert submitted == [("queue me", "queue")]


@pytest.mark.parametrize("tick", [False, True])
def test_alt_backspace_byte_at_a_time(editor, tick):
    for ch in "kill word":
        editor.feed(ch)
    feed_split(editor, "\x1b\x7f", tick_between=tick)
    assert editor.buffer == "kill "


@pytest.mark.parametrize("tick", [False, True])
def test_paste_open_byte_at_a_time(editor, tick):
    feed_split(editor, "\x1b[200~", tick_between=tick)
    assert editor._paste.active is True
    for ch in "pasted\x1b[201~":
        editor.feed(ch)
    assert editor.buffer == "pasted"


def test_bare_esc_still_expires_via_tick(editor, clock):
    """The ticks above must not break BARE-ESC expiry: an ESC with nothing
    following (beyond the window) resolves and later chars are literal."""
    editor.feed("\x1b")
    clock.t += 1.0  # window expired
    editor.check_timeout()
    editor.feed("A")
    assert editor.buffer == "A"  # literal, not an arrow


# =========================================================================
# The actual root cause: raw-fd chunk reads in the POSIX listener
# =========================================================================


def test_read_chunk_returns_all_available_bytes():
    """os.read on the raw fd must deliver a whole burst ('\\x1b[A') in one
    go — the buffered TextIOWrapper.read(1) stranded the tail."""
    import codecs

    from code_puppy.agents._key_listeners import _read_chunk

    r, w = os.pipe()
    try:
        os.write(w, b"\x1b[A")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        assert _read_chunk(r, decoder) == "\x1b[A"
    finally:
        os.close(r)
        os.close(w)


def test_read_chunk_reassembles_split_utf8():
    import codecs

    from code_puppy.agents._key_listeners import _read_chunk

    r, w = os.pipe()
    try:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        dog = "\U0001f436".encode("utf-8")
        os.write(w, dog[:2])  # first half of a 4-byte char
        first = _read_chunk(r, decoder)
        os.write(w, dog[2:])
        second = _read_chunk(r, decoder)
        assert (first or "") + (second or "") == "\U0001f436"
    finally:
        os.close(r)
        os.close(w)


def test_read_chunk_eof_returns_none():
    import codecs

    from code_puppy.agents._key_listeners import _read_chunk

    r, w = os.pipe()
    os.close(w)
    try:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        assert _read_chunk(r, decoder) is None
    finally:
        os.close(r)


def test_posix_listener_no_longer_uses_buffered_stdin_read():
    """Belt-and-braces source check: the select loop must never go back
    to TextIOWrapper reads."""
    import inspect

    from code_puppy.agents import _key_listeners

    # The read loop lives in _posix_read_session (the supervisor in
    # _listen_posix just restarts sessions) — check both, so a future
    # refactor can't sneak a buffered read into either.
    src = inspect.getsource(_key_listeners._listen_posix) + inspect.getsource(
        _key_listeners._posix_read_session
    )
    assert "stdin.read(" not in src
    assert "_read_chunk" in src


# =========================================================================
# Suspect 2: persistent-path history wiring (file-backed store)
# =========================================================================


def test_persistent_editor_history_is_file_backed(monkeypatch, tmp_path):
    from code_puppy import config as cp_config
    from code_puppy.messaging import bottom_bar as bottom_bar_mod
    import code_puppy.messaging.run_ui as run_ui_mod

    history_file = str(tmp_path / "command_history.txt")
    monkeypatch.setattr(cp_config, "COMMAND_HISTORY_FILE", history_file)
    # Seed an entry the way the classic prompt would have written it.
    from code_puppy.messaging.editor_history import HistoryStore

    HistoryStore(history_file).append("seeded entry")

    monkeypatch.setattr(run_ui_mod, "_spawn_persistent_listener", lambda: None)

    class TTY(io.StringIO):
        def isatty(self):
            return True

    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=TTY(), get_size=lambda: (80, 24)
    )
    try:
        assert run_ui_mod.start_persistent_ui() is True
        editor = run_ui_mod.get_run_editor()
        # The navigator's store points at COMMAND_HISTORY_FILE...
        assert editor._history._store._path == history_file
        # ...and Up actually recalls the seeded entry.
        editor.feed("\x1b[A")
        assert editor.buffer == "seeded entry"
    finally:
        run_ui_mod.stop_persistent_ui()
        bottom_bar_mod.reset_bottom_bar()


# =========================================================================
# Suspect 3: menu-state gating
# =========================================================================


def test_attached_but_closed_menu_does_not_block_history(editor):
    class ClosedEngine:
        def is_open(self):
            return False

        def on_edit(self, *a):
            pass

        def on_tab(self, *a):
            return True

        def close(self):
            pass

        def set_suppressed(self, *_a):
            pass

        def move(self, *_a):  # must NOT be reached
            raise AssertionError("menu consumed the arrow while closed")

    editor.attach_completion(ClosedEngine())
    feed_split(editor, "\x1b[A")
    assert editor._history.ups == 1
