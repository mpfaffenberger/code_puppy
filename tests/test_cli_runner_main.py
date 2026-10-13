"""Coverage for cli_entry.py::main() (the async CLI entry dispatch).

Split out of test_cli_runner_full_coverage.py; shared helpers live in
``tests/cli_runner_fixtures.py``.
"""

import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tests.cli_runner_fixtures import (
    _apply_patches,
    _assert_core_plugins_message_once,
    _base_main_patches,
    _mock_renderer,
)


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
            extra_patches={"code_puppy.cli_entry.execute_single_prompt": mock_exec},
        )
        mock_exec.assert_called_once()

    @pytest.mark.anyio
    async def test_prompt_mode_does_not_double_autosave(self):
        """The interactive-only belt-and-braces save must not also fire for
        headless `-p` runs: execute_single_prompt() already persists itself
        in its own finally (via persist_named_session), to the same session
        name. A second save here would write the file twice, fire the
        post_autosave hook in headless mode, and touch sessions for runs
        that never invoked the agent."""
        mock_exec = AsyncMock()
        mock_autosave = MagicMock()
        await self._run_main(
            ["code-puppy", "-p", "hello world"],
            extra_patches={
                "code_puppy.cli_entry.execute_single_prompt": mock_exec,
                "code_puppy.cli_entry._save_autosave_snapshot": mock_autosave,
            },
        )
        mock_autosave.assert_not_called()

    @pytest.mark.anyio
    async def test_interactive_mode_default(self, capsys):
        mock_inter = AsyncMock()
        await self._run_main(
            ["code-puppy"],
            extra_patches={
                "code_puppy.cli_entry.interactive_mode": mock_inter,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            },
        )
        mock_inter.assert_called_once()
        output = capsys.readouterr().out.lower()
        assert "logo" in output
        assert "pydantic" not in output
        assert "logfire" not in output

    @pytest.mark.anyio
    async def test_shutdown_persists_autosave_snapshot(self):
        """main()'s finally is the belt-and-braces save for any shutdown path
        (Ctrl-D, /exit, top-level interrupt) a cancelled turn skipped."""
        mock_inter = AsyncMock()
        mock_autosave = MagicMock()
        await self._run_main(
            ["code-puppy"],
            extra_patches={
                "code_puppy.cli_entry.interactive_mode": mock_inter,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
                "code_puppy.cli_entry._save_autosave_snapshot": mock_autosave,
            },
        )
        mock_autosave.assert_called_once()

    @pytest.mark.anyio
    async def test_narrow_terminal_interactive_mode_uses_compact_banner(self):
        mock_inter = AsyncMock()
        mock_figlet = MagicMock(return_value="LOGO\n\n")
        # Rich's Console honors COLUMNS, so this squeezes the banner width
        # below the full CODE PUPPY figlet (79 cols).
        with patch.dict(os.environ, {"COLUMNS": "50"}):
            await self._run_main(
                ["code-puppy"],
                extra_patches={
                    "code_puppy.cli_entry.interactive_mode": mock_inter,
                    "pyfiglet.figlet_format": mock_figlet,
                },
            )

        mock_figlet.assert_called_once_with("PUP", font="ansi_shadow")

    @pytest.mark.anyio
    async def test_with_command_args(self):
        mock_inter = AsyncMock()
        await self._run_main(
            ["code-puppy", "do", "something"],
            extra_patches={
                "code_puppy.cli_entry.interactive_mode": mock_inter,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            },
        )
        assert mock_inter.call_args[1]["initial_command"] == "do something"

    @pytest.mark.anyio
    async def test_no_available_port(self):
        await self._run_main(
            ["code-puppy", "-p", "test"],
            base_overrides={
                "code_puppy.cli_entry.find_available_port": MagicMock(
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
                    "code_puppy.cli_entry.validate_cancel_agent_key": MagicMock(
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
                "code_puppy.cli_entry.execute_single_prompt": AsyncMock(),
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
                "code_puppy.cli_entry.execute_single_prompt": AsyncMock(),
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
    @pytest.mark.parametrize(
        ("argv", "mode_target"),
        [
            (
                ["code-puppy", "-p", "hi"],
                "code_puppy.cli_entry.execute_single_prompt",
            ),
            (["code-puppy"], "code_puppy.cli_entry.interactive_mode"),
        ],
        ids=["one-shot", "interactive"],
    )
    async def test_core_plugins_version_with_updates_disabled(self, argv, mode_target):
        mock_emit = MagicMock()
        mock_core_version = MagicMock(return_value="0.0.2")

        await self._run_main(
            argv,
            extra_patches={
                mode_target: AsyncMock(),
                "code_puppy.cli_entry.get_core_plugins_version": mock_core_version,
                "code_puppy.messaging.emit_system_message": mock_emit,
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            },
        )

        from code_puppy.cli_entry import __version__ as current_version

        mock_core_version.assert_called_once_with()
        assert call(f"Current version: {current_version}") in mock_emit.call_args_list
        _assert_core_plugins_message_once(mock_emit, "0.0.2")

    @pytest.mark.anyio
    async def test_core_plugins_version_renders_once_through_message_pipeline(self):
        from io import StringIO

        from rich.console import Console as RichConsole

        from code_puppy.messaging.message_queue import MessageQueue

        output = StringIO()
        queue = MessageQueue()
        queue.start()
        console = RichConsole(file=output, force_terminal=False, width=120)

        async def execute_and_drain(*_args, **_kwargs):
            assert queue.drain()

        patches = _base_main_patches()
        patches["code_puppy.cli_entry.get_core_plugins_version"] = MagicMock(
            return_value="0.0.2"
        )

        try:
            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"}))
                stack.enter_context(patch("sys.argv", ["code-puppy", "-p", "hi"]))
                stack.enter_context(
                    patch("code_puppy.cli_entry.Console", return_value=console)
                )
                stack.enter_context(
                    patch(
                        "code_puppy.messaging.RichConsoleRenderer",
                        return_value=_mock_renderer(),
                    )
                )
                stack.enter_context(
                    patch("code_puppy.messaging.get_global_queue", return_value=queue)
                )
                stack.enter_context(
                    patch(
                        "code_puppy.messaging.message_queue.get_global_queue",
                        return_value=queue,
                    )
                )
                stack.enter_context(
                    patch(
                        "code_puppy.messaging.get_message_bus",
                        return_value=MagicMock(),
                    )
                )
                stack.enter_context(
                    patch(
                        "code_puppy.cli_entry.execute_single_prompt",
                        side_effect=execute_and_drain,
                    )
                )
                _apply_patches(stack, patches)

                from code_puppy.cli_runner import main

                await main()
        finally:
            queue.stop()

        assert output.getvalue().count("Core plugins version: 0.0.2") == 1

    @pytest.mark.anyio
    async def test_core_plugins_version_uses_localized_unknown_fallback(self):
        mock_emit = MagicMock()

        await self._run_main(
            ["code-puppy", "-p", "hi"],
            extra_patches={
                "code_puppy.cli_entry.execute_single_prompt": AsyncMock(),
                "code_puppy.cli_entry.get_core_plugins_version": MagicMock(
                    return_value=None
                ),
                "code_puppy.messaging.emit_system_message": mock_emit,
            },
        )

        _assert_core_plugins_message_once(mock_emit, "unknown")

    @pytest.mark.anyio
    async def test_version_flag_output_is_unchanged(self, capsys):
        from code_puppy.cli_entry import __version__ as current_version
        from code_puppy.cli_runner import main

        mock_core_version = MagicMock()
        capsys.readouterr()
        with (
            patch("sys.argv", ["code-puppy", "--version"]),
            patch("code_puppy.cli_entry.callbacks", MagicMock()),
            patch("code_puppy.cli_entry.get_core_plugins_version", mock_core_version),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()

        assert exc_info.value.code == 0
        assert capsys.readouterr().out == f"{current_version}\n"
        mock_core_version.assert_not_called()

    @pytest.mark.anyio
    async def test_version_check_with_callbacks(self):
        cb_mock = MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[lambda: None]),
        )
        patches = _base_main_patches()
        default_version_check = patches[
            "code_puppy.cli_entry.default_version_mismatch_behavior"
        ]
        mock_core_version = MagicMock(return_value="0.0.2")
        mock_emit = MagicMock()
        patches["code_puppy.cli_entry.callbacks"] = cb_mock
        patches["code_puppy.cli_entry.get_core_plugins_version"] = mock_core_version
        patches["code_puppy.messaging.emit_system_message"] = mock_emit
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
                    "code_puppy.cli_entry.execute_single_prompt",
                    new_callable=AsyncMock,
                )
            )
            _apply_patches(stack, patches)
            from code_puppy.cli_runner import main

            await main()
            cb_mock.on_version_check.assert_called_once()
            default_version_check.assert_not_called()
            mock_core_version.assert_called_once_with()
            _assert_core_plugins_message_once(mock_emit, "0.0.2")

    @pytest.mark.anyio
    async def test_version_check_no_callbacks(self):
        """Version check falls back to default_version_mismatch_behavior."""
        patches = _base_main_patches()
        default_version_check = patches[
            "code_puppy.cli_entry.default_version_mismatch_behavior"
        ]
        mock_core_version = MagicMock(return_value="0.0.2")
        mock_emit = MagicMock()
        patches["code_puppy.cli_entry.callbacks"] = MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[]),
        )
        patches["code_puppy.cli_entry.get_core_plugins_version"] = mock_core_version
        patches["code_puppy.messaging.emit_system_message"] = mock_emit
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
                    "code_puppy.cli_entry.execute_single_prompt",
                    new_callable=AsyncMock,
                )
            )
            _apply_patches(stack, patches)
            from code_puppy.cli_runner import main

            await main()
            default_version_check.assert_called_once()
            mock_core_version.assert_called_once_with()
            _assert_core_plugins_message_once(mock_emit, "0.0.2")

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
                "code_puppy.cli_entry.interactive_mode": AsyncMock(),
                "builtins.__import__": fake_import,
            },
        )


# ---------------------------------------------------------------------------
# interactive_mode() tests
# ---------------------------------------------------------------------------
