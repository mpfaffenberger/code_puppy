"""Invalid persisted identity must fail without replacing the active session."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents._session_state import SESSION_KEY
from code_puppy.command_line import session_commands
from code_puppy.i18n import t
from code_puppy.session_storage import save_session
from tests.agents.test_session_state_identity import SessionAgent
from tests.test_cli_runner_full_coverage import (
    _interactive_patches,
    _mock_parse_result,
    _mock_renderer,
    _run_interactive,
    _scripted_input,
)


@pytest.fixture(
    params=["not-a-dict", {}, {"agent_id": "invalid\nidentity"}, {"agent_id": "other"}]
)
def saved_session(request, tmp_path):
    history = [
        ModelRequest(
            parts=[UserPromptPart("saved")], metadata={SESSION_KEY: request.param}
        )
    ]
    save_session(
        session_name="saved",
        history=history,
        base_dir=tmp_path,
        timestamp="2026-01-01T00:00:00",
        token_estimator=lambda message: 1,
    )
    return tmp_path


@pytest.fixture
def active_session():
    agent = SessionAgent(agent_id="active")
    history = [ModelRequest(parts=[UserPromptPart("active conversation")])]
    agent.set_message_history(history)
    cached = agent._code_generation_agent = object()
    return agent, history, cached


def assert_unchanged(active_session):
    agent, history, cached = active_session
    assert agent.id == "active"
    assert agent.get_message_history() is history
    assert agent._code_generation_agent is cached


@pytest.mark.parametrize("command", ["quick_resume", "load_context"])
def test_load_commands_reject_invalid_identity(saved_session, active_session, command):
    agent, _, _ = active_session
    with (
        patch.object(session_commands, "AUTOSAVE_DIR", str(saved_session)),
        patch("code_puppy.agents.agent_manager.get_current_agent", return_value=agent),
        patch(
            "code_puppy.config.resolve_quick_resume_pickle",
            return_value=saved_session / "saved.json",
        ),
        patch(
            "code_puppy.config.get_quick_resume_location",
            return_value=(str(saved_session), "test"),
        ),
        patch("code_puppy.config.set_current_autosave_from_session_name") as pin,
        patch("code_puppy.config.rotate_session_name") as rotate,
        patch("code_puppy.messaging.emit_error") as error,
        patch("code_puppy.messaging.emit_success") as success,
        patch("code_puppy.messaging.emit_info"),
    ):
        handler = getattr(session_commands, f"handle_{command}_command")
        assert handler(f"/{command.replace('_', '-')} saved") is True
    error.assert_called_once()
    success.assert_not_called()
    pin.assert_not_called()
    rotate.assert_not_called()
    assert_unchanged(active_session)


async def test_autosave_picker_rejects_invalid_identity_and_continues(
    saved_session, active_session, monkeypatch
):
    agent, _, _ = active_session
    error = MagicMock()
    pin = MagicMock()
    preview = MagicMock()
    parse = MagicMock(return_value=_mock_parse_result("/autosave_load"))
    stdin, stdout = MagicMock(), MagicMock()
    stdin.isatty.return_value = stdout.isatty.return_value = True
    monkeypatch.setenv("CODE_PUPPY_NO_TUI", "")
    monkeypatch.setenv("CODE_PUPPY_CLASSIC_PROMPT", "1")
    patches = _interactive_patches()
    patches["code_puppy.cli_runner.COMMAND_HISTORY_FILE"] = str(
        saved_session / "history"
    )
    # A second command proves the loop survives the failed restore, then EOF quits.
    await _run_interactive(
        _mock_renderer(),
        patches,
        _scripted_input("/autosave_load", "/help"),
        agent=agent,
        extra_patches={
            "code_puppy.cli_runner.AUTOSAVE_DIR": str(saved_session),
            "code_puppy.command_line.command_handler.handle_command": MagicMock(
                side_effect=["__AUTOSAVE_LOAD__", True]
            ),
            "code_puppy.cli_runner.parse_prompt_attachments": parse,
            "sys.stdin": stdin,
            "sys.stdout": stdout,
            "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                return_value="saved"
            ),
            "code_puppy.config.pin_current_session_name": pin,
            "code_puppy.command_line.autosave_menu.display_resumed_history": preview,
            "code_puppy.messaging.emit_error": error,
        },
    )
    assert parse.call_count == 2
    error.assert_called_once()
    assert str(error.call_args.args[0]).startswith(
        t("cli.autosave.load_failed", error="")
    )
    pin.assert_not_called()
    preview.assert_not_called()
    assert_unchanged(active_session)
