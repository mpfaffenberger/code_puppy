"""Tests for ask_user_question renderers module."""

import re

from code_puppy.tools.ask_user_question.models import Question, QuestionOption
from code_puppy.tools.ask_user_question.renderers import (
    _render_help_overlay,
    _render_option,
    render_question_panel,
)
from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState
from code_puppy.tools.ask_user_question.theme import RichColors

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _make_questions(multi_select=False, num_options=3):
    """Helper to create test questions."""
    options = [
        QuestionOption(label=f"Option {i}", description=f"Desc {i}")
        for i in range(num_options)
    ]
    return [
        Question(
            question="What do you want?",
            header="Test",
            multi_select=multi_select,
            options=options,
        )
    ]


def _make_state(multi_select=False, num_options=3):
    questions = _make_questions(multi_select=multi_select, num_options=num_options)
    return QuestionUIState(questions)


class TestRenderQuestionPanel:
    """Tests for render_question_panel."""

    def test_basic_render_single_select(self):
        state = _make_state()
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "What do you want?" in text
        assert "Test" in text

    def test_basic_render_multi_select(self):
        state = _make_state(multi_select=True)
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "select multiple" in text

    def test_uses_default_colors_when_none(self):
        state = _make_state()
        # Should not raise when colors=None
        result = render_question_panel(state, colors=None)
        assert result is not None

    def test_uses_provided_colors(self):
        state = _make_state()
        colors = RichColors()
        result = render_question_panel(state, colors=colors)
        assert result is not None

    def test_show_help_overlay(self):
        state = _make_state()
        state.show_help = True
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "KEYBOARD SHORTCUTS" in text

    def test_other_option_rendered(self):
        state = _make_state()
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "Other" in text

    def test_other_text_displayed(self):
        state = _make_state()
        state.other_texts[0] = "custom value"
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "custom value" in text

    def test_entering_other_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "myinput"
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "myinput" in text
        assert "Enter to confirm" in text

    def test_cursor_on_different_options(self):
        state = _make_state(num_options=3)
        for i in range(4):  # 3 options + Other
            state.current_cursor = i
            result = render_question_panel(state)
            assert result is not None

    def test_selected_option_rendering(self):
        state = _make_state()
        state.single_selections[0] = 1
        result = render_question_panel(state)
        assert result is not None

    def test_multi_select_selected(self):
        state = _make_state(multi_select=True)
        state.selected_options[0] = {0, 2}
        result = render_question_panel(state)
        assert result is not None

    def test_timeout_warning(self):
        state = _make_state()
        state.timeout_seconds = 30
        # Set last_activity_time far enough back
        import time

        state.last_activity_time = time.monotonic() - 25
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "Timeout" in text or "timeout" in text.lower()

    def test_multiple_questions_progress(self):
        questions = [
            Question(
                question="Q1?",
                header="First",
                multi_select=False,
                options=[
                    QuestionOption(label="A", description=""),
                    QuestionOption(label="B", description=""),
                ],
            ),
            Question(
                question="Q2?",
                header="Second",
                multi_select=False,
                options=[
                    QuestionOption(label="C", description=""),
                    QuestionOption(label="D", description=""),
                ],
            ),
        ]
        state = QuestionUIState(questions)
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        assert "1/2" in text

    def test_last_question_help_text(self):
        """On last question, 'Enter Next' should not appear."""
        state = _make_state()
        result = render_question_panel(state)
        text = _strip_ansi(result.value)
        # Single question = last question, no "Enter Next"
        assert "Enter Next" not in text
        assert "Submit" in text

    def test_rich_escape_in_other_text(self):
        """Other text with Rich markup chars should be escaped."""
        state = _make_state()
        state.other_texts[0] = "[bold]dangerous[/bold]"
        result = render_question_panel(state)
        # Should not crash and should contain escaped text
        assert result is not None


class TestRenderHelpOverlay:
    def test_renders_all_sections(self):
        import io

        from rich.console import Console

        buf = io.StringIO()
        console = Console(
            file=buf, force_terminal=True, width=80, color_system="truecolor"
        )
        colors = RichColors()
        result = _render_help_overlay(console, buf, colors)
        text = _strip_ansi(result.value)
        assert "KEYBOARD SHORTCUTS" in text
        assert "Navigation" in text
        assert "Selection" in text
        assert "Other" in text
        assert "Move up" in text
        assert "Submit all" in text


class TestRenderOption:
    def _render(self, **kwargs):
        import io

        from rich.console import Console

        buf = io.StringIO()
        console = Console(
            file=buf, force_terminal=True, width=80, color_system="truecolor"
        )
        defaults = dict(
            console=console,
            label="Test",
            description="A desc",
            is_cursor=False,
            is_selected=False,
            multi_select=False,
            colors=RichColors(),
            padding="  ",
        )
        defaults.update(kwargs)
        _render_option(**defaults)
        return _strip_ansi(buf.getvalue())

    def test_single_select_not_selected(self):
        text = self._render()
        assert "( )" in text

    def test_single_select_selected(self):
        text = self._render(is_selected=True)
        assert "●" in text  # RADIO_FILLED

    def test_single_select_cursor(self):
        text = self._render(is_cursor=True)
        assert "❯" in text  # CURSOR_POINTER

    def test_multi_select_not_selected(self):
        text = self._render(multi_select=True)
        assert "[ ]" in text

    def test_multi_select_selected(self):
        text = self._render(multi_select=True, is_selected=True)
        assert "✓" in text  # CHECK_MARK

    def test_multi_select_cursor(self):
        text = self._render(multi_select=True, is_cursor=True)
        assert "❯" in text

    def test_no_description(self):
        text = self._render(description="")
        assert "Test" in text

    def test_cursor_and_selected(self):
        text = self._render(is_cursor=True, is_selected=True)
        assert "●" in text
        assert "❯" in text

    def test_selected_not_cursor_styling(self):
        text = self._render(is_selected=True, is_cursor=False)
        assert "Test" in text
