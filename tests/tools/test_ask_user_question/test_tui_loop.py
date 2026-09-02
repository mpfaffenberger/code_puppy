"""Headless tests for the termflow question TUI.

Drives QuestionTUI with scripted keys and a StringIO output -- no tty,
no mocked key events. Each scenario scripts a full user journey and
asserts on the returned (answers, cancelled, timed_out) triple.
"""

from __future__ import annotations

import re
from io import StringIO

from code_puppy.tools.ask_user_question.models import Question
from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState
from code_puppy.tools.ask_user_question.tui_loop import QuestionTUI, run_question_tui


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def make_questions(count: int = 1, multi: bool = False) -> list[Question]:
    return [
        Question(
            question=f"Question number {i}?",
            header=f"Q{i}",
            multi_select=multi,
            options=[
                {"label": f"Alpha {i}", "description": "first"},
                {"label": f"Beta {i}", "description": "second"},
            ],
        )
        for i in range(count)
    ]


def drive(questions: list[Question], keys: list[str], timeout_seconds: int = 300):
    """Run the TUI headlessly on a key script. Returns (result, output)."""
    state = QuestionUIState(questions)
    state.timeout_seconds = timeout_seconds
    script = iter(keys)
    out = StringIO()
    tui = QuestionTUI(
        state,
        key_source=lambda: next(script),
        output=out,
        size=lambda: (100, 30),
        use_alt_screen=False,
    )
    return tui.run(), out.getvalue()


class TestSingleSelect:
    def test_enter_selects_and_double_enter_submits(self):
        (answers, cancelled, timed_out), _ = drive(
            make_questions(1), ["enter", "enter"]
        )
        assert not cancelled and not timed_out
        assert answers[0].selected_options == ["Alpha 0"]

    def test_navigate_then_select(self):
        (answers, _, _), _ = drive(make_questions(1), ["down", "enter", "enter"])
        assert answers[0].selected_options == ["Beta 0"]

    def test_space_selects_without_advancing(self):
        (answers, _, _), _ = drive(make_questions(2), [" ", "enter", "enter", "enter"])
        assert answers[0].selected_options == ["Alpha 0"]
        assert answers[1].selected_options == ["Alpha 1"]

    def test_vim_navigation(self):
        (answers, _, _), _ = drive(make_questions(1), ["j", "enter", "enter"])
        assert answers[0].selected_options == ["Beta 0"]

    def test_jump_to_last_option(self):
        # G jumps past the regular options to "Other"; g jumps back to first.
        (answers, _, _), _ = drive(make_questions(1), ["G", "g", "enter", "enter"])
        assert answers[0].selected_options == ["Alpha 0"]


class TestMultiSelect:
    def test_space_toggles_and_enter_confirms(self):
        (answers, _, _), _ = drive(
            make_questions(1, multi=True), [" ", "down", " ", "ctrl-s"]
        )
        assert answers[0].selected_options == ["Alpha 0", "Beta 0"]

    def test_select_all_and_none(self):
        (answers, _, _), _ = drive(
            make_questions(1, multi=True), ["a", "n", " ", "ctrl-s"]
        )
        assert answers[0].selected_options == ["Alpha 0"]


class TestMultiQuestion:
    def test_left_right_switch_questions(self):
        (answers, _, _), _ = drive(
            make_questions(2), ["right", "enter", "left", "enter", "enter", "enter"]
        )
        # Q1 answered via right-then-enter... enter on Q0 advances back to Q1.
        assert answers[0].selected_options == ["Alpha 0"]
        assert answers[1].selected_options == ["Alpha 1"]

    def test_ctrl_s_submits_partial(self):
        (answers, cancelled, _), _ = drive(make_questions(2), ["enter", "ctrl-s"])
        assert not cancelled
        assert answers[0].selected_options == ["Alpha 0"]
        assert answers[1].selected_options == []


class TestOtherOption:
    def test_type_other_text(self):
        # Enter commits the text; Ctrl+S submits (Enter on Other re-edits).
        keys = ["G", "enter", "d", "o", "g", "enter", "ctrl-s"]
        (answers, _, _), _ = drive(make_questions(1), keys)
        assert answers[0].selected_options == ["Other"]
        assert answers[0].other_text == "dog"

    def test_backspace_edits_buffer(self):
        keys = ["G", "enter", "d", "x", "backspace", "o", "g", "enter", "ctrl-s"]
        (answers, _, _), _ = drive(make_questions(1), keys)
        assert answers[0].other_text == "dog"

    def test_escape_cancels_text_entry_only(self):
        keys = ["G", "enter", "d", "escape", "g", "enter", "enter"]
        (answers, cancelled, _), _ = drive(make_questions(1), keys)
        assert not cancelled
        assert answers[0].selected_options == ["Alpha 0"]
        assert answers[0].other_text is None

    def test_ctrl_s_commits_text_and_submits(self):
        keys = ["G", "enter", "c", "a", "t", "ctrl-s"]
        (answers, _, _), _ = drive(make_questions(1), keys)
        assert answers[0].other_text == "cat"

    def test_empty_other_text_not_saved(self):
        keys = ["G", "enter", "enter", "g", "enter", "enter"]
        (answers, _, _), _ = drive(make_questions(1), keys)
        assert answers[0].other_text is None


class TestCancellation:
    def test_escape_cancels(self):
        (answers, cancelled, timed_out), _ = drive(make_questions(1), ["escape"])
        assert cancelled and not timed_out and answers == []

    def test_ctrl_c_cancels(self):
        (_, cancelled, _), _ = drive(make_questions(1), ["ctrl-c"])
        assert cancelled

    def test_ctrl_c_cancels_during_text_entry(self):
        (_, cancelled, _), _ = drive(make_questions(1), ["G", "enter", "ctrl-c"])
        assert cancelled


class TestTimeout:
    def test_poll_tick_after_timeout_returns_timed_out(self):
        (answers, cancelled, timed_out), _ = drive(
            make_questions(1), [""], timeout_seconds=0
        )
        assert timed_out and not cancelled and answers == []

    def test_activity_resets_timer(self):
        state = QuestionUIState(make_questions(1))
        state.timeout_seconds = 300
        state.last_activity_time -= 400  # would be timed out
        script = iter(["enter", "enter"])
        tui = QuestionTUI(
            state,
            key_source=lambda: next(script),
            output=StringIO(),
            size=lambda: (100, 30),
            use_alt_screen=False,
        )
        answers, cancelled, timed_out = tui.run()
        # First key resets the timer before the next poll tick checks it.
        assert not timed_out and answers[0].selected_options == ["Alpha 0"]


class TestHelpOverlay:
    def test_question_mark_shows_help_any_key_closes(self):
        (answers, _, _), out = drive(make_questions(1), ["?", "x", "enter", "enter"])
        assert "KEYBOARD SHORTCUTS" in out
        assert answers[0].selected_options == ["Alpha 0"]


class TestPainting:
    def test_paint_shows_headers_and_options(self):
        _, out = drive(make_questions(2), ["escape"])
        plain = strip_ansi(out)
        assert "Questions" in plain  # left panel title
        assert "Q0" in plain and "Q1" in plain
        assert "Alpha 0" in plain

    def test_resize_repaints(self):
        # paint(1) + equal tick + differing tick -> paint(2) + escape
        sizes = iter([(100, 30), (100, 30), (60, 20), (60, 20)])
        state = QuestionUIState(make_questions(1))
        script = iter(["", "", "escape"])
        out = StringIO()
        tui = QuestionTUI(
            state,
            key_source=lambda: next(script),
            output=out,
            size=lambda: next(sizes),
            use_alt_screen=False,
        )
        tui.run()
        # Two paints: initial + resize-triggered.
        assert out.getvalue().count("\x1b[2J") >= 2

    def test_every_line_fits_width(self):
        from termflow.ansi.utils import visible_length

        _, out = drive(make_questions(3, multi=True), ["?", "x", " ", "escape"])
        for frame in out.split("\x1b[2J\x1b[H"):
            for line in frame.split("\r\n"):
                assert visible_length(line) <= 100


class TestAsyncEntry:
    def test_run_question_tui_seam(self, monkeypatch):
        import asyncio

        from code_puppy.tools.ask_user_question import tui_loop

        class FakeTUI:
            def __init__(self, state, **kwargs):
                pass

            def run(self):
                return ([], True, False)

        monkeypatch.setattr(tui_loop, "QuestionTUI", FakeTUI)
        state = QuestionUIState(make_questions(1))
        answers, cancelled, timed_out = asyncio.run(run_question_tui(state))
        assert cancelled and not timed_out
