"""Behavior tests for the 4 TUI parity gaps fixed in this branch.

Each test answers: "What user-visible behavior would break if this fix is
reverted?" — not just "did the function get called."
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import Static

from code_puppy.tui.app import build_app


# ---------------------------------------------------------------------------
# Gap #3 — spinner uses the active catalogue (not the deprecated shim)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spinner_uses_active_catalogue_frames():
    """_render_spinner pulls frames from puppy_spinner.spinners, not FRAMES."""
    custom_frames = ("[@]", "[A]", "[@]")
    fake_spinner = MagicMock()
    fake_spinner.frames = custom_frames
    fake_spinner.interval = 0.05

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        with patch(
            "code_puppy.plugins.puppy_spinner.register_callbacks._current_frames_and_interval",
            return_value=(custom_frames, 0.05),
        ):
            app._spinner_frame = 0
            app._set_busy(True)
            await pilot.pause()
            app._render_spinner()
            await pilot.pause()
            widget = app.query_one("#spinner", Static)
            rendered = widget.render()
            text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
            assert "[@]" in text, (
                f"Expected custom frame '[@]' in spinner, got: {text!r}"
            )
        app._set_busy(False)


@pytest.mark.asyncio
async def test_spinner_falls_back_gracefully_when_plugin_unavailable():
    """_render_spinner still works even if puppy_spinner plugin isn't loaded."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._set_busy(True)
        await pilot.pause()
        widget = app.query_one("#spinner", Static)
        rendered = widget.render()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        assert "thinking" in text, f"Spinner should show 'thinking' text, got: {text!r}"
        app._set_busy(False)


# ---------------------------------------------------------------------------
# Gap #4 — turn-boundary hooks fire in TUI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interactive_turn_end_fires_on_successful_turn():
    """on_interactive_turn_end is called after a turn completes."""
    from code_puppy.callbacks import register_callback, unregister_callback

    turn_end_calls = []

    async def _capture(*args, success=True, error=None, **kwargs):
        turn_end_calls.append({"success": success, "error": error})

    register_callback("interactive_turn_end", _capture)
    try:
        fake_result = MagicMock()
        fake_result.output = "done"
        fake_result.all_messages.return_value = []

        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            with (
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    new_callable=AsyncMock,
                    return_value=(fake_result, MagicMock()),
                ),
                patch("code_puppy.agents.get_current_agent", return_value=MagicMock()),
                patch("code_puppy.config.auto_save_session_if_enabled"),
            ):
                app.submit_prompt("hello")
                # Wait for the worker to finish.
                await pilot.pause(0.5)
                # Give the event loop a tick to drain turn-end hook.
                await asyncio.sleep(0.05)

        assert len(turn_end_calls) >= 1, "on_interactive_turn_end never fired"
        assert turn_end_calls[0]["success"] is True
        assert turn_end_calls[0]["error"] is None
    finally:
        unregister_callback("interactive_turn_end", _capture)


@pytest.mark.asyncio
async def test_interactive_turn_cancel_fires_when_result_is_none():
    """on_interactive_turn_cancel fires when run_prompt returns None (cancelled)."""
    from code_puppy.callbacks import register_callback, unregister_callback

    cancel_calls = []

    async def _capture(prompt, *, reason="cancelled"):
        cancel_calls.append(reason)

    register_callback("interactive_turn_cancel", _capture)
    try:
        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            with (
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    new_callable=AsyncMock,
                    return_value=(None, MagicMock()),
                ),
                patch("code_puppy.agents.get_current_agent", return_value=MagicMock()),
                patch("code_puppy.config.auto_save_session_if_enabled"),
            ):
                app.submit_prompt("hello")
                await pilot.pause(0.5)
                await asyncio.sleep(0.05)

        assert len(cancel_calls) >= 1, "on_interactive_turn_cancel never fired"
        assert cancel_calls[0] == "cancellation"
    finally:
        unregister_callback("interactive_turn_cancel", _capture)


@pytest.mark.asyncio
async def test_continuation_loop_re_runs_on_plugin_request():
    """If on_interactive_turn_end returns a continuation dict, the TUI re-runs."""
    from code_puppy.callbacks import register_callback, unregister_callback

    run_count = 0
    turn_end_count = 0

    async def _turn_end(agent, prompt, result, *, success=True, error=None):
        nonlocal turn_end_count
        turn_end_count += 1
        # Return continuation only on first call.
        if turn_end_count == 1:
            return {"prompt": "continuation prompt", "delay": 0}
        return None

    register_callback("interactive_turn_end", _turn_end)
    try:
        fake_result = MagicMock()
        fake_result.output = "ok"
        fake_result.all_messages.return_value = []

        async def _fake_run(*args, **kwargs):
            nonlocal run_count
            run_count += 1
            return fake_result, MagicMock()

        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            with (
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    side_effect=_fake_run,
                ),
                patch("code_puppy.agents.get_current_agent", return_value=MagicMock()),
                patch("code_puppy.config.auto_save_session_if_enabled"),
            ):
                app.submit_prompt("first")
                await pilot.pause(1.0)
                await asyncio.sleep(0.1)

        # The agent ran twice: original prompt + continuation.
        assert run_count >= 2, (
            f"Expected 2 runs (original + continuation), got {run_count}"
        )
    finally:
        unregister_callback("interactive_turn_end", _turn_end)


# ---------------------------------------------------------------------------
# Gap #1 — sub-agent live panel renders in TUI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subagent_panel_becomes_visible_when_lines_pushed():
    """When subagent_panel_lines_changed fires with content, the panel shows."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#subagent-panel", Static)
        assert not widget.has_class("visible"), "Panel should start hidden"

        # Simulate the hook firing with panel lines.
        from rich.text import Text

        lines = [Text("🤖 agent  claude  ⠿ 00:03  reading files")]
        app._on_subagent_panel_lines_changed(lines)
        await pilot.pause()

        assert widget.has_class("visible"), "Panel should be visible after lines pushed"
        rendered = widget.render()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        assert "agent" in text or "reading" in text, (
            f"Panel should contain agent text, got: {text!r}"
        )


@pytest.mark.asyncio
async def test_subagent_panel_hides_when_empty_lines_pushed():
    """When empty lines are pushed, the panel hides."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#subagent-panel", Static)

        from rich.text import Text

        # Show it first.
        app._on_subagent_panel_lines_changed([Text("agent row")])
        await pilot.pause()
        assert widget.has_class("visible")

        # Clear it.
        app._on_subagent_panel_lines_changed([])
        await pilot.pause()
        assert not widget.has_class("visible"), "Panel should hide when no lines"


# ---------------------------------------------------------------------------
# Idle queue drain — queued prompts auto-run after current turn ends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queued_prompt_auto_submits_after_turn_completes():
    """A queued prompt is auto-submitted as the next turn when the TUI goes idle."""
    from code_puppy.messaging.pause_controller import (
        get_pause_controller,
        reset_pause_controller,
    )

    reset_pause_controller()
    try:
        # Seed a queued prompt BEFORE the turn runs.
        get_pause_controller().request_steer("queued follow-up", mode="queue")

        submitted_prompts = []
        fake_result = MagicMock()
        fake_result.output = "ok"
        fake_result.all_messages.return_value = []

        async def _fake_run(_agent, prompt, *args, **kwargs):
            submitted_prompts.append(prompt)
            return fake_result, MagicMock()

        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            with (
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    side_effect=_fake_run,
                ),
                patch("code_puppy.agents.get_current_agent", return_value=MagicMock()),
                patch("code_puppy.config.auto_save_session_if_enabled"),
            ):
                app.submit_prompt("first prompt")
                # Wait for both turns (original + auto-queued) to complete.
                await pilot.pause(1.0)
                await asyncio.sleep(0.1)

        assert len(submitted_prompts) >= 2, (
            f"Expected 2 runs (original + queued), got {len(submitted_prompts)}: "
            f"{submitted_prompts}"
        )
        assert submitted_prompts[0] == "first prompt"
        assert submitted_prompts[1] == "queued follow-up"
    finally:
        reset_pause_controller()


@pytest.mark.asyncio
async def test_queued_prompt_not_swallowed_on_cancel():
    """A queued prompt is NOT auto-consumed when the turn is cancelled (result=None)."""
    from code_puppy.messaging.pause_controller import (
        get_pause_controller,
        reset_pause_controller,
    )

    reset_pause_controller()
    try:
        get_pause_controller().request_steer("should stay", mode="queue")

        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            with (
                patch(
                    "code_puppy.cli_runner.run_prompt_with_attachments",
                    new_callable=AsyncMock,
                    return_value=(None, MagicMock()),
                ),
                patch("code_puppy.agents.get_current_agent", return_value=MagicMock()),
                patch("code_puppy.config.auto_save_session_if_enabled"),
            ):
                app.submit_prompt("cancels")
                await pilot.pause(0.5)
                await asyncio.sleep(0.05)

            # Queue should still contain the item — cancel must not drain it.
            remaining = get_pause_controller().peek_pending_steer_queued()
            assert remaining == ["should stay"], (
                f"Queue was wrongly drained on cancel: {remaining}"
            )
    finally:
        reset_pause_controller()


@pytest.mark.asyncio
async def test_subagent_panel_registered_and_unregistered_with_lifecycle():
    """The subagent_panel_lines_changed hook is registered on mount, removed on unmount."""
    from code_puppy.callbacks import get_callbacks

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        handlers = get_callbacks("subagent_panel_lines_changed")
        assert any(getattr(h, "__self__", None) is app for h in handlers), (
            "App's handler not found in subagent_panel_lines_changed callbacks during run"
        )

    # After unmount, the handler should be gone.
    handlers_after = get_callbacks("subagent_panel_lines_changed")
    app_handlers = [h for h in handlers_after if getattr(h, "__self__", None) is app]
    assert not app_handlers, "Handler still registered after app unmount"
