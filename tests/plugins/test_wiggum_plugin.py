"""Tests for the Wiggum/goal-mode plugin."""

from __future__ import annotations

import importlib

from unittest.mock import patch


def _plugin_module():
    return importlib.import_module("code_puppy.plugins.wiggum.register_callbacks")


def test_goal_command_uses_banner_for_activation():
    module = _plugin_module()

    with (
        patch.object(module, "_display_banner_message") as mock_banner,
        patch.object(module, "emit_info") as mock_info,
        patch.object(module.state, "start") as mock_start,
    ):
        result = module.handle_goal_command("/goal say hi")

    assert result == "say hi"
    mock_start.assert_called_once_with("say hi", mode="goal")
    mock_banner.assert_called_once_with(
        "GOAL MODE",
        "🎯 ACTIVATED!",
        banner_name="llm_judge",
    )
    # Goal: ..., "After each iteration...", "Configure judges..."
    assert mock_info.call_count == 3


def test_display_llm_judge_uses_shared_banner_helper():
    module = _plugin_module()

    with patch.object(module, "_display_banner_message") as mock_banner:
        module._display_llm_judge("✅ done", "notes", final=True)

    mock_banner.assert_called_once_with(
        "LLM JUDGE",
        "✅ done",
        banner_name="llm_judge",
        details="notes",
        final=True,
    )


def test_judges_command_invokes_menu():
    module = _plugin_module()

    fake_future = object()

    class _ExecCtx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, fn):
            class _F:
                def result(self_inner, timeout=None):
                    fn()
                    return fake_future

            return _F()

    with (
        patch.object(module, "asyncio") as mock_asyncio,
        patch(
            "concurrent.futures.ThreadPoolExecutor",
            return_value=_ExecCtx(),
        ),
        patch(
            "code_puppy.command_line.judges_menu.interactive_judges_menu"
        ) as mock_menu,
    ):
        mock_asyncio.run.return_value = None
        result = module.handle_judges_command("/judges")

    assert result is True
    # asyncio.run() was called with the menu coroutine
    assert mock_asyncio.run.called
    # menu function was referenced (it's the thing passed to asyncio.run)
    mock_menu.assert_called_once()


# ---------------------------------------------------------------------------
# /goal aliases: /kibble, /chow
# ---------------------------------------------------------------------------


def test_goal_command_has_puppy_themed_aliases():
    """`/kibble` and `/chow` must resolve to the same CommandInfo as `/goal`.

    These are puppy-themed aliases for /goal so users can pick whichever
    feels most natural. They MUST share the same handler so behavior is
    identical \u2014 if they ever diverge, that's a bug.
    """
    from code_puppy.command_line.command_registry import get_all_commands

    # Importing the plugin module triggers @register_command via side-effect.
    import code_puppy.plugins.wiggum.register_callbacks  # noqa: F401

    cmds = get_all_commands()
    goal = cmds.get("goal")
    assert goal is not None, "/goal command should be registered"
    assert "kibble" in goal.aliases
    assert "chow" in goal.aliases

    # Both aliases must resolve to the SAME CommandInfo object, not a copy.
    # (Same identity guarantees same handler, same description, same usage.)
    assert cmds.get("kibble") is goal
    assert cmds.get("chow") is goal


def test_prompt_extraction_is_command_word_agnostic():
    """_extract_prompt drops the first whitespace-delimited token, so the
    same prompt is extracted regardless of which alias the user typed."""
    from code_puppy.plugins.wiggum.register_callbacks import _extract_prompt

    expected = "make the tests pass for the auth flow"
    assert _extract_prompt(f"/goal {expected}") == expected
    assert _extract_prompt(f"/kibble {expected}") == expected
    assert _extract_prompt(f"/chow {expected}") == expected


def test_usage_hint_mentions_aliases():
    """When the user types `/goal` (or an alias) with no prompt, the usage
    hint should advertise the aliases so they're discoverable."""
    from unittest.mock import patch

    from code_puppy.plugins.wiggum.register_callbacks import handle_goal_command

    captured: list[str] = []

    def capture(msg, *_a, **_kw):
        captured.append(msg)

    with (
        patch(
            "code_puppy.plugins.wiggum.register_callbacks.emit_warning",
            side_effect=capture,
        ),
        patch(
            "code_puppy.plugins.wiggum.register_callbacks.emit_info",
            side_effect=capture,
        ),
    ):
        # Empty prompt triggers the usage hint.
        result = handle_goal_command("/goal")

    assert result is True  # command consumed, no prompt to dispatch
    joined = " ".join(captured)
    assert "/kibble" in joined
    assert "/chow" in joined
