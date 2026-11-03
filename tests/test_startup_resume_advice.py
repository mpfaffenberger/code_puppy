"""The CLI resume flags share the fixed, non-destructive compaction advice."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy import resume_advice
from tests.test_cli_runner_full_coverage import TestMain as _MainHarness


@pytest.mark.parametrize("resume_args", [["-r", "my-session"], ["-qr"]])
@pytest.mark.parametrize(
    "tokens,expected", [(49999, False), (50000, False), (50001, True)]
)
@pytest.mark.parametrize("headless", [False, True])
async def test_startup_resume_advice(resume_args, tokens, expected, headless, tmp_path):
    agent = MagicMock()
    agent.estimate_tokens_for_message.return_value = tokens
    agent._get_model_context_length.return_value = 100000
    history = [MagicMock()]
    warning = MagicMock()
    resolver = MagicMock(return_value=("my-session", tmp_path, False))
    preview = MagicMock()
    tty = MagicMock()
    tty.isatty.return_value = True
    argv = ["code-puppy", *resume_args]
    if headless:
        argv.extend(["-p", "hello"])
    with patch.object(resume_advice, "emit_warning", warning):
        await _MainHarness()._run_main(
            argv,
            extra_patches={
                "code_puppy.cli_runner.interactive_mode": AsyncMock(),
                "code_puppy.cli_runner.execute_single_prompt": AsyncMock(),
                "code_puppy.agents.agent_manager.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.session_lifecycle.resolve_or_create_resume_target": resolver,
                "code_puppy.session_storage.load_session": MagicMock(
                    return_value=history
                ),
                "code_puppy.config.pin_current_session_name": MagicMock(),
                "code_puppy.config.get_quick_resume_location": MagicMock(
                    return_value=(str(tmp_path), None)
                ),
                "code_puppy.config.resolve_quick_resume_pickle": MagicMock(
                    return_value=str(tmp_path / "my-session.json")
                ),
                "code_puppy.command_line.autosave_menu.display_resumed_history": preview,
                "code_puppy.cli_runner._save_autosave_snapshot": MagicMock(),
                "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
                "sys.stdout": tty,
            },
        )
    assert resolver.call_args.args[0] == (
        str(tmp_path / "my-session.json") if resume_args == ["-qr"] else "my-session"
    )
    agent.set_message_history.assert_called_once_with(history)
    assert warning.call_count == int(expected)
    if expected:
        assert "/compact" in warning.call_args.args[0]
    assert preview.called is not headless


@pytest.mark.parametrize("resume_args", [["-r", "my-session"], ["-qr"]])
async def test_failed_startup_resume_does_not_suggest(resume_args, tmp_path):
    with patch.object(resume_advice, "emit_warning") as warning:
        with pytest.raises(SystemExit) as exit_info:
            await _MainHarness()._run_main(
                ["code-puppy", *resume_args],
                extra_patches={
                    "code_puppy.session_lifecycle.resolve_or_create_resume_target": MagicMock(
                        return_value=("my-session", tmp_path, False)
                    ),
                    "code_puppy.session_storage.load_session": MagicMock(
                        side_effect=ValueError("Damaged session")
                    ),
                    "code_puppy.config.get_quick_resume_location": MagicMock(
                        return_value=(str(tmp_path), None)
                    ),
                    "code_puppy.config.resolve_quick_resume_pickle": MagicMock(
                        return_value=str(Path(tmp_path) / "my-session.json")
                    ),
                },
            )
    assert exit_info.value.code == 1
    warning.assert_not_called()
