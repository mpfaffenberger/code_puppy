"""Awaiting-input flags that observer plugins (herdr, notifiers) read."""

from __future__ import annotations

from unittest.mock import patch

from code_puppy import callbacks
from code_puppy.tools import command_runner


def test_every_wait_fires_the_awaiting_user_input_hook(monkeypatch):
    """The single choke point observers (herdr, notifiers) rely on."""
    seen: list[bool] = []
    monkeypatch.setitem(callbacks._callbacks, "awaiting_user_input", [])
    callbacks.register_callback("awaiting_user_input", seen.append)
    command_runner.set_awaiting_user_input(True)
    command_runner.set_awaiting_user_input(False)
    assert seen == [True, False]


def test_user_initiated_menus_wait_without_notifying():
    try:
        command_runner.set_awaiting_user_input(True, notify=False)
        assert command_runner.is_awaiting_user_input()
        assert not command_runner.should_notify_awaiting_user_input()
        command_runner.set_awaiting_user_input(True)
        assert command_runner.should_notify_awaiting_user_input()
    finally:
        command_runner.set_awaiting_user_input(False)


def test_panel_teardown_never_raises_from_the_sigint_path():
    with patch(
        "code_puppy.messaging.bottom_bar.get_bottom_bar",
        side_effect=RuntimeError("no bar"),
    ):
        command_runner._tear_down_live_panels()  # must swallow
