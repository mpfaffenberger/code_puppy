"""Threshold boundaries, localization, and real /resume wiring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy import resume_advice
from code_puppy.i18n import format_number, get_locale, set_locale, t
from tests.test_cli_runner_full_coverage import (
    _interactive_patches,
    _mock_parse_result,
    _mock_renderer,
    _run_interactive,
    _scripted_input,
)


@pytest.mark.parametrize(
    "tokens,expected", [(0, False), (84999, False), (85000, False), (85001, True)]
)
def test_threshold_boundary(tokens, expected):
    with (
        patch.object(resume_advice, "get_compaction_threshold", return_value=0.85),
        patch.object(resume_advice, "emit_warning") as warning,
    ):
        resume_advice.suggest_compaction(tokens, 100000)
    assert warning.called is expected
    if expected:
        assert "/compact" in warning.call_args.args[0]


@pytest.mark.parametrize("locale", ["en-US", "es", "fr-CA", "qps-ploc"])
def test_configured_threshold_and_localization(locale):
    previous_locale = get_locale()
    set_locale(locale)
    try:
        with (
            patch.object(resume_advice, "get_compaction_threshold", return_value=0.5),
            patch.object(resume_advice, "emit_warning") as warning,
        ):
            resume_advice.suggest_compaction(10001, 20000)
        warning.assert_called_once_with(
            t(
                "cli.autosave.compact_suggestion",
                tokens=format_number(10001),
                threshold=format_number(10000),
            )
        )
        assert "/compact" in warning.call_args.args[0]
        assert "cli.autosave.compact_suggestion" not in warning.call_args.args[0]
    finally:
        set_locale(previous_locale)


@pytest.mark.parametrize(
    "tokens,agent_context,expected",
    [
        (85000, 100000, False),
        (85001, 100000, True),
        (90000, 100000, True),
        (90000, 200000, False),
    ],
)
async def test_resume_suggests_without_changing_history(
    tokens, agent_context, expected, monkeypatch
):
    monkeypatch.setenv("CODE_PUPPY_NO_TUI", "")
    agent = MagicMock()
    agent.get_user_prompt.return_value = "task:"
    agent.estimate_tokens_for_message.return_value = tokens
    # A pinned model can differ from the global 200k context window.
    from code_puppy.agents.base_agent import BaseAgent

    agent.get_model_name.return_value = "pinned-model"
    agent._get_model_context_length.side_effect = lambda: (
        BaseAgent._get_model_context_length(agent)
    )
    history = [MagicMock()]
    tty = MagicMock()
    tty.isatty.return_value = True
    warning = MagicMock()
    with (
        patch.object(resume_advice, "get_compaction_threshold", return_value=0.85),
        patch("code_puppy.config.get_global_model_name", return_value="global-model"),
        patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={
                "global-model": {"context_length": 200000},
                "pinned-model": {"context_length": agent_context},
            },
        ),
        patch.object(resume_advice, "emit_warning", warning),
    ):
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            _scripted_input("/resume"),
            agent=agent,
            extra_patches={
                "code_puppy.cli_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/resume")
                ),
                "sys.stdin": tty,
                "sys.stdout": tty,
                "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                    return_value="my-session"
                ),
                "code_puppy.session_storage.load_session": MagicMock(
                    return_value=history
                ),
                "code_puppy.config.pin_current_session_name": MagicMock(),
                "code_puppy.command_line.autosave_menu.display_resumed_history": MagicMock(),
            },
        )
    agent.set_message_history.assert_called_once_with(history)
    assert warning.called is expected
    if expected:
        assert "/compact" in warning.call_args.args[0]
