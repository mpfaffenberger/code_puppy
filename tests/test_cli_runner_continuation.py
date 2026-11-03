"""Coverage for interactive_runner.py::interactive_mode() continuation,
cancellation, and onboarding-after-continuation branches.

Split out of test_cli_runner_full_coverage.py; shared helpers live in
``tests/cli_runner_fixtures.py``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.cli_runner_fixtures import (
    _interactive_patches,
    _mock_clipboard,
    _mock_parse_result,
    _mock_renderer,
    _run_interactive,
    _scripted_input,
)


class TestInteractiveMode:
    """Test interactive_mode() continuation/cancellation branches."""

    @pytest.mark.anyio
    async def test_continuation_loop(self):
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        mock_run = AsyncMock(return_value=(mock_result, MagicMock()))
        mock_turn_end = AsyncMock(
            side_effect=[[{"prompt": "repeat", "clear_context": True}], []]
        )

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": mock_run,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.callbacks.on_interactive_turn_end": mock_turn_end,
            },
        )
        assert mock_run.await_count == 2

    @pytest.mark.anyio
    async def test_continuation_loop_cancelled(self):
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            return (None, MagicMock())

        mock_cancel = AsyncMock()
        mock_turn_end = AsyncMock(
            side_effect=[[{"prompt": "repeat", "clear_context": True}], []]
        )

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.callbacks.on_interactive_turn_end": mock_turn_end,
                "code_puppy.callbacks.on_interactive_turn_cancel": mock_cancel,
            },
        )
        mock_cancel.assert_awaited()

    @pytest.mark.anyio
    async def test_continuation_loop_keyboard_interrupt_autosaves(self):
        """A Ctrl+C during a continuation-requested turn previously broke out
        of the loop with zero persistence attempt; it must now autosave
        before breaking, same as every other cancel path.

        The first turn's own post-turn save already calls
        ``_save_autosave_snapshot()`` once, so asserting ``called()`` alone
        would pass even without the fix. Assert the count instead: one call
        for the successful first turn, one for the interrupted continuation.
        """
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            raise KeyboardInterrupt()

        mock_autosave = MagicMock()
        mock_turn_end = AsyncMock(
            side_effect=[[{"prompt": "repeat", "clear_context": True}], []]
        )

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.callbacks.on_interactive_turn_end": mock_turn_end,
                "code_puppy.interactive_runner._save_autosave_snapshot": mock_autosave,
            },
        )
        assert mock_autosave.call_count == 2

    @pytest.mark.anyio
    async def test_continuation_no_request_stops(self):
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        mock_turn_end = AsyncMock(return_value=[])
        mock_run = AsyncMock(return_value=(mock_result, MagicMock()))
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": mock_run,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.callbacks.on_interactive_turn_end": mock_turn_end,
            },
        )
        mock_turn_end.assert_called()
        assert mock_run.await_count == 1

    @pytest.mark.anyio
    async def test_continuation_loop_exception_is_reported_to_plugins(self):
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            raise RuntimeError("wiggum fail")

        mock_turn_end = AsyncMock(
            side_effect=[[{"prompt": "repeat", "clear_context": True}], []]
        )

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.callbacks.on_interactive_turn_end": mock_turn_end,
            },
        )
        assert mock_turn_end.call_count >= 2

    @pytest.mark.anyio
    async def test_onboarding_chatgpt(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(return_value=True)
        )

        mock_future = MagicMock()
        mock_future.result.return_value = "chatgpt"
        mock_pool = MagicMock()
        mock_pool.submit.return_value = mock_future
        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_pool)
        mock_executor.__exit__ = MagicMock(return_value=False)

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
            extra_patches={
                "concurrent.futures.ThreadPoolExecutor": MagicMock(
                    return_value=mock_executor
                ),
                "code_puppy.command_line.onboarding_wizard.run_onboarding_wizard": AsyncMock(
                    return_value="chatgpt"
                ),
                "code_puppy_core_plugins.chatgpt_oauth.oauth_flow.run_oauth_flow": MagicMock(),
                "code_puppy.config.set_model_name": MagicMock(),
            },
        )

    @pytest.mark.anyio
    async def test_onboarding_claude(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(return_value=True)
        )

        mock_future = MagicMock()
        mock_future.result.return_value = "claude"
        mock_pool = MagicMock()
        mock_pool.submit.return_value = mock_future
        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_pool)
        mock_executor.__exit__ = MagicMock(return_value=False)

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
            extra_patches={
                "concurrent.futures.ThreadPoolExecutor": MagicMock(
                    return_value=mock_executor
                ),
                "code_puppy_core_plugins.claude_code_oauth.register_callbacks._perform_authentication": MagicMock(),
                "code_puppy.config.set_model_name": MagicMock(),
            },
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize("onboarding_result", ["completed", "skipped"])
    async def test_onboarding_result(self, onboarding_result):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(return_value=True)
        )

        mock_future = MagicMock()
        mock_future.result.return_value = onboarding_result
        mock_pool = MagicMock()
        mock_pool.submit.return_value = mock_future
        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_pool)
        mock_executor.__exit__ = MagicMock(return_value=False)

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
            extra_patches={
                "concurrent.futures.ThreadPoolExecutor": MagicMock(
                    return_value=mock_executor
                ),
            },
        )

    @pytest.mark.anyio
    async def test_onboarding_exception(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(side_effect=RuntimeError("fail"))
        )

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
        )

    @pytest.mark.anyio
    async def test_clear_no_clipboard_images(self):
        """Test /clear when no clipboard images pending."""
        fake_input = _scripted_input("/clear")

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.prompt_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                # Same lazy-import targets as test_clear_command above.
                "code_puppy.command_line.clipboard.get_clipboard_manager": MagicMock(
                    return_value=_mock_clipboard()
                ),
                "code_puppy.config.finalize_autosave_session": MagicMock(
                    return_value="session-1"
                ),
            },
        )


# ---------------------------------------------------------------------------
# main_entry() additional tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Additional interactive_mode edge cases for remaining uncovered lines
# ---------------------------------------------------------------------------
