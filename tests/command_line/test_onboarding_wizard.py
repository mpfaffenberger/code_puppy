"""Tests for code_puppy/command_line/onboarding_wizard.py"""

import os
from unittest.mock import AsyncMock, mock_open, patch

import pytest

MODULE = "code_puppy.command_line.onboarding_wizard"


# ---------------------------------------------------------------------------
# State tracking functions
# ---------------------------------------------------------------------------


class TestHasCompletedOnboarding:
    @patch(f"{MODULE}.os.path.exists", return_value=True)
    def test_returns_true_when_file_exists(self, mock_exists):
        from code_puppy.command_line.onboarding_wizard import has_completed_onboarding

        assert has_completed_onboarding() is True

    @patch(f"{MODULE}.os.path.exists", return_value=False)
    def test_returns_false_when_file_missing(self, mock_exists):
        from code_puppy.command_line.onboarding_wizard import has_completed_onboarding

        assert has_completed_onboarding() is False


class TestMarkOnboardingComplete:
    @patch(f"{MODULE}.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_creates_file(self, m_open, m_makedirs):
        from code_puppy.command_line.onboarding_wizard import mark_onboarding_complete

        mark_onboarding_complete()
        m_makedirs.assert_called_once()
        m_open.assert_called_once()


class TestShouldShowOnboarding:
    @patch(f"{MODULE}.has_completed_onboarding", return_value=True)
    def test_returns_false_when_completed(self, mock_completed):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        assert should_show_onboarding() is False

    @patch(f"{MODULE}.has_completed_onboarding", return_value=False)
    def test_returns_true_when_not_completed(self, mock_completed):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        with patch.dict(os.environ, {}, clear=False):
            # Make sure skip env var is not set
            os.environ.pop("CODE_PUPPY_SKIP_TUTORIAL", None)
            assert should_show_onboarding() is True

    @pytest.mark.parametrize(
        "env_value", ["1", "true", "yes"], ids=["one", "true", "yes"]
    )
    @patch(f"{MODULE}.has_completed_onboarding", return_value=False)
    def test_returns_false_when_env_skip(self, mock_completed, env_value):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        with patch.dict(os.environ, {"CODE_PUPPY_SKIP_TUTORIAL": env_value}):
            assert should_show_onboarding() is False


class TestResetOnboarding:
    @patch(f"{MODULE}.os.path.exists", return_value=True)
    @patch(f"{MODULE}.os.remove")
    def test_removes_file(self, mock_remove, mock_exists):
        from code_puppy.command_line.onboarding_wizard import reset_onboarding

        reset_onboarding()
        mock_remove.assert_called_once()

    @patch(f"{MODULE}.os.path.exists", return_value=False)
    @patch(f"{MODULE}.os.remove")
    def test_no_op_when_missing(self, mock_remove, mock_exists):
        from code_puppy.command_line.onboarding_wizard import reset_onboarding

        reset_onboarding()
        mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# OnboardingWizard class
# ---------------------------------------------------------------------------


class TestOnboardingWizard:
    def _make_wizard(self):
        from code_puppy.command_line.onboarding_wizard import OnboardingWizard

        return OnboardingWizard()

    def test_init(self):
        w = self._make_wizard()
        assert w.current_slide == 0
        assert w.selected_option == 0
        assert w.trigger_oauth is None
        assert w.model_choice is None
        assert w.result is None
        assert w._should_exit is False

    def test_total_slides(self):
        w = self._make_wizard()
        assert w.TOTAL_SLIDES == 5

    def test_get_progress_indicator(self):
        w = self._make_wizard()
        progress = w.get_progress_indicator()
        assert "●" in progress
        assert progress.count("○") == 4

    @pytest.mark.parametrize(
        "slide",
        [0, 1, 2, 3, 4],
        ids=["slide_0", "slide_1", "slide_2", "slide_3", "slide_4"],
    )
    def test_get_slide_content(self, slide):
        w = self._make_wizard()
        w.current_slide = slide
        content = w.get_slide_content()
        assert isinstance(content, list)

    def test_get_options_for_slide_1(self):
        w = self._make_wizard()
        w.current_slide = 1
        opts = w.get_options_for_slide()
        assert len(opts) > 0

    def test_get_options_for_slide_0(self):
        w = self._make_wizard()
        w.current_slide = 0
        assert w.get_options_for_slide() == []

    def test_handle_option_select_chatgpt(self):
        w = self._make_wizard()
        w.current_slide = 1
        opts = w.get_options_for_slide()
        # Find chatgpt index
        chatgpt_idx = next(i for i, (id_, _) in enumerate(opts) if id_ == "chatgpt")
        w.selected_option = chatgpt_idx
        w.handle_option_select()
        assert w.trigger_oauth == "chatgpt"
        assert w.model_choice == "chatgpt"

    def test_handle_option_select_claude(self):
        w = self._make_wizard()
        w.current_slide = 1
        opts = w.get_options_for_slide()
        claude_idx = next(i for i, (id_, _) in enumerate(opts) if id_ == "claude")
        w.selected_option = claude_idx
        w.handle_option_select()
        assert w.trigger_oauth == "claude"

    def test_handle_option_select_api_keys(self):
        w = self._make_wizard()
        w.current_slide = 1
        opts = w.get_options_for_slide()
        idx = next(i for i, (id_, _) in enumerate(opts) if id_ == "api_keys")
        w.selected_option = idx
        w.handle_option_select()
        assert w.trigger_oauth is None
        assert w.model_choice == "api_keys"

    def test_handle_option_select_no_options(self):
        w = self._make_wizard()
        w.current_slide = 0  # no options
        w.handle_option_select()  # should not crash

    def test_next_slide(self):
        w = self._make_wizard()
        assert w.next_slide() is True
        assert w.current_slide == 1
        assert w.selected_option == 0

    def test_next_slide_at_end(self):
        w = self._make_wizard()
        w.current_slide = 4
        assert w.next_slide() is False

    def test_prev_slide(self):
        w = self._make_wizard()
        w.current_slide = 2
        assert w.prev_slide() is True
        assert w.current_slide == 1

    def test_prev_slide_at_start(self):
        w = self._make_wizard()
        assert w.prev_slide() is False

    def test_next_option(self):
        w = self._make_wizard()
        w.current_slide = 1
        w.selected_option = 0
        w.next_option()
        assert w.selected_option == 1

    def test_next_option_wraps(self):
        w = self._make_wizard()
        w.current_slide = 1
        opts = w.get_options_for_slide()
        w.selected_option = len(opts) - 1
        w.next_option()
        assert w.selected_option == 0

    def test_prev_option(self):
        w = self._make_wizard()
        w.current_slide = 1
        w.selected_option = 1
        w.prev_option()
        assert w.selected_option == 0

    def test_prev_option_wraps(self):
        w = self._make_wizard()
        w.current_slide = 1
        w.selected_option = 0
        w.prev_option()
        opts = w.get_options_for_slide()
        assert w.selected_option == len(opts) - 1

    def test_next_option_no_options(self):
        w = self._make_wizard()
        w.current_slide = 0
        w.next_option()  # should not crash

    def test_prev_option_no_options(self):
        w = self._make_wizard()
        w.current_slide = 0
        w.prev_option()  # should not crash


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


class TestGetSlidePanelContent:
    def test_returns_fragments_with_progress_header(self):
        from code_puppy.command_line.onboarding_wizard import (
            OnboardingWizard,
            _get_slide_panel_content,
        )

        w = OnboardingWizard()
        fragments = _get_slide_panel_content(w)
        assert isinstance(fragments, list)
        assert any("Slide 1 of 5" in text for _, text in fragments)


class TestFragmentsToLines:
    def test_splits_on_newlines_and_styles_fragments(self):
        from code_puppy.command_line.onboarding_wizard import _fragments_to_lines

        lines = _fragments_to_lines(
            [("class:tui.title", "Hello\nWorld"), ("class:tui.body", " plain")]
        )
        assert len(lines) == 2
        assert "Hello" in lines[0] and "\x1b[" in lines[0]  # styled
        assert lines[1].endswith(" plain")  # body is unstyled

    def test_unknown_class_renders_plain(self):
        from code_puppy.command_line.onboarding_wizard import _fragments_to_lines

        lines = _fragments_to_lines([("class:tui.whatever", "text")])
        assert lines == ["text"]


# ---------------------------------------------------------------------------
# OnboardingTUI (headless scripted drives)
# ---------------------------------------------------------------------------


def drive(keys, wizard=None):
    from io import StringIO

    from code_puppy.command_line.onboarding_wizard import (
        OnboardingTUI,
        OnboardingWizard,
    )

    wizard = wizard or OnboardingWizard()
    script = iter(keys)
    out = StringIO()
    OnboardingTUI(
        wizard,
        key_source=lambda: next(script),
        output=out,
        size=lambda: (90, 30),
        use_alt_screen=False,
    ).run()
    return wizard, out.getvalue()


class TestOnboardingTUI:
    def test_right_advances_and_completes_on_last(self):
        wizard, _ = drive(["right", "right", "right", "right", "right"])
        assert wizard.result == "completed"
        assert wizard.current_slide == 4

    def test_vim_keys_navigate_slides(self):
        wizard, _ = drive(["l", "l", "h", "escape"])
        assert wizard.current_slide == 1
        assert wizard.result == "skipped"

    def test_option_navigation_on_model_slide(self):
        wizard, _ = drive(["right", "j", "j", "k", "escape"])
        assert wizard.current_slide == 1
        assert wizard.selected_option == 1

    def test_enter_selects_oauth_option_and_advances(self):
        # Slide 1, option 0 is chatgpt.
        wizard, _ = drive(["right", "enter", "escape"])
        assert wizard.trigger_oauth == "chatgpt"
        assert wizard.model_choice == "chatgpt"
        assert wizard.current_slide == 2

    def test_enter_all_the_way_through_completes(self):
        wizard, _ = drive(["enter"] * 5)
        assert wizard.result == "completed"

    def test_escape_and_ctrl_c_skip(self):
        wizard, _ = drive(["escape"])
        assert wizard.result == "skipped"
        wizard, _ = drive(["ctrl-c"])
        assert wizard.result == "skipped"

    def test_paint_shows_title_and_progress(self):
        _, out = drive(["escape"])
        assert "Code Puppy Tutorial" in out
        assert "Slide 1 of 5" in out

    def test_every_line_fits_width(self):
        from termflow.ansi.utils import visible_length

        _, out = drive(["right", "j", "right", "escape"])
        for frame in out.split("\x1b[H"):
            for line in frame.split("\r\n"):
                cleaned = line.replace("\x1b[K", "").replace("\x1b[J", "")
                assert visible_length(cleaned) <= 90


# ---------------------------------------------------------------------------
# run_onboarding_wizard (entry point, TUI faked)
# ---------------------------------------------------------------------------


def _fake_tui(result, trigger_oauth=None, raises=None):
    class FakeTUI:
        def __init__(self, wizard, **kwargs):
            self._wizard = wizard

        def run(self):
            if raises is not None:
                raise raises
            self._wizard.result = result
            self._wizard.trigger_oauth = trigger_oauth

    return FakeTUI


class TestRunOnboardingWizard:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    async def test_skipped(self, mock_set, mock_emit, mock_mark):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        with patch(f"{MODULE}.OnboardingTUI", _fake_tui("skipped")):
            result = await run_onboarding_wizard()
        assert result == "skipped"
        mock_mark.assert_called_once()

    @pytest.mark.parametrize(
        ("trigger_oauth", "expected"),
        [(None, "completed"), ("chatgpt", "chatgpt")],
        ids=["completed", "trigger_oauth"],
    )
    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    async def test_run_wizard_completion(
        self, mock_set, mock_emit, mock_mark, trigger_oauth, expected
    ):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        with patch(f"{MODULE}.OnboardingTUI", _fake_tui("completed", trigger_oauth)):
            result = await run_onboarding_wizard()
        assert result == expected
        mock_mark.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    async def test_keyboard_interrupt(self, mock_set, mock_emit, mock_mark):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        with patch(
            f"{MODULE}.OnboardingTUI", _fake_tui(None, raises=KeyboardInterrupt())
        ):
            result = await run_onboarding_wizard()
        assert result == "skipped"

    @pytest.mark.asyncio
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    async def test_exception(self, mock_set, mock_emit):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        with patch(
            f"{MODULE}.OnboardingTUI", _fake_tui(None, raises=RuntimeError("boom"))
        ):
            result = await run_onboarding_wizard()
        assert result is None


# ---------------------------------------------------------------------------
# run_onboarding_if_needed
# ---------------------------------------------------------------------------


class TestRunOnboardingIfNeeded:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.should_show_onboarding", return_value=False)
    async def test_skips_if_not_needed(self, mock_should):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_if_needed

        result = await run_onboarding_if_needed()
        assert result is None

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.run_onboarding_wizard",
        new_callable=AsyncMock,
        return_value="completed",
    )
    @patch(f"{MODULE}.should_show_onboarding", return_value=True)
    async def test_runs_if_needed(self, mock_should, mock_run):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_if_needed

        result = await run_onboarding_if_needed()
        assert result == "completed"
        mock_run.assert_awaited_once()
