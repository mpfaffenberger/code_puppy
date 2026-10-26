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
