"""Tests for code_puppy/command_line/onboarding_wizard.py"""

import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

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

    @patch(f"{MODULE}.has_completed_onboarding", return_value=False)
    def test_returns_false_when_env_skip_1(self, mock_completed):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        with patch.dict(os.environ, {"CODE_PUPPY_SKIP_TUTORIAL": "1"}):
            assert should_show_onboarding() is False

    @patch(f"{MODULE}.has_completed_onboarding", return_value=False)
    def test_returns_false_when_env_skip_true(self, mock_completed):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        with patch.dict(os.environ, {"CODE_PUPPY_SKIP_TUTORIAL": "true"}):
            assert should_show_onboarding() is False

    @patch(f"{MODULE}.has_completed_onboarding", return_value=False)
    def test_returns_false_when_env_skip_yes(self, mock_completed):
        from code_puppy.command_line.onboarding_wizard import should_show_onboarding

        with patch.dict(os.environ, {"CODE_PUPPY_SKIP_TUTORIAL": "yes"}):
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

    def test_get_slide_content_slide_0(self):
        w = self._make_wizard()
        w.current_slide = 0
        content = w.get_slide_content()
        assert isinstance(content, str)

    def test_get_slide_content_slide_1(self):
        w = self._make_wizard()
        w.current_slide = 1
        content = w.get_slide_content()
        assert isinstance(content, str)

    def test_get_slide_content_slide_2(self):
        w = self._make_wizard()
        w.current_slide = 2
        content = w.get_slide_content()
        assert isinstance(content, str)

    def test_get_slide_content_slide_3(self):
        w = self._make_wizard()
        w.current_slide = 3
        content = w.get_slide_content()
        assert isinstance(content, str)

    def test_get_slide_content_slide_4(self):
        w = self._make_wizard()
        w.current_slide = 4
        content = w.get_slide_content()
        assert isinstance(content, str)

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
# _get_slide_panel_content
# ---------------------------------------------------------------------------


class TestGetSlidePanelContent:
    def test_returns_ansi(self):
        from prompt_toolkit.formatted_text import ANSI

        from code_puppy.command_line.onboarding_wizard import (
            OnboardingWizard,
            _get_slide_panel_content,
        )

        w = OnboardingWizard()
        result = _get_slide_panel_content(w)
        assert isinstance(result, ANSI)


# ---------------------------------------------------------------------------
# run_onboarding_wizard
# ---------------------------------------------------------------------------


class TestRunOnboardingWizardKeyBindings:
    """Test inner key-binding handlers by intercepting KeyBindings."""

    def _capture_kb(self):
        import asyncio

        from code_puppy.command_line.onboarding_wizard import (
            OnboardingWizard,
            run_onboarding_wizard,
        )

        captured = {}
        wizard = OnboardingWizard()

        with (
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch(f"{MODULE}.sys") as mock_sys,
            patch(f"{MODULE}.asyncio") as mock_asyncio,
            patch("code_puppy.messaging.emit_info"),
            patch(f"{MODULE}.mark_onboarding_complete"),
            patch(f"{MODULE}.Application") as MockApp,
            patch(f"{MODULE}.OnboardingWizard", return_value=wizard),
            patch(f"{MODULE}.KeyBindings") as MockKB,
        ):
            mock_sys.stdout = MagicMock()
            # Use real KeyBindings
            from prompt_toolkit.key_binding import KeyBindings as RealKB

            real_kb = RealKB()
            MockKB.return_value = real_kb

            app_instance = MagicMock()

            async def fake_run():
                wizard.result = "skipped"

            app_instance.run_async = fake_run
            MockApp.return_value = app_instance

            mock_asyncio.sleep = AsyncMock()

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run_onboarding_wizard())
            finally:
                loop.close()

            captured["kb"] = real_kb
            captured["wizard"] = wizard
            captured["app"] = app_instance

        return captured

    def _find_handler(self, kb, key_name):
        alias_map = {"tab": "c-i", "enter": "c-m"}
        search = alias_map.get(key_name, key_name)
        for binding in kb.bindings:
            keys = [k.value if hasattr(k, "value") else str(k) for k in binding.keys]
            if search in keys:
                return binding.handler
        return None

    def test_right_next_slide(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "right")
        assert handler is not None
        event = MagicMock()
        c["wizard"].current_slide = 0
        c["wizard"].result = None
        handler(event)
        assert c["wizard"].current_slide == 1

    def test_right_last_slide_completes(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "right")
        event = MagicMock()
        c["wizard"].current_slide = c["wizard"].TOTAL_SLIDES - 1
        handler(event)
        assert c["wizard"].result == "completed"
        event.app.exit.assert_called()

    def test_left_prev_slide(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "left")
        event = MagicMock()
        c["wizard"].current_slide = 2
        handler(event)
        assert c["wizard"].current_slide == 1

    def test_down_next_option(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "down")
        event = MagicMock()
        c["wizard"].current_slide = 1
        c["wizard"].selected_option = 0
        handler(event)
        assert c["wizard"].selected_option == 1

    def test_up_prev_option(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "up")
        event = MagicMock()
        c["wizard"].current_slide = 1
        c["wizard"].selected_option = 1
        handler(event)
        assert c["wizard"].selected_option == 0

    def test_enter_select_and_next(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "enter")
        event = MagicMock()
        c["wizard"].current_slide = 1
        c["wizard"].selected_option = 0
        handler(event)
        assert c["wizard"].current_slide == 2

    def test_enter_on_last_slide(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "enter")
        event = MagicMock()
        c["wizard"].current_slide = c["wizard"].TOTAL_SLIDES - 1
        handler(event)
        assert c["wizard"].result == "completed"
        event.app.exit.assert_called()

    def test_escape_skips(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "escape")
        event = MagicMock()
        handler(event)
        assert c["wizard"].result == "skipped"
        event.app.exit.assert_called()

    def test_ctrl_c_skips(self):
        c = self._capture_kb()
        handler = self._find_handler(c["kb"], "c-c")
        event = MagicMock()
        handler(event)
        assert c["wizard"].result == "skipped"


class TestRunOnboardingWizard:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.Application")
    async def test_skipped(self, MockApp, mock_sys, mock_set, mock_emit, mock_mark):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()

        async def fake_run_async():
            pass

        app_instance.run_async = fake_run_async
        MockApp.return_value = app_instance

        with patch(f"{MODULE}.OnboardingWizard") as MockWizard:
            wizard = MagicMock()
            wizard.TOTAL_SLIDES = 5
            wizard.result = "skipped"
            wizard._should_exit = True
            wizard.trigger_oauth = None
            MockWizard.return_value = wizard

            result = await run_onboarding_wizard()
            assert result == "skipped"
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.Application")
    async def test_completed(self, MockApp, mock_sys, mock_set, mock_emit, mock_mark):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()

        async def fake_run_async():
            pass

        app_instance.run_async = fake_run_async
        MockApp.return_value = app_instance

        with patch(f"{MODULE}.OnboardingWizard") as MockWizard:
            wizard = MagicMock()
            wizard.TOTAL_SLIDES = 5
            wizard.result = "completed"
            wizard._should_exit = True
            wizard.trigger_oauth = None
            MockWizard.return_value = wizard

            result = await run_onboarding_wizard()
            assert result == "completed"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.mark_onboarding_complete")
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.Application")
    async def test_trigger_oauth(
        self, MockApp, mock_sys, mock_set, mock_emit, mock_mark
    ):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()

        async def fake_run_async():
            pass

        app_instance.run_async = fake_run_async
        MockApp.return_value = app_instance

        with patch(f"{MODULE}.OnboardingWizard") as MockWizard:
            wizard = MagicMock()
            wizard.TOTAL_SLIDES = 5
            wizard.result = "completed"
            wizard._should_exit = True
            wizard.trigger_oauth = "chatgpt"
            MockWizard.return_value = wizard

            result = await run_onboarding_wizard()
            assert result == "chatgpt"

    @pytest.mark.asyncio
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.Application")
    async def test_keyboard_interrupt(self, MockApp, mock_sys, mock_set, mock_emit):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()
        app_instance.run_async = AsyncMock(side_effect=KeyboardInterrupt)
        MockApp.return_value = app_instance

        with patch(f"{MODULE}.mark_onboarding_complete"):
            result = await run_onboarding_wizard()
            assert result == "skipped"

    @pytest.mark.asyncio
    @patch("code_puppy.messaging.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.Application")
    async def test_exception(self, MockApp, mock_sys, mock_set, mock_emit):
        from code_puppy.command_line.onboarding_wizard import run_onboarding_wizard

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()
        app_instance.run_async = AsyncMock(side_effect=RuntimeError("boom"))
        MockApp.return_value = app_instance

        result = await run_onboarding_wizard()
        # result is None on generic exception
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
