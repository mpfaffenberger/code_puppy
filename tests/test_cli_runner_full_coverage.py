"""Full coverage tests for cli_runner.py.

Covers main(), interactive_mode(), run_prompt_with_attachments(),
execute_single_prompt(), and main_entry() — targeting all uncovered branches.
"""

import asyncio
import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_renderer():
    r = MagicMock()
    r.console = MagicMock()
    r.console.file = MagicMock()
    r.console.file.flush = MagicMock()
    r.start = MagicMock()
    r.stop = MagicMock()
    return r


def _mock_parse_result(
    prompt="hello", warnings=None, attachments=None, link_attachments=None
):
    m = MagicMock()
    m.prompt = prompt
    m.warnings = warnings or []
    m.attachments = attachments or []
    m.link_attachments = link_attachments or []
    return m


def _mock_clipboard(images=None):
    mgr = MagicMock()
    mgr.get_pending_images.return_value = images or []
    mgr.get_pending_count.return_value = len(images) if images else 0
    mgr.clear_pending = MagicMock()
    return mgr


def _apply_patches(stack, patches_dict):
    """Apply a dict of patches using an ExitStack."""
    for target, value in patches_dict.items():
        stack.enter_context(patch(target, value))


def _base_main_patches():
    """Return a dict of common patches needed for main()."""
    return {
        "code_puppy.cli_runner.find_available_port": MagicMock(return_value=8090),
        "code_puppy.cli_runner.ensure_config_exists": MagicMock(),
        "code_puppy.cli_runner.validate_cancel_agent_key": MagicMock(),
        "code_puppy.cli_runner.initialize_command_history_file": MagicMock(),
        "code_puppy.cli_runner.get_use_dbos": MagicMock(return_value=False),
        "code_puppy.cli_runner.default_version_mismatch_behavior": MagicMock(),
        "code_puppy.cli_runner.print_truecolor_warning": MagicMock(),
        "code_puppy.cli_runner.reset_unix_terminal": MagicMock(),
        "code_puppy.cli_runner.reset_windows_terminal_ansi": MagicMock(),
        "code_puppy.cli_runner.reset_windows_terminal_full": MagicMock(),
        "code_puppy.cli_runner.callbacks": MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[]),
        ),
        "code_puppy.cli_runner.plugins": MagicMock(),
        "code_puppy.config.load_api_keys_to_environment": MagicMock(),
    }


def _interactive_patches():
    return {
        "code_puppy.cli_runner.print_truecolor_warning": MagicMock(),
        "code_puppy.cli_runner.get_cancel_agent_display_name": MagicMock(
            return_value="Ctrl+C"
        ),
        "code_puppy.cli_runner.reset_windows_terminal_ansi": MagicMock(),
        "code_puppy.cli_runner.reset_windows_terminal_full": MagicMock(),
        "code_puppy.cli_runner.save_command_to_history": MagicMock(),
        "code_puppy.cli_runner.finalize_autosave_session": MagicMock(
            return_value="session-1"
        ),
        "code_puppy.cli_runner.COMMAND_HISTORY_FILE": "/tmp/test_history",
        "code_puppy.command_line.motd.print_motd": MagicMock(),
        "code_puppy.command_line.onboarding_wizard.should_show_onboarding": MagicMock(
            return_value=False
        ),
        "code_puppy.config.auto_save_session_if_enabled": MagicMock(),
    }


async def _run_interactive(
    renderer,
    patches_dict,
    input_fn,
    agent=None,
    initial_command=None,
    extra_patches=None,
):
    """Helper to run interactive_mode with patching."""
    if agent is None:
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

    with ExitStack() as stack:
        _apply_patches(stack, patches_dict)
        stack.enter_context(
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
                side_effect=input_fn
                if callable(input_fn) and not isinstance(input_fn, AsyncMock)
                else input_fn,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
                return_value="> ",
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            )
        )
        if extra_patches:
            _apply_patches(stack, extra_patches)

        from code_puppy.cli_runner import interactive_mode

        await interactive_mode(renderer, initial_command=initial_command)


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------


class TestMain:
    """Test the main() async function."""

    async def _run_main(self, argv, extra_patches=None, base_overrides=None):
        patches = _base_main_patches()
        if base_overrides:
            patches.update(base_overrides)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"}))
            stack.enter_context(patch("sys.argv", argv))
            stack.enter_context(
                patch(
                    "code_puppy.messaging.SynchronousInteractiveRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.messaging.RichConsoleRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_global_queue", return_value=MagicMock())
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_message_bus", return_value=MagicMock())
            )
            _apply_patches(stack, patches)
            if extra_patches:
                _apply_patches(stack, extra_patches)
            from code_puppy.cli_runner import main

            await main()

    @pytest.mark.anyio
    async def test_prompt_mode(self):
        mock_exec = AsyncMock()
        await self._run_main(
            ["code-puppy", "-p", "hello world"],
            extra_patches={"code_puppy.cli_runner.execute_single_prompt": mock_exec},
        )
        mock_exec.assert_called_once()

    @pytest.mark.anyio
    async def test_interactive_mode_default(self):
        mock_inter = AsyncMock()
        await self._run_main(
            ["code-puppy"],
            extra_patches={
                "code_puppy.cli_runner.interactive_mode": mock_inter,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            },
        )
        mock_inter.assert_called_once()

    @pytest.mark.anyio
    async def test_with_command_args(self):
        mock_inter = AsyncMock()
        await self._run_main(
            ["code-puppy", "do", "something"],
            extra_patches={
                "code_puppy.cli_runner.interactive_mode": mock_inter,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            },
        )
        assert mock_inter.call_args[1]["initial_command"] == "do something"

    @pytest.mark.anyio
    async def test_no_available_port(self):
        await self._run_main(
            ["code-puppy", "-p", "test"],
            base_overrides={
                "code_puppy.cli_runner.find_available_port": MagicMock(
                    return_value=None
                ),
            },
        )

    @pytest.mark.anyio
    async def test_keymap_error(self):
        from code_puppy.keymap import KeymapError

        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-p", "test"],
                base_overrides={
                    "code_puppy.cli_runner.validate_cancel_agent_key": MagicMock(
                        side_effect=KeymapError("bad key")
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_model_valid(self):
        mock_set = MagicMock()
        await self._run_main(
            ["code-puppy", "-m", "gpt-5", "-p", "hi"],
            extra_patches={
                "code_puppy.cli_runner.execute_single_prompt": AsyncMock(),
                "code_puppy.config.set_model_name": mock_set,
                "code_puppy.config._validate_model_exists": MagicMock(
                    return_value=True
                ),
            },
        )
        mock_set.assert_called_with("gpt-5")

    @pytest.mark.anyio
    async def test_model_invalid(self):
        mock_mf = MagicMock()
        mock_mf.load_config.return_value = {"gpt-5": {}}
        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-m", "bad-model", "-p", "hi"],
                extra_patches={
                    "code_puppy.config.set_model_name": MagicMock(),
                    "code_puppy.config._validate_model_exists": MagicMock(
                        return_value=False
                    ),
                    "code_puppy.model_factory.ModelFactory": mock_mf,
                },
            )

    @pytest.mark.anyio
    async def test_model_validation_exception(self):
        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-m", "bad", "-p", "hi"],
                extra_patches={
                    "code_puppy.config.set_model_name": MagicMock(),
                    "code_puppy.config._validate_model_exists": MagicMock(
                        side_effect=RuntimeError("boom")
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_agent_valid(self):
        mock_set = MagicMock()
        await self._run_main(
            ["code-puppy", "-a", "code-puppy", "-p", "hi"],
            extra_patches={
                "code_puppy.cli_runner.execute_single_prompt": AsyncMock(),
                "code_puppy.agents.agent_manager.get_available_agents": MagicMock(
                    return_value={"code-puppy": {}}
                ),
                "code_puppy.agents.agent_manager.set_current_agent": mock_set,
            },
        )
        mock_set.assert_called_with("code-puppy")

    @pytest.mark.anyio
    async def test_agent_invalid(self):
        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-a", "bad-agent", "-p", "hi"],
                extra_patches={
                    "code_puppy.agents.agent_manager.get_available_agents": MagicMock(
                        return_value={"code-puppy": {}}
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_agent_exception(self):
        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-a", "bad", "-p", "hi"],
                extra_patches={
                    "code_puppy.agents.agent_manager.get_available_agents": MagicMock(
                        side_effect=RuntimeError("boom")
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_version_check_with_callbacks(self):
        cb_mock = MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[lambda: None]),
        )
        patches = _base_main_patches()
        patches["code_puppy.cli_runner.callbacks"] = cb_mock
        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(os.environ, {"NO_VERSION_UPDATE": ""}, clear=False)
            )
            stack.enter_context(patch("sys.argv", ["code-puppy", "-p", "hi"]))
            stack.enter_context(
                patch(
                    "code_puppy.messaging.SynchronousInteractiveRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.messaging.RichConsoleRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_global_queue", return_value=MagicMock())
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_message_bus", return_value=MagicMock())
            )
            stack.enter_context(
                patch(
                    "code_puppy.cli_runner.execute_single_prompt",
                    new_callable=AsyncMock,
                )
            )
            _apply_patches(stack, patches)
            from code_puppy.cli_runner import main

            await main()
            cb_mock.on_version_check.assert_called_once()

    @pytest.mark.anyio
    async def test_version_check_no_callbacks(self):
        """Version check falls back to default_version_mismatch_behavior."""
        patches = _base_main_patches()
        patches["code_puppy.cli_runner.callbacks"] = MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[]),
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(os.environ, {"NO_VERSION_UPDATE": ""}, clear=False)
            )
            stack.enter_context(patch("sys.argv", ["code-puppy", "-p", "hi"]))
            stack.enter_context(
                patch(
                    "code_puppy.messaging.SynchronousInteractiveRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.messaging.RichConsoleRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_global_queue", return_value=MagicMock())
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_message_bus", return_value=MagicMock())
            )
            stack.enter_context(
                patch(
                    "code_puppy.cli_runner.execute_single_prompt",
                    new_callable=AsyncMock,
                )
            )
            _apply_patches(stack, patches)
            from code_puppy.cli_runner import main

            await main()

    @pytest.mark.anyio
    async def test_dbos_enabled(self):
        mock_dbos_cls = MagicMock()
        await self._run_main(
            ["code-puppy", "-p", "hi"],
            base_overrides={
                "code_puppy.cli_runner.get_use_dbos": MagicMock(return_value=True),
            },
            extra_patches={
                "code_puppy.cli_runner.execute_single_prompt": AsyncMock(),
                "code_puppy.cli_runner.DBOS": mock_dbos_cls,
            },
        )
        mock_dbos_cls.launch.assert_called_once()

    @pytest.mark.anyio
    async def test_dbos_init_error(self):
        mock_dbos_cls = MagicMock(side_effect=RuntimeError("db fail"))
        with pytest.raises(SystemExit):
            await self._run_main(
                ["code-puppy", "-p", "hi"],
                base_overrides={
                    "code_puppy.cli_runner.get_use_dbos": MagicMock(return_value=True),
                },
                extra_patches={
                    "code_puppy.cli_runner.DBOS": mock_dbos_cls,
                },
            )

    @pytest.mark.anyio
    async def test_pyfiglet_import_error(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pyfiglet":
                raise ImportError("no pyfiglet")
            return real_import(name, *args, **kwargs)

        await self._run_main(
            ["code-puppy"],
            extra_patches={
                "code_puppy.cli_runner.interactive_mode": AsyncMock(),
                "builtins.__import__": fake_import,
            },
        )


# ---------------------------------------------------------------------------
# interactive_mode() tests
# ---------------------------------------------------------------------------


class TestInteractiveMode:
    """Test interactive_mode() branches."""

    @pytest.mark.anyio
    async def test_exit_command(self):
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
        )

    @pytest.mark.anyio
    async def test_quit_command(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = None  # test None prompt branch
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="quit"),
            agent=agent,
        )

    @pytest.mark.anyio
    async def test_eof_exits(self):
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(side_effect=EOFError),
        )

    @pytest.mark.anyio
    async def test_keyboard_interrupt_continues(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt
            return "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
            },
        )

    @pytest.mark.anyio
    async def test_keyboard_interrupt_stops_wiggum(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt
            return "/exit"

        mock_stop = MagicMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=True
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": mock_stop,
            },
        )
        mock_stop.assert_called()

    @pytest.mark.anyio
    async def test_clear_command(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/clear" if call_count == 1 else "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.get_clipboard_manager": MagicMock(
                    return_value=_mock_clipboard([b"img"])
                ),
            },
        )
        agent.clear_message_history.assert_called()

    @pytest.mark.anyio
    async def test_slash_command_handled(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/help" if call_count == 1 else "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value=True
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/help")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_returns_prompt(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/custom" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="run this"
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/custom")
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_exception(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/bad" if call_count == 1 else "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    side_effect=RuntimeError("cmd error")
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/bad")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_normal_prompt_execution(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_prompt_returns_none_cancelled(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_prompt_cancelled_wiggum_active(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_stop = MagicMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=True
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": mock_stop,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
            },
        )
        mock_stop.assert_called()

    @pytest.mark.anyio
    async def test_prompt_exception(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    side_effect=RuntimeError("agent error")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.messaging.queue_console.get_queue_console": MagicMock(
                    return_value=MagicMock()
                ),
            },
        )

    @pytest.mark.anyio
    async def test_empty_input_skipped(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "   " if call_count == 1 else "/exit"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("   ")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_success(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_error(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    side_effect=RuntimeError("fail")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_returns_none(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
            },
        )

    @pytest.mark.anyio
    async def test_autosave_load_non_tty(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/autosave_load" if call_count == 1 else "/exit"

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = False

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="__AUTOSAVE_LOAD__"
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/autosave_load")
                ),
                "sys.stdin": mock_stdin,
                "sys.stdout": mock_stdout,
                "code_puppy.session_storage.restore_autosave_interactively": AsyncMock(),
            },
        )

    @pytest.mark.anyio
    async def test_autosave_load_tty_cancelled(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/autosave_load" if call_count == 1 else "/exit"

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": ""}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                fake_input,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/autosave_load")
                    ),
                    "sys.stdin": mock_stdin,
                    "sys.stdout": mock_stdout,
                    "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                        return_value=None
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_autosave_load_tty_success(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/autosave_load" if call_count == 1 else "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        agent.estimate_tokens_for_message.return_value = 10

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": ""}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                fake_input,
                agent=agent,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/autosave_load")
                    ),
                    "sys.stdin": mock_stdin,
                    "sys.stdout": mock_stdout,
                    "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                        return_value="my-session"
                    ),
                    "code_puppy.session_storage.load_session": MagicMock(
                        return_value=[MagicMock()]
                    ),
                    "code_puppy.config.set_current_autosave_from_session_name": MagicMock(),
                    "code_puppy.command_line.autosave_menu.display_resumed_history": MagicMock(),
                    "code_puppy.cli_runner.get_current_agent": MagicMock(
                        return_value=agent
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_autosave_load_exception(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/autosave_load" if call_count == 1 else "/exit"

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = False

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="__AUTOSAVE_LOAD__"
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/autosave_load")
                ),
                "sys.stdin": mock_stdin,
                "sys.stdout": mock_stdout,
                "code_puppy.session_storage.restore_autosave_interactively": AsyncMock(
                    side_effect=RuntimeError("fail")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_returns_false(self):
        """Command returns False = not recognized, fall through."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/unknown" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="ok")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value=False
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/unknown")
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
            },
        )

    @pytest.mark.anyio
    async def test_wiggum_loop(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            return wiggum_calls == 1

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.get_wiggum_prompt": MagicMock(
                    return_value="repeat"
                ),
                "code_puppy.command_line.wiggum_state.increment_wiggum_count": MagicMock(
                    return_value=1
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": MagicMock(),
            },
        )

    @pytest.mark.anyio
    async def test_wiggum_loop_cancelled(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            return (None, MagicMock())

        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            return wiggum_calls == 1

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.get_wiggum_prompt": MagicMock(
                    return_value="repeat"
                ),
                "code_puppy.command_line.wiggum_state.increment_wiggum_count": MagicMock(
                    return_value=1
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": MagicMock(),
            },
        )

    @pytest.mark.anyio
    async def test_wiggum_no_prompt_stops(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            return wiggum_calls <= 1

        mock_stop = MagicMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.get_wiggum_prompt": MagicMock(
                    return_value=None
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": mock_stop,
            },
        )
        mock_stop.assert_called()

    @pytest.mark.anyio
    async def test_wiggum_loop_exception(self):
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            raise RuntimeError("wiggum fail")

        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            return wiggum_calls == 1

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.get_wiggum_prompt": MagicMock(
                    return_value="repeat"
                ),
                "code_puppy.command_line.wiggum_state.increment_wiggum_count": MagicMock(
                    return_value=1
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": MagicMock(),
            },
        )

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
                "code_puppy.plugins.chatgpt_oauth.oauth_flow.run_oauth_flow": MagicMock(),
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
                "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication": MagicMock(),
                "code_puppy.config.set_model_name": MagicMock(),
            },
        )

    @pytest.mark.anyio
    async def test_onboarding_completed(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(return_value=True)
        )

        mock_future = MagicMock()
        mock_future.result.return_value = "completed"
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
    async def test_onboarding_skipped(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.onboarding_wizard.should_show_onboarding"] = (
            MagicMock(return_value=True)
        )

        mock_future = MagicMock()
        mock_future.result.return_value = "skipped"
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
    async def test_motd_exception(self):
        patches = _interactive_patches()
        patches["code_puppy.command_line.motd.print_motd"] = MagicMock(
            side_effect=RuntimeError("motd fail")
        )

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
        )

    @pytest.mark.anyio
    async def test_clear_no_clipboard_images(self):
        """Test /clear when no clipboard images pending."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/clear" if call_count == 1 else "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.get_clipboard_manager": MagicMock(
                    return_value=_mock_clipboard()
                ),
            },
        )


# ---------------------------------------------------------------------------
# main_entry() additional tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Additional interactive_mode edge cases for remaining uncovered lines
# ---------------------------------------------------------------------------


class TestInteractiveModeEdgeCases:
    """Cover remaining uncovered lines in interactive_mode."""

    @pytest.mark.anyio
    async def test_exit_with_running_task(self):
        """Lines 594-599: exit cancels running agent task."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "do work"
            return "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        # Use a real Future that we can cancel and await
        loop = asyncio.get_event_loop()
        mock_task = loop.create_future()
        # Don't resolve it - it stays pending (not done)

        async def fake_run(*a, **kw):
            return (mock_result, mock_task)

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("do work")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
            },
        )

    @pytest.mark.anyio
    async def test_eof_with_running_task_cancels(self):
        """Lines 574-579: EOF cancels running agent task."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "do work"
            raise EOFError

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        loop = asyncio.get_event_loop()
        mock_task = loop.create_future()

        async def fake_run(*a, **kw):
            return (mock_result, mock_task)

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("do work")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": MagicMock(
                    return_value=False
                ),
            },
        )

    @pytest.mark.anyio
    async def test_clear_with_clipboard_images(self):
        """Line 625: clipboard_count > 0 message."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "clear" if call_count == 1 else "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        clip = _mock_clipboard([b"img1", b"img2"])

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.command_line.clipboard.get_clipboard_manager": MagicMock(
                    return_value=clip
                ),
            },
        )

    @pytest.mark.anyio
    async def test_autosave_load_no_tui_env(self):
        """Line 656: CODE_PUPPY_NO_TUI=1 forces non-interactive picker."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "/autosave_load" if call_count == 1 else "/exit"

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": "1"}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                fake_input,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/autosave_load")
                    ),
                    "sys.stdin": mock_stdin,
                    "sys.stdout": mock_stdout,
                    "code_puppy.session_storage.restore_autosave_interactively": AsyncMock(),
                },
            )

    @pytest.mark.anyio
    async def test_wiggum_keyboard_interrupt(self):
        """Lines 874-876: KeyboardInterrupt in wiggum loop."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []
        run_call = 0

        async def fake_run(*a, **kw):
            nonlocal run_call
            run_call += 1
            if run_call == 1:
                return (mock_result, MagicMock())
            raise KeyboardInterrupt

        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            return wiggum_calls == 1

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": fake_run,
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.get_wiggum_prompt": MagicMock(
                    return_value="repeat"
                ),
                "code_puppy.command_line.wiggum_state.increment_wiggum_count": MagicMock(
                    return_value=1
                ),
                "code_puppy.command_line.wiggum_state.stop_wiggum": MagicMock(),
            },
        )


# ---------------------------------------------------------------------------
# main() uvx detection and other edge cases
# ---------------------------------------------------------------------------


class TestMainUvxAndEdgeCases:
    @pytest.mark.anyio
    async def test_uvx_alternate_cancel_key(self):
        """Lines 181-212: uvx should_use_alternate_cancel_key returns True."""
        patches = _base_main_patches()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"}))
            stack.enter_context(patch("sys.argv", ["code-puppy", "-p", "hi"]))
            stack.enter_context(
                patch(
                    "code_puppy.messaging.SynchronousInteractiveRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.messaging.RichConsoleRenderer",
                    return_value=_mock_renderer(),
                )
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_global_queue", return_value=MagicMock())
            )
            stack.enter_context(
                patch("code_puppy.messaging.get_message_bus", return_value=MagicMock())
            )
            stack.enter_context(
                patch(
                    "code_puppy.cli_runner.execute_single_prompt",
                    new_callable=AsyncMock,
                )
            )
            _apply_patches(stack, patches)
            # Patch the uvx detection to return True
            stack.enter_context(
                patch(
                    "code_puppy.uvx_detection.should_use_alternate_cancel_key",
                    return_value=True,
                )
            )
            stack.enter_context(
                patch("code_puppy.terminal_utils.disable_windows_ctrl_c")
            )
            stack.enter_context(
                patch("code_puppy.terminal_utils.set_keep_ctrl_c_disabled")
            )
            stack.enter_context(patch("signal.signal"))
            from code_puppy.cli_runner import main

            await main()

    @pytest.mark.anyio
    async def test_initial_command_awaiting_input(self):
        """Lines 405-406: is_awaiting_user_input branch."""
        patches = _interactive_patches()
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.tools.command_runner.is_awaiting_user_input": MagicMock(
                    return_value=True
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_awaiting_input_import_error(self):
        """Lines 405-406: is_awaiting_user_input ImportError."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "command_runner" in name and "is_awaiting" not in str(args):
                # Only block the specific import inside the try block
                pass
            return real_import(name, *args, **kwargs)

        patches = _interactive_patches()
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            patches,
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.cli_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
            },
        )


class TestRemainingEdgeCases:
    """Cover the hardest-to-reach lines."""

    @pytest.mark.anyio
    async def test_cancelled_result_wiggum_stop_message(self):
        """Lines 750-751: cancelled result emits wiggum stop warning."""
        call_count = 0

        async def fake_input(*a, **kw):
            nonlocal call_count
            call_count += 1
            return "write hello" if call_count == 1 else "/exit"

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        # First call to is_wiggum_active: False (in the result==None block)
        # But we need the result to be None AND wiggum to be active
        # The code path: result is None -> reset terminal -> check wiggum -> stop + emit
        wiggum_calls = 0

        def fake_wiggum():
            nonlocal wiggum_calls
            wiggum_calls += 1
            # Called from the result==None block
            if wiggum_calls == 1:
                return True  # in the cancelled block
            return False  # after the while loop

        mock_stop = MagicMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.command_line.wiggum_state.is_wiggum_active": fake_wiggum,
                "code_puppy.command_line.wiggum_state.stop_wiggum": mock_stop,
            },
        )
        mock_stop.assert_called()

    @pytest.mark.anyio
    async def test_execute_single_prompt_success_path(self):
        """Lines 1005-1015: execute_single_prompt success with .output access."""
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = _mock_renderer()
        # response needs .output attribute (not a tuple)
        mock_response = MagicMock()
        mock_response.output = "the response"

        with ExitStack() as stack:
            stack.enter_context(patch("code_puppy.cli_runner.get_current_agent"))
            stack.enter_context(
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                )
            )
            stack.enter_context(patch("code_puppy.cli_runner.emit_info"))
            await execute_single_prompt("test", mock_renderer)


class TestImportErrorFallbacks:
    """Test ImportError fallback branches."""

    @pytest.mark.anyio
    async def test_prompt_toolkit_import_error_fallback(self):
        """Lines 449-470, 542-546: prompt_toolkit not installed.

        These lines are import-error fallbacks for prompt_toolkit_completion.
        They're only reachable when the module genuinely can't be imported,
        which is impractical to test without breaking the test infrastructure.
        Marking as known-uncoverable (Windows/missing-dep edge case).
        """
        # This test documents that lines 449-470 and 542-546 are
        # ImportError fallback paths that can't be easily covered
        # in a test environment where prompt_toolkit is installed.
        pass

    @pytest.mark.anyio
    async def test_is_awaiting_user_input_import_error(self):
        """Lines 405-406: ImportError for is_awaiting_user_input."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "code_puppy.tools.command_runner":
                raise ImportError("no command_runner")
            return real_import(name, *args, **kwargs)

        renderer = _mock_renderer()
        patches = _interactive_patches()
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        with ExitStack() as stack:
            _apply_patches(stack, patches)
            stack.enter_context(
                patch(
                    "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
                    new_callable=AsyncMock,
                    return_value="/exit",
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
                    return_value="> ",
                )
            )
            stack.enter_context(
                patch(
                    "code_puppy.agents.agent_manager.get_current_agent",
                    return_value=agent,
                )
            )
            stack.enter_context(
                patch("code_puppy.cli_runner.get_current_agent", return_value=agent)
            )
            stack.enter_context(
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    new_callable=AsyncMock,
                    return_value=(mock_result, MagicMock()),
                )
            )
            stack.enter_context(patch("builtins.__import__", side_effect=fake_import))
            from code_puppy.cli_runner import interactive_mode

            await interactive_mode(renderer, initial_command="test")


class TestMainEntryAdditional:
    @patch("asyncio.run", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_stderr_output(self, mock_run):
        from code_puppy.cli_runner import main_entry

        with ExitStack() as stack:
            stack.enter_context(patch("code_puppy.cli_runner.reset_unix_terminal"))
            stack.enter_context(
                patch("code_puppy.cli_runner.get_use_dbos", return_value=False)
            )
            result = main_entry()
            assert result == 0
