"""Phase 3: the register_screen plugin hook."""

import pytest

from code_puppy.callbacks import register_callback, unregister_callback
from code_puppy.messaging import UserInputRequest
from code_puppy.tui.app import build_app
from code_puppy.tui.menus import get_menu_opener
from code_puppy.tui.screens.interactive import TextInputModal


def test_get_menu_opener_resolves_builtin_and_plugin():
    assert get_menu_opener("model") is not None  # builtin
    assert get_menu_opener("/model") is not None  # leading slash tolerated
    assert get_menu_opener("definitely-not-a-menu") is None

    def cb():
        return [{"command": "zztool", "open": lambda app: None}]

    register_callback("register_screen", cb)
    try:
        assert get_menu_opener("zztool") is not None
        assert get_menu_opener("nope-still-unknown") is None
    finally:
        unregister_callback("register_screen", cb)


@pytest.mark.asyncio
async def test_plugin_screen_opens_via_command():
    opened = {}

    def opener(app):
        opened["yes"] = True
        app.push_screen(
            TextInputModal(UserInputRequest(prompt_id="x", prompt_text="hi"))
        )

    def cb():
        return [{"command": "mytool", "open": opener, "aliases": ["mt"]}]

    register_callback("register_screen", cb)
    try:
        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.submit_prompt("/mt")  # alias resolves to the same opener
            await pilot.pause(0.1)
            assert opened.get("yes") is True
            assert isinstance(app.screen, TextInputModal)
    finally:
        unregister_callback("register_screen", cb)


@pytest.mark.asyncio
async def test_plugin_screen_with_args_falls_through():
    calls = []

    def cb():
        return [{"command": "mytool", "open": lambda app: calls.append("opened")}]

    register_callback("register_screen", cb)
    try:
        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            # With an argument, the menu opener must NOT fire (falls through).
            app._dispatch_command("/mytool somearg")
            await pilot.pause(0.1)
            assert calls == []
    finally:
        unregister_callback("register_screen", cb)
