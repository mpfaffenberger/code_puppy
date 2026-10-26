"""Menu navigation is silent; actual results and failures remain visible."""

from contextlib import nullcontext
from unittest.mock import AsyncMock, Mock

import pytest

from code_puppy.i18n import t
from code_puppy.messaging import message_queue, run_ui
from code_puppy.messaging.menu_lifecycle import _LEGACY_CLOSE_NOTICES


@pytest.mark.parametrize(
    "notice",
    [
        *_LEGACY_CLOSE_NOTICES,
        t("model_menu.browser.exited"),
        t("cmd.model_settings.agent_reloaded"),
        t("cmd.model.success", model="codex-test"),
    ],
)
def test_legacy_close_notices_never_enter_queue(monkeypatch, notice):
    queue = Mock()
    monkeypatch.setattr(message_queue, "get_global_queue", lambda: queue)
    message_queue.emit_info(notice)
    message_queue.emit_success(notice)
    queue.emit_simple.assert_not_called()


@pytest.mark.parametrize("kind", [message_queue.emit_info, message_queue.emit_error])
def test_real_output_is_preserved(monkeypatch, kind):
    queue = Mock()
    monkeypatch.setattr(message_queue, "get_global_queue", lambda: queue)
    kind("Failed to save configuration")
    queue.emit_simple.assert_called_once()


@pytest.mark.parametrize("paused", [True, False])
@pytest.mark.asyncio
async def test_menu_pause_resume_is_silent(monkeypatch, paused):
    from code_puppy.messaging import bus, pause_controller

    messages = Mock()
    pc = Mock()
    pc.is_paused.return_value = paused
    editor = Mock()
    editor.get_pending_command.return_value = None
    monkeypatch.setattr(bus, "get_message_bus", lambda: messages)
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: pc)
    monkeypatch.setattr(run_ui, "_await_parked", AsyncMock())
    monkeypatch.setattr(run_ui, "suspended_run_ui", nullcontext)
    monkeypatch.setattr(run_ui, "_execute_command", lambda cmd: True)
    monkeypatch.setattr(run_ui, "_handle_command_result", Mock())
    emit = Mock()
    monkeypatch.setattr(message_queue, "emit_info", emit)
    monkeypatch.setattr(message_queue, "emit_warning", emit)
    await run_ui._run_paused_commands(editor, "/queue")
    emit.assert_not_called()
    assert messages.provide_response.call_count == 2
