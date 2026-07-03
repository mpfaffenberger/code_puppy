"""Phase B feature 2: completions — adapter, engine, popup navigation."""

import asyncio


from code_puppy.messaging.editor_completion import (
    CompletionEngine,
    query_completions,
    should_autotrigger,
)
from code_puppy.messaging.line_editor import RunningLineEditor


class FakeCompleter:
    """Static prompt_toolkit-style completer (pure logic)."""

    def __init__(self, words):
        self._words = words
        self.calls = []

    def get_completions(self, document, _event):
        self.calls.append((document.text, document.cursor_position))
        prefix = document.text_before_cursor
        from prompt_toolkit.completion import Completion

        for w in self._words:
            if w.startswith(prefix):
                yield Completion(w, start_position=-len(prefix), display=w)


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def up(self, _t):
        return None

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    def __init__(self):
        self.active = False
        self.query = ""

    def start(self):
        self.active = True
        self.query = ""

    def cancel(self):
        self.active = False

    def feed_char(self, ch):
        self.query += ch

    def backspace(self):
        self.query = self.query[:-1]

    def next_older(self):
        pass

    def current_match(self):
        return None

    def prompt_text(self):
        return f"(reverse-i-search)`{self.query}': "


def make_engine(words, repaints=None):
    loop = asyncio.get_running_loop()
    editor = RunningLineEditor(
        bar=FakeBar(), history=FakeHistory(), reverse_search=FakeRSearch()
    )
    engine = CompletionEngine(
        loop,
        apply_edit=editor.apply_completion,
        repaint=(repaints.append if repaints is not None else lambda: None)
        if repaints is not None
        else (lambda: None),
        completer_factory=lambda: FakeCompleter(words),
    )
    editor.attach_completion(engine)
    return editor, engine


async def settle():
    await asyncio.sleep(0.12)  # debounce (50ms) + executor round-trip


# =========================================================================
# Adapter
# =========================================================================


def test_query_completions_builds_document():
    completer = FakeCompleter(["/help", "/hero"])
    items = query_completions(completer, "/he", 3)
    assert completer.calls == [("/he", 3)]
    assert [i.text for i in items] == ["/help", "/hero"]
    assert items[0].start_position == -3


def test_should_autotrigger_prefixes():
    assert should_autotrigger("/mo", 3) is True
    assert should_autotrigger("look at @src/ma", 15) is True
    assert should_autotrigger("plain prose", 11) is False


# =========================================================================
# Engine: open / navigate / accept / close
# =========================================================================


async def test_typing_slash_opens_menu():
    editor, engine = make_engine(["/help", "/hero"])
    editor.feed("/")
    await settle()
    assert engine.is_open() is True
    lines, selected = engine.popup_rows()
    assert len(lines) == 2
    assert selected == 0


async def test_tab_accepts_selection_without_submitting():
    """Tab completes the highlighted item (classic prompt behavior) —
    it must NOT cycle to the next menu entry."""
    steers = []
    editor, engine = make_engine(["/help", "/hero"])
    editor.set_submit_router(lambda text, mode: steers.append(text) or None)
    editor.feed("/")
    await settle()
    editor.feed("\t")  # accept "/help", NOT navigate
    assert editor.buffer == "/help"
    assert steers == []  # no submission happened
    assert engine.is_open() is False


async def test_down_then_tab_accepts_navigated_selection():
    steers = []
    editor, engine = make_engine(["/help", "/hero"])
    editor.set_submit_router(lambda text, mode: steers.append(text) or None)
    editor.feed("/")
    await settle()
    editor.feed("\x1b[B")  # Down -> "/hero"
    editor.feed("\t")  # accept it
    assert editor.buffer == "/hero"
    assert steers == []
    assert engine.is_open() is False


async def test_enter_accepts_without_submitting():
    steers = []
    editor, engine = make_engine(["/help", "/hero"])
    editor.set_submit_router(lambda text, mode: steers.append(text) or None)
    editor.feed("/")
    await settle()
    editor.feed("\x1b[B")  # Down -> "/hero"
    editor.feed("\r")  # accept, NOT submit (classic behavior)
    assert editor.buffer == "/hero"
    assert steers == []
    assert engine.is_open() is False


async def test_accept_after_cursor_moved_left_splices_correctly():
    """Regression: completion offsets are anchored to the QUERY cursor.

    Type "/he", arrow LEFT (menu stays open), then Enter: the completion
    must replace the original "/he" cleanly — not splice against the
    moved cursor and produce garbage like "/helpe" that later submits
    as a plain prompt."""
    steers = []
    editor, engine = make_engine(["/help", "/hero"])
    editor.set_submit_router(lambda text, mode: steers.append(text) or None)
    for ch in "/he":
        editor.feed(ch)
    await settle()
    assert engine.is_open() is True
    editor.feed("\x1b[D")  # Left: cursor drifts, menu stays open
    editor.feed("\r")  # accept — must use the query-time anchor
    assert editor.buffer == "/help"
    assert editor.cursor == len("/help")
    assert steers == []  # accepted, never submitted
    assert engine.is_open() is False


async def test_tab_accept_after_cursor_moved_left_splices_correctly():
    editor, engine = make_engine(["/help", "/hero"])
    for ch in "/he":
        editor.feed(ch)
    await settle()
    editor.feed("\x1b[D")  # Left
    editor.feed("\x1b[D")  # Left again (cursor=1)
    editor.feed("\t")  # Tab-accept — same anchor rules as Enter
    assert editor.buffer == "/help"
    assert engine.is_open() is False


async def test_shift_tab_moves_backwards():
    editor, engine = make_engine(["/aa", "/bb", "/cc"])
    editor.feed("/")
    await settle()
    engine.move(1)
    editor.feed("\x1b[Z")  # Shift-Tab
    _lines, selected = engine.popup_rows()
    assert selected == 0


async def test_up_down_navigate_menu_before_history():
    editor, engine = make_engine(["/aa", "/bb"])
    editor.feed("/")
    await settle()
    editor.feed("\x1b[B")  # Down -> menu next, NOT history
    _lines, selected = engine.popup_rows()
    assert selected == 1


async def test_esc_closes_menu():
    editor, engine = make_engine(["/help"])
    editor.feed("/")
    await settle()
    fake_now = [100.0]
    editor._now = lambda: fake_now[0]
    editor.feed("\x1b")
    fake_now[0] += 1.0
    editor.check_timeout()  # bare ESC resolved -> close
    assert engine.is_open() is False


async def test_stale_result_discarded():
    editor, engine = make_engine(["/help"])
    editor.feed("/")  # query scheduled for "/"
    editor.feed("x")  # buffer changed -> earlier query is stale
    await settle()
    # The final state corresponds to "/x" (no matches), never "/".
    lines, _ = engine.popup_rows()
    assert all("/help" not in line for line in lines) or lines == []


async def test_backspace_requeries():
    editor, engine = make_engine(["/help", "/hero"])
    for ch in "/hel":
        editor.feed(ch)
    await settle()
    assert [line.strip() for line in engine.popup_rows()[0]] == ["/help"]
    editor.feed("\x7f")  # "/he" again -> both match
    await settle()
    assert len(engine.popup_rows()[0]) == 2


async def test_reverse_search_suppresses_completion():
    editor, engine = make_engine(["/help"])
    editor.feed("\x12")  # Ctrl+R
    editor.feed("/")  # goes to the search query, not the buffer
    await settle()
    assert engine.is_open() is False


# =========================================================================
# Programmatic mutations must NOT trigger completion (UX fix)
# =========================================================================


class RecallHistory(FakeHistory):
    """Up recalls a slash command; Down restores a working entry."""

    def up(self, _t):
        return "/model gpt-5.4"

    def down(self, _t):
        return "@src/working draft"


def attach_recall_history(editor):
    editor._history = RecallHistory()


async def test_history_recall_does_not_open_popup():
    editor, engine = make_engine(["/model", "/mcp"])
    attach_recall_history(editor)
    editor.feed("\x1b[A")  # Up: recall "/model gpt-5.4"
    await settle()
    assert editor.buffer == "/model gpt-5.4"
    assert engine.is_open() is False


async def test_working_entry_restore_does_not_open_popup():
    editor, engine = make_engine(["/model"])
    attach_recall_history(editor)
    editor.feed("\x1b[A")
    editor.feed("\x1b[B")  # Down: restore "@src/working draft"
    await settle()
    assert engine.is_open() is False


async def test_typing_after_recall_requeries():
    editor, engine = make_engine(["/model gpt-5.4x"])
    attach_recall_history(editor)
    editor.feed("\x1b[A")
    await settle()
    assert engine.is_open() is False
    editor.feed("x")  # genuine typing -> completion re-engages
    await settle()
    assert engine.is_open() is True


async def test_backspace_after_recall_requeries():
    editor, engine = make_engine(["/model gpt-5."])
    attach_recall_history(editor)
    editor.feed("\x1b[A")
    await settle()
    editor.feed("\x7f")  # backspace = editing -> re-query
    await settle()
    assert engine.is_open() is True


async def test_tab_after_recall_force_opens():
    editor, engine = make_engine(["/model gpt-5.4", "/model gpt-5.4-mini"])
    attach_recall_history(editor)
    editor.feed("\x1b[A")
    await settle()
    assert engine.is_open() is False
    editor.feed("\t")  # Tab must always work, however the buffer got here
    await settle()
    assert engine.is_open() is True


async def test_recall_invalidates_in_flight_query():
    """Type '/' (query scheduled) then recall before the debounce lands:
    the stale result must be discarded, popup stays closed."""
    editor, engine = make_engine(["/model"])
    attach_recall_history(editor)
    editor.feed("/")  # schedules a debounced query
    editor.feed("\x1b[A")  # recall bumps the seq via close()
    await settle()
    assert engine.is_open() is False


async def test_rsearch_accept_does_not_open_popup():
    editor, engine = make_engine(["/model"])

    class MatchRSearch(FakeRSearch):
        def current_match(self):
            return "/model gpt-5.4"

    editor._rsearch = MatchRSearch()
    editor.feed("\x12")  # Ctrl+R
    editor.feed("\r")  # accept the match into the buffer
    await settle()
    assert editor.buffer == "/model gpt-5.4"
    assert engine.is_open() is False


async def test_paste_of_slash_text_does_not_open_popup():
    editor, engine = make_engine(["/foo"])
    for ch in "\x1b[200~/foo @bar\x1b[201~":
        editor.feed(ch)
    await settle()
    assert editor.buffer == "/foo @bar"
    assert engine.is_open() is False


async def test_typing_after_paste_requeries():
    editor, engine = make_engine(["/foox"])
    for ch in "\x1b[200~/foo\x1b[201~":
        editor.feed(ch)
    await settle()
    assert engine.is_open() is False
    editor.feed("x")
    await settle()
    assert engine.is_open() is True


async def test_menu_open_up_down_still_navigates_menu():
    """No regression: with the popup OPEN, Up/Down move the selection —
    history recall never fires."""
    editor, engine = make_engine(["/aa", "/bb"])
    attach_recall_history(editor)
    editor.feed("/")
    await settle()
    assert engine.is_open() is True
    editor.feed("\x1b[B")  # Down -> menu next
    _lines, selected = engine.popup_rows()
    assert selected == 1
    assert editor.buffer == "/"  # no recall happened


# =========================================================================
# Popup rendering on the bar (precedence over sub-agent panel)
# =========================================================================


def test_popup_takes_precedence_over_panel():
    import io

    from code_puppy.messaging.bottom_bar import BottomBar

    class TTY(io.StringIO):
        def isatty(self):
            return True

    tty = TTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_panel_lines(["agent row"])
    tty.truncate(0)
    tty.seek(0)
    bar.set_popup_lines(["/help", "/hero"], selected=1)
    out = tty.getvalue()
    assert "/help" in out and "/hero" in out
    assert "\x1b[1;36m/hero\x1b[22;39m" in out  # selected row: brand accent
    assert "agent row" not in out  # panel hidden while popup open
    # Close popup -> panel restored.
    tty.truncate(0)
    tty.seek(0)
    bar.set_popup_lines([])
    assert "agent row" in tty.getvalue()
    bar.stop()
