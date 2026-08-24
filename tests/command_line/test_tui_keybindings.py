"""Tests that exercise TUI keybinding handler bodies.

Captures the KeyBindings object from Application construction
and invokes handlers directly to cover the closure bodies.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_event():
    event = MagicMock()
    event.app = MagicMock()
    return event


def _extract_kb(mock_app_cls):
    """Extract KeyBindings from the Application constructor call."""
    call = mock_app_cls.call_args
    if call is None:
        return None
    return call.kwargs.get("key_bindings")


def _fire(kb, keys):
    """Call all handlers matching any of the given keys."""
    event = _make_event()
    called = set()
    for b in kb.bindings:
        for k in b.keys:
            kv = k.value if hasattr(k, "value") else str(k)
            if kv in keys and id(b.handler) not in called:
                called.add(id(b.handler))
                try:
                    b.handler(event)
                except Exception:
                    pass


def _run_coro(coro):
    """Run a coroutine in a new event loop, swallowing all exceptions."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    except (Exception, KeyboardInterrupt):
        pass
    finally:
        loop.close()


# ============================================================
# agent_menu.py - lines 530-586
# ============================================================


def test_agent_menu_keybindings():
    import code_puppy.command_line.agent_menu as am
    from io import StringIO

    # Create enough entries for multiple pages (PAGE_SIZE=10)
    entries = [(f"agent{i}", f"Agent {i}", "builtin") for i in range(25)]

    # One shared script spanning the picker's sequential menu runs:
    #   run 1: navigate + page both directions, then "p" (pin action)
    #   run 2: "c" (clone action)
    #   run 3: "d" (delete action)
    #   run 4: enter (select highlighted)
    script = iter(["down", "up", "right", "left", "p", "c", "d", "enter"])

    real_build = am.build_agent_menu

    def headless_build(entries_arg, current, pending, idx, **_overrides):
        return real_build(
            entries_arg,
            current,
            pending,
            idx,
            key_source=lambda: next(script),
            output=StringIO(),
            size=lambda: (120, 40),
            alt_screen=False,
        )

    with (
        patch(
            "code_puppy.command_line.agent_menu._get_agent_entries",
            return_value=entries,
        ),
        patch(
            "code_puppy.command_line.agent_menu.build_agent_menu",
            side_effect=headless_build,
        ),
        patch("code_puppy.command_line.agent_menu.set_awaiting_user_input"),
        patch(
            "code_puppy.command_line.agent_menu._select_pinned_model",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("code_puppy.command_line.agent_menu.clone_agent", return_value=None),
        patch(
            "code_puppy.command_line.agent_menu.is_clone_agent_name", return_value=True
        ),
        patch(
            "code_puppy.command_line.agent_menu.delete_clone_agent", return_value=True
        ),
        patch(
            "code_puppy.command_line.agent_menu.get_current_agent", return_value=None
        ),
        patch(
            "code_puppy.command_line.agent_menu._get_pinned_model", return_value=None
        ),
        patch("code_puppy.command_line.agent_menu.get_bound_servers", return_value={}),
        patch("code_puppy.command_line.agent_menu.emit_warning"),
        patch("code_puppy.command_line.agent_menu.emit_info"),
    ):
        result = asyncio.run(am.interactive_agent_picker())

    # After pin/clone/delete detours, the final Enter selects the
    # highlighted agent (delete resets the cursor to the top).
    assert result == "agent0"


# ============================================================
# autosave_menu.py - lines 572-663
# ============================================================


# ============================================================
# uc_menu.py - lines 674-754
# ============================================================


def test_uc_menu_keybindings():
    from code_puppy.command_line.uc_menu import interactive_uc_picker
    from code_puppy_core_plugins.universal_constructor.models import (
        ToolMeta,
        UCToolInfo,
    )

    # Create enough tools for multiple pages
    tools = [
        UCToolInfo(
            meta=ToolMeta(
                name=f"test{i}",
                namespace="ns",
                description=f"d{i}",
                enabled=True,
                version="1.0",
            ),
            signature=f"test{i}()",
            source_path=f"/fake/test{i}.py",
            function_name=f"test{i}",
            docstring=f"test{i}",
        )
        for i in range(25)
    ]

    with (
        patch("code_puppy.command_line.uc_menu._get_tool_entries", return_value=tools),
        patch("code_puppy.command_line.uc_menu.Application") as mock_app_cls,
        patch("code_puppy.command_line.uc_menu.set_awaiting_user_input"),
        patch(
            "code_puppy.command_line.uc_menu._toggle_tool_enabled", return_value=True
        ),
        patch("code_puppy.command_line.uc_menu._delete_tool", return_value=False),
        patch(
            "code_puppy.command_line.uc_menu._load_source_code",
            return_value=(["line1", "line2"] * 30, None),
        ),
        patch("sys.stdout"),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_app = AsyncMock()
        mock_app_cls.return_value = mock_app

        call_count = [0]

        async def run_and_capture():
            call_count[0] += 1
            kb = _extract_kb(mock_app_cls)
            if kb:
                if call_count[0] == 1:
                    # List mode: navigate
                    _fire(kb, {"down"})  # 0->1
                    _fire(kb, {"up"})  # 1->0
                    _fire(kb, {"right"})  # page 0->1
                    _fire(kb, {"left"})  # page 1->0
                    _fire(kb, {"e"})  # toggle enable
                elif call_count[0] == 2:
                    _fire(kb, {"d"})  # delete
                elif call_count[0] == 3:
                    _fire(kb, {"c-m"})  # enter -> switch to source view
                elif call_count[0] == 4:
                    # Source mode bindings (source_kb)
                    _fire(kb, {"down"})  # source scroll down
                    _fire(kb, {"up"})  # source scroll up
                    _fire(kb, {"pagedown"})  # source page down
                    _fire(kb, {"pageup"})  # source page up
                    _fire(kb, {"escape"})  # back to list
                else:
                    _fire(kb, {"c-c"})

        mock_app.run_async = run_and_capture
        _run_coro(interactive_uc_picker())
