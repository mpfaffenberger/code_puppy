"""Phase 4: legacy global-queue output reaches the TUI.

The classic renderers (which drain the legacy queue) aren't started in TUI
mode, so the app bridges the queue itself. Without this, emit_info/emit_warning
and QueueConsole.print output (used by many tools) would be invisible.
"""

import pytest

from code_puppy.messaging.message_queue import (
    MessageType,
    UIMessage,
    emit_info,
    get_global_queue,
)
from code_puppy.tui.app import build_app
from code_puppy.tui.screens.interactive import TextInputModal


def _log_text(app) -> str:
    return app.log_text()


@pytest.mark.asyncio
async def test_legacy_emit_info_reaches_the_tui():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.2)
        emit_info("legacy-bridge-marker-xyz")
        for _ in range(60):
            await pilot.pause(0.05)
            if "legacy-bridge-marker-xyz" in _log_text(app):
                break
        assert "legacy-bridge-marker-xyz" in _log_text(app)


@pytest.mark.asyncio
async def test_legacy_human_input_request_opens_modal_and_replies(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        get_global_queue(),
        "provide_prompt_response",
        lambda pid, val: captured.update(pid=pid, val=val),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.2)
        app.handle_legacy_message(
            UIMessage(
                type=MessageType.HUMAN_INPUT_REQUEST,
                content="Your name?",
                metadata={"prompt_id": "p1"},
            )
        )
        await pilot.pause(0.1)
        assert isinstance(app.screen, TextInputModal)
        await pilot.press(*"luc")
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert captured.get("pid") == "p1"
    assert captured.get("val") == "luc"


@pytest.mark.asyncio
async def test_user_approval_routes_through_bus_in_tui(monkeypatch):
    import asyncio

    monkeypatch.setattr("code_puppy.config.get_ui_mode", lambda: "textual")
    from code_puppy.tools.common import get_user_approval_async
    from code_puppy.tui.screens.interactive import ConfirmModal

    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.2)
        holder = {}

        async def ask():
            holder["r"] = await get_user_approval_async(
                "Edit file?", "Apply diff to x.py"
            )

        task = asyncio.create_task(ask())
        for _ in range(40):
            await pilot.pause(0.05)
            if isinstance(app.screen, ConfirmModal):
                break
        assert isinstance(app.screen, ConfirmModal)
        await pilot.click("#opt-0")  # Approve
        await asyncio.wait_for(task, timeout=3)
    assert holder["r"][0] is True
