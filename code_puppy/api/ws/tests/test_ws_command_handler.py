from __future__ import annotations

import sys
from types import ModuleType

import pytest

from code_puppy.api.ws.ws_command_handler import handle_command_message


def _install_fake_command_handler(
    monkeypatch, *, help_text="Available commands", handle_result=True
):
    fake_module = ModuleType("code_puppy.command_line.command_handler")
    fake_module.get_commands_help = lambda: help_text
    fake_module.handle_command = lambda command: (
        handle_result(command) if callable(handle_result) else handle_result
    )
    monkeypatch.setitem(
        sys.modules, "code_puppy.command_line.command_handler", fake_module
    )


@pytest.mark.asyncio
async def test_handle_command_message_help_command(monkeypatch):
    sent = []
    _install_fake_command_handler(monkeypatch, help_text="usage text")

    class _FakeConsole:
        def __init__(self, *args, file=None, **_kwargs):
            self.file = file

        def print(self, value):
            self.file.write(f"plain:{value}")

    monkeypatch.setattr("code_puppy.api.ws.ws_command_handler.Console", _FakeConsole)

    async def _send_typed(message):
        sent.append(message)

    handled = await handle_command_message(
        msg={"type": "command", "command": "/help"},
        session_id="session-1",
        send_typed=_send_typed,
    )

    assert handled is True
    assert len(sent) == 1
    assert sent[0].command == "/help"
    assert sent[0].success is True
    assert sent[0].output == "plain:usage text"


@pytest.mark.asyncio
async def test_handle_command_message_runs_generic_command(monkeypatch):
    sent = []
    _install_fake_command_handler(
        monkeypatch, handle_result=lambda command: f"ran:{command}"
    )

    async def _send_typed(message):
        sent.append(message)

    handled = await handle_command_message(
        msg={"type": "command", "command": "/agents"},
        session_id="session-2",
        send_typed=_send_typed,
    )

    assert handled is True
    assert len(sent) == 1
    assert sent[0].command == "/agents"
    assert sent[0].success is True
    assert sent[0].output == "ran:/agents"


@pytest.mark.asyncio
async def test_handle_command_message_ignores_non_command_messages():
    sent = []

    async def _send_typed(message):
        sent.append(message)

    handled = await handle_command_message(
        msg={"type": "message", "content": "hello"},
        session_id="session-3",
        send_typed=_send_typed,
    )

    assert handled is False
    assert sent == []


@pytest.mark.asyncio
async def test_handle_command_message_reports_errors(monkeypatch):
    sent = []

    def _boom(_command):
        raise RuntimeError("boom")

    _install_fake_command_handler(monkeypatch, handle_result=_boom)

    async def _send_typed(message):
        sent.append(message)

    handled = await handle_command_message(
        msg={"type": "command", "command": "/broken"},
        session_id="session-4",
        send_typed=_send_typed,
    )

    assert handled is True
    assert len(sent) == 1
    assert sent[0].command == "/broken"
    assert sent[0].success is False
    assert sent[0].error == "boom"


@pytest.mark.asyncio
async def test_handle_command_message_treats_none_result_as_failure(monkeypatch):
    sent = []
    _install_fake_command_handler(monkeypatch, handle_result=lambda _command: None)

    async def _send_typed(message):
        sent.append(message)

    handled = await handle_command_message(
        msg={"type": "command", "command": "/noop"},
        session_id="session-5",
        send_typed=_send_typed,
    )

    assert handled is True
    assert len(sent) == 1
    assert sent[0].command == "/noop"
    assert sent[0].success is False
