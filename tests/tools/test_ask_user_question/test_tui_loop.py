"""Tests for ask_user_question tui_loop module."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.ask_user_question.models import Question, QuestionOption
from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState
from code_puppy.tools.ask_user_question.tui_loop import TUIResult, run_question_tui


def _make_questions(multi_select=False, count=1):
    options = [
        QuestionOption(label="Alpha", description="First"),
        QuestionOption(label="Beta", description="Second"),
    ]
    return [
        Question(
            question=f"Q{i}?",
            header=f"H{i}",
            multi_select=multi_select,
            options=options,
        )
        for i in range(count)
    ]


def _make_state(multi_select=False, count=1):
    return QuestionUIState(_make_questions(multi_select=multi_select, count=count))


# Map friendly names to prompt_toolkit internal key representations
_KEY_ALIASES = {
    "enter": "c-m",
    "backspace": "c-h",
}


def _find_handler(kb, key_name):
    """Find a handler in KeyBindings by key name."""
    target = _KEY_ALIASES.get(key_name, key_name)
    for b in kb.bindings:
        for k in b.keys:
            val = k.value if hasattr(k, "value") else k
            if val == target:
                return b.handler
    return None


def _make_event(exit_called=None):
    """Create a mock KeyPressEvent."""
    event = MagicMock()
    event.app = MagicMock()
    if exit_called is not None:
        event.app.exit = exit_called
    return event


async def _run_with_handler_callback(state, callback):
    """Run TUI, capturing kb and calling callback during run_async to get coverage."""
    captured_kb = None

    with (
        patch("code_puppy.tools.ask_user_question.tui_loop.Application") as MockApp,
        patch("code_puppy.tools.ask_user_question.tui_loop.create_output"),
        patch("sys.__stdout__", new=MagicMock()),
    ):

        def capture_app(**kwargs):
            nonlocal captured_kb
            captured_kb = kwargs.get("key_bindings")
            mock = MagicMock()

            async def run_and_invoke():
                if captured_kb and callback:
                    callback(captured_kb, mock)

            mock.run_async = run_and_invoke
            return mock

        MockApp.side_effect = capture_app
        result = await run_question_tui(state)

    return result, captured_kb


class TestTUIResult:
    def test_defaults(self):
        r = TUIResult()
        assert r.cancelled is False
        assert r.confirmed is False

    def test_set_values(self):
        r = TUIResult(cancelled=True, confirmed=True)
        assert r.cancelled is True
        assert r.confirmed is True


class TestRunQuestionTUI:
    @pytest.mark.asyncio
    async def test_default_returns_answers(self):
        state = _make_state()
        state.single_selections[0] = 0
        result, _ = await _run_with_handler_callback(state, None)
        answers, cancelled, timed_out = result
        assert not cancelled
        assert not timed_out
        assert len(answers) == 1

    @pytest.mark.asyncio
    async def test_timeout_returns_timed_out(self):
        state = _make_state()
        state.timeout_seconds = 0
        state.last_activity_time = time.monotonic() - 1000

        with (
            patch("code_puppy.tools.ask_user_question.tui_loop.Application") as MockApp,
            patch("code_puppy.tools.ask_user_question.tui_loop.create_output"),
            patch("sys.__stdout__", new=MagicMock()),
        ):
            app_inst = MagicMock()

            async def fake_run():
                await asyncio.sleep(2)

            app_inst.run_async = fake_run
            app_inst.exit = MagicMock()
            app_inst.invalidate = MagicMock()
            MockApp.return_value = app_inst

            answers, cancelled, timed_out = await run_question_tui(state)
            assert timed_out is True
            assert answers == []

    @pytest.mark.asyncio
    async def test_exception_reraised(self):
        state = _make_state()
        with (
            patch("code_puppy.tools.ask_user_question.tui_loop.Application") as MockApp,
            patch("code_puppy.tools.ask_user_question.tui_loop.create_output"),
            patch("sys.__stdout__", new=MagicMock()),
        ):
            MockApp.return_value.run_async = AsyncMock(side_effect=RuntimeError("boom"))
            with pytest.raises(RuntimeError, match="boom"):
                await run_question_tui(state)

    @pytest.mark.asyncio
    async def test_cancelled_via_escape(self):
        state = _make_state()

        def press_escape(kb, app):
            handler = _find_handler(kb, "escape")
            event = _make_event()
            event.app = app
            handler(event)

        result, _ = await _run_with_handler_callback(state, press_escape)
        answers, cancelled, timed_out = result
        assert cancelled is True
        assert answers == []

    @pytest.mark.asyncio
    async def test_ctrl_c_cancels(self):
        state = _make_state()

        def press_ctrl_c(kb, app):
            handler = _find_handler(kb, "c-c")
            event = _make_event()
            event.app = app
            handler(event)

        result, _ = await _run_with_handler_callback(state, press_ctrl_c)
        answers, cancelled, timed_out = result
        assert cancelled is True

    @pytest.mark.asyncio
    async def test_confirmed_via_ctrl_s(self):
        state = _make_state()
        state.single_selections[0] = 0

        def press_ctrl_s(kb, app):
            handler = _find_handler(kb, "c-s")
            event = _make_event()
            event.app = app
            handler(event)

        result, _ = await _run_with_handler_callback(state, press_ctrl_s)
        answers, cancelled, timed_out = result
        assert not cancelled
        assert len(answers) == 1


class TestKeyHandlers:
    """Test all keyboard handlers by invoking them during run_async."""

    @pytest.mark.asyncio
    async def test_arrow_up_moves_cursor(self):
        state = _make_state()
        state.cursor_positions[0] = 1

        def action(kb, app):
            h = _find_handler(kb, "up")
            e = _make_event()

            e.app = app
            h(e)
            # Exit cleanly
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.cursor_positions[0] == 0

    @pytest.mark.asyncio
    async def test_arrow_down_moves_cursor(self):
        state = _make_state()

        def action(kb, app):
            h = _find_handler(kb, "down")
            e = _make_event()

            e.app = app
            h(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.cursor_positions[0] == 1

    @pytest.mark.asyncio
    async def test_arrow_left_right_switch_questions(self):
        state = _make_state(count=2)

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "right")(e)
            assert state.current_question_index == 1
            _find_handler(kb, "left")(e)
            assert state.current_question_index == 0
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_arrow_keys_ignored_in_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.cursor_positions[0] = 1

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "up")(e)
            _find_handler(kb, "escape")(e)  # exit text mode
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.cursor_positions[0] == 1  # unchanged

    @pytest.mark.asyncio
    async def test_vim_j_navigates_in_normal_mode(self):
        state = _make_state()

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "j")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.cursor_positions[0] == 1

    @pytest.mark.asyncio
    async def test_vim_k_navigates_in_normal_mode(self):
        state = _make_state()
        state.cursor_positions[0] = 1

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "k")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.cursor_positions[0] == 0

    @pytest.mark.asyncio
    async def test_vim_keys_type_in_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = ""

        def action(kb, app):
            e = _make_event()

            e.app = app
            for key in ["j", "k", "h", "l", "g", "G", "a", "n", "?"]:
                _find_handler(kb, key)(e)
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_space_toggles_multi_select(self):
        state = _make_state(multi_select=True)

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = " "
            _find_handler(kb, " ")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert 0 in state.selected_options[0]

    @pytest.mark.asyncio
    async def test_space_selects_single_select(self):
        state = _make_state(multi_select=False)
        state.cursor_positions[0] = 1

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = " "
            _find_handler(kb, " ")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)
        assert state.single_selections[0] == 1

    @pytest.mark.asyncio
    async def test_space_in_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "hi"

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = " "
            _find_handler(kb, " ")(e)
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_space_on_other_option(self):
        state = _make_state()
        state.cursor_positions[0] = len(state.questions[0].options)  # Other

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = " "
            _find_handler(kb, " ")(e)
            assert state.entering_other_text is True
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_enter_advances_question(self):
        state = _make_state(count=2)

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "enter")(e)
            assert state.current_question_index == 1
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_enter_on_last_question_confirms(self):
        state = _make_state(count=1)
        state.single_selections[0] = 0
        state.cursor_positions[0] = 0

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "enter")(e)

        result, _ = await _run_with_handler_callback(state, action)
        answers, cancelled, timed_out = result
        assert not cancelled

    @pytest.mark.asyncio
    async def test_enter_last_question_new_selection(self):
        state = _make_state(count=1)
        state.cursor_positions[0] = 1
        state.single_selections[0] = 0  # different

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "enter")(e)
            # Should NOT exit, just invalidate
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_enter_in_other_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "custom"

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "enter")(e)
            assert state.entering_other_text is False
            assert state.other_texts[0] == "custom"
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_enter_on_other_option(self):
        state = _make_state()
        state.cursor_positions[0] = len(state.questions[0].options)

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "enter")(e)
            assert state.entering_other_text is True
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_ctrl_s_saves_other_text_first(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "my text"

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "c-s")(e)

        result, _ = await _run_with_handler_callback(state, action)
        assert state.other_texts[0] == "my text"

    @pytest.mark.asyncio
    async def test_escape_exits_text_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "typing"

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "escape")(e)
            assert state.entering_other_text is False
            assert state.other_text_buffer == ""
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_text_input_in_other_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = ""

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = "x"
            _find_handler(kb, "<any>")(e)
            assert "x" in state.other_text_buffer
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_text_input_ignores_control_chars(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = ""

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = "\x01"
            _find_handler(kb, "<any>")(e)
            assert state.other_text_buffer == ""
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_text_input_not_in_other_mode(self):
        """<any> handler does nothing when not in text mode."""
        state = _make_state()

        def action(kb, app):
            e = _make_event()

            e.app = app

            e.data = "x"
            _find_handler(kb, "<any>")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_backspace_in_other_mode(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = "ab"

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "backspace")(e)
            assert state.other_text_buffer == "a"
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_backspace_empty_buffer(self):
        state = _make_state()
        state.entering_other_text = True
        state.other_text_buffer = ""

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "backspace")(e)
            _find_handler(kb, "escape")(e)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_backspace_not_in_other_mode(self):
        state = _make_state()

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "backspace")(e)  # should do nothing
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_question_mark_toggles_help(self):
        state = _make_state()

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "?")(e)
            assert state.show_help is True
            _find_handler(kb, "?")(e)
            assert state.show_help is False
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_select_all_and_none(self):
        state = _make_state(multi_select=True)

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "a")(e)
            assert len(state.selected_options[0]) == 2
            _find_handler(kb, "n")(e)
            assert len(state.selected_options[0]) == 0
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)

    @pytest.mark.asyncio
    async def test_g_and_G_jump(self):
        state = _make_state()
        state.cursor_positions[0] = 1

        def action(kb, app):
            e = _make_event()

            e.app = app
            _find_handler(kb, "g")(e)
            assert state.cursor_positions[0] == 0
            _find_handler(kb, "G")(e)
            # last option (including Other)
            _find_handler(kb, "c-c")(e)

        await _run_with_handler_callback(state, action)


class TestPanelRendering:
    """Test left/right panel rendering functions."""

    @pytest.mark.asyncio
    async def test_panel_lambdas_callable(self):
        state = _make_state(count=2)
        state.single_selections[0] = 0  # answered

        captured_lambdas = []

        with (
            patch("code_puppy.tools.ask_user_question.tui_loop.Application") as MockApp,
            patch("code_puppy.tools.ask_user_question.tui_loop.create_output"),
            patch("sys.__stdout__", new=MagicMock()),
        ):

            class CaptureFTC:
                def __init__(self, fn):
                    captured_lambdas.append(fn)

            with (
                patch(
                    "code_puppy.tools.ask_user_question.tui_loop.FormattedTextControl",
                    CaptureFTC,
                ),
                patch(
                    "code_puppy.tools.ask_user_question.tui_loop.Window",
                    return_value=MagicMock(),
                ),
                patch(
                    "code_puppy.tools.ask_user_question.tui_loop.VSplit",
                    return_value=MagicMock(),
                ),
                patch(
                    "code_puppy.tools.ask_user_question.tui_loop.Frame",
                    return_value=MagicMock(),
                ),
                patch("code_puppy.tools.ask_user_question.tui_loop.Layout"),
            ):
                MockApp.side_effect = lambda **kw: MagicMock(run_async=AsyncMock())
                await run_question_tui(state)

        assert len(captured_lambdas) >= 2
        left = captured_lambdas[0]()
        right = captured_lambdas[1]()
        assert left is not None
        assert right is not None
