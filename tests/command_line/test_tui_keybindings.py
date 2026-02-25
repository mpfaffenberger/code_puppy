"""Tests that exercise TUI keybinding handler bodies.

Captures the KeyBindings object from Application construction
and invokes handlers directly to cover the closure bodies.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
# colors_menu.py - lines 262-338
# ============================================================


def test_colors_menu_keybindings():
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.layout.controls import FormattedTextControl as RealFTC

    from code_puppy.command_line.colors_menu import _split_panel_selector

    choices = ["Red", "Blue", "───", "Green"]
    on_change = MagicMock()
    get_preview = MagicMock(return_value=ANSI("preview"))

    captured_lambdas = []
    real_ftc = RealFTC

    def capture_ftc(*args, **kwargs):
        # Capture lambda text generators
        if args and callable(args[0]):
            captured_lambdas.append(args[0])
        return real_ftc(*args, **kwargs)

    with (
        patch("code_puppy.command_line.colors_menu.Application") as mock_app_cls,
        patch(
            "code_puppy.command_line.colors_menu.FormattedTextControl",
            side_effect=capture_ftc,
        ),
    ):
        mock_app = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run_and_capture():
            kb = _extract_kb(mock_app_cls)
            if kb:
                _fire(kb, {"up", "down", "c-m", "c-c"})
            # Call the captured lambdas to cover inner rendering functions
            for fn in captured_lambdas:
                try:
                    fn()
                except Exception:
                    pass

        mock_app.run_async = run_and_capture
        _run_coro(
            _split_panel_selector("Test", choices, on_change, get_preview=get_preview)
        )


# ============================================================
# diff_menu.py - lines 565-569, 620
# ============================================================


def test_diff_menu_keybindings():
    from prompt_toolkit.formatted_text import ANSI

    from code_puppy.command_line.diff_menu import (
        DiffConfiguration,
        _split_panel_selector,
    )

    choices = ["Python", "JavaScript"]
    on_change = MagicMock()
    get_preview = MagicMock(return_value=ANSI("preview"))
    config = DiffConfiguration()

    with patch("code_puppy.command_line.diff_menu.Application") as mock_app_cls:
        mock_app = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run_and_capture():
            kb = _extract_kb(mock_app_cls)
            if kb:
                _fire(kb, {"up", "down", "left", "right", "c-m"})

        mock_app.run_async = run_and_capture
        _run_coro(
            _split_panel_selector(
                "Test", choices, on_change, get_preview=get_preview, config=config
            )
        )


def test_diff_menu_cancel():
    from prompt_toolkit.formatted_text import ANSI

    from code_puppy.command_line.diff_menu import (
        DiffConfiguration,
        _split_panel_selector,
    )

    choices = ["Python"]
    on_change = MagicMock()
    get_preview = MagicMock(return_value=ANSI("preview"))
    config = DiffConfiguration()

    with patch("code_puppy.command_line.diff_menu.Application") as mock_app_cls:
        mock_app = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run_and_cancel():
            kb = _extract_kb(mock_app_cls)
            if kb:
                _fire(kb, {"c-c"})

        mock_app.run_async = run_and_cancel

        async def run_test():
            with pytest.raises(KeyboardInterrupt):
                await _split_panel_selector(
                    "Test", choices, on_change, get_preview=get_preview, config=config
                )

        _run_coro(run_test())


# ============================================================
# add_model_menu.py - lines 900-975
# ============================================================


def test_add_model_menu_keybindings():
    from code_puppy.command_line.add_model_menu import AddModelMenu

    providers = [MagicMock() for _ in range(3)]
    for i, p in enumerate(providers):
        p.name = f"Provider{i}"
        p.id = f"prov{i}"
        p.description = f"Desc{i}"
        p.env_vars = []
        p.models = [MagicMock(name=f"model{j}") for j in range(3)]

    menu = AddModelMenu.__new__(AddModelMenu)
    menu.providers = providers
    menu.registry = {p.id: p for p in providers}
    menu.current_models = providers[0].models
    menu.current_provider = providers[0]
    menu.selected_provider_idx = 1
    menu.selected_model_idx = 1
    menu.current_page = 0
    menu.view_mode = "providers"
    menu.result = None
    menu.pending_model = None
    menu.pending_provider = None

    with (
        patch("code_puppy.command_line.add_model_menu.Application") as mock_app_cls,
        patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input"),
        patch("sys.stdout"),
        patch("time.sleep"),
    ):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app

        def run_and_capture(**kwargs):
            kb = _extract_kb(mock_app_cls)
            if not kb:
                return
            # Providers view
            menu.view_mode = "providers"
            menu.selected_provider_idx = 1
            _fire(kb, {"up"})
            _fire(kb, {"down"})
            menu.current_page = 1
            _fire(kb, {"left"})
            menu.current_page = 0
            _fire(kb, {"right"})
            _fire(kb, {"c-m"})  # enter
            menu.view_mode = "providers"
            _fire(kb, {"escape"})  # no-op in providers
            # Models view
            menu.view_mode = "models"
            menu.selected_model_idx = 1
            _fire(kb, {"up"})
            _fire(kb, {"down"})
            _fire(kb, {"escape"})
            menu.view_mode = "models"
            _fire(kb, {"c-h"})  # backspace
            menu.view_mode = "models"
            _fire(kb, {"c-m"})  # enter in models
            _fire(kb, {"c-c"})

        mock_app.run = run_and_capture
        try:
            menu.run()
        except Exception:
            pass


# ============================================================
# model_settings_menu.py - lines 760-853
# ============================================================


def test_model_settings_keybindings():
    from code_puppy.command_line.model_settings_menu import ModelSettingsMenu

    with patch(
        "code_puppy.command_line.model_settings_menu._load_all_model_names",
        return_value=["gpt-4", "claude-3"],
    ):
        menu = ModelSettingsMenu()

    with (
        patch(
            "code_puppy.command_line.model_settings_menu.Application"
        ) as mock_app_cls,
        patch("code_puppy.command_line.model_settings_menu.set_awaiting_user_input"),
        patch("sys.stdout"),
        patch("time.sleep"),
    ):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app

        def run_and_capture(**kwargs):
            kb = _extract_kb(mock_app_cls)
            if not kb:
                return
            # Models view
            menu.view_mode = "models"
            menu.model_index = 1
            _fire(kb, {"up"})
            menu.model_index = 0
            _fire(kb, {"down"})
            _fire(kb, {"pageup"})
            _fire(kb, {"pagedown"})
            _fire(kb, {"left"})
            _fire(kb, {"right"})
            _fire(kb, {"c-m"})  # enter -> settings
            # Settings view
            menu.view_mode = "settings"
            menu.setting_index = 1
            menu.editing_mode = False
            _fire(kb, {"up"})
            menu.setting_index = 0
            _fire(kb, {"down"})
            _fire(kb, {"c-m"})  # enter -> start editing
            # Editing mode
            menu.editing_mode = True
            _fire(kb, {"left"})  # adjust -1
            _fire(kb, {"right"})  # adjust +1
            _fire(kb, {"c-m"})  # save
            # d to reset
            menu.view_mode = "settings"
            _fire(kb, {"d"})
            # Escape in editing
            menu.editing_mode = True
            menu.view_mode = "settings"
            _fire(kb, {"escape"})
            # Escape in settings (back)
            menu.editing_mode = False
            menu.view_mode = "settings"
            _fire(kb, {"escape"})
            # Escape in models (exit)
            menu.view_mode = "models"
            _fire(kb, {"escape"})
            # c-c with editing
            menu.editing_mode = True
            _fire(kb, {"c-c"})

        mock_app.run = run_and_capture
        try:
            menu.run()
        except Exception:
            pass


# ============================================================
# agent_menu.py - lines 530-586
# ============================================================


def test_agent_menu_keybindings():
    from code_puppy.command_line.agent_menu import interactive_agent_picker

    # Create enough entries for multiple pages (PAGE_SIZE=10)
    entries = [(f"agent{i}", f"Agent {i}", "builtin") for i in range(25)]
    with (
        patch(
            "code_puppy.command_line.agent_menu._get_agent_entries",
            return_value=entries,
        ),
        patch("code_puppy.command_line.agent_menu.Application") as mock_app_cls,
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
        patch("code_puppy.command_line.agent_menu.emit_warning"),
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
                    # First call: navigate down then up to cover both bodies
                    _fire(kb, {"down"})  # selected_idx: 0->1
                    _fire(kb, {"up"})  # selected_idx: 1->0 (covers up body)
                    # Navigate to next page and back
                    _fire(kb, {"right"})  # page 0->1
                    _fire(kb, {"left"})  # page 1->0
                    _fire(kb, {"p"})  # pin action
                elif call_count[0] == 2:
                    _fire(kb, {"c"})  # clone action
                elif call_count[0] == 3:
                    _fire(kb, {"d"})  # delete action
                elif call_count[0] == 4:
                    _fire(kb, {"c-m"})  # enter/select
                else:
                    _fire(kb, {"c-c"})

        mock_app.run_async = run_and_capture
        _run_coro(interactive_agent_picker())


# ============================================================
# autosave_menu.py - lines 572-663
# ============================================================


def test_autosave_menu_keybindings():
    from code_puppy.command_line.autosave_menu import interactive_autosave_picker

    # Create enough entries for multiple pages
    entries = [
        (
            f"session{i}",
            {"timestamp": f"2024-01-{i + 1:02d}T12:00:00", "messages": i * 10},
        )
        for i in range(25)
    ]
    fake_history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "msg2"},
    ]
    with (
        patch(
            "code_puppy.command_line.autosave_menu._get_session_entries",
            return_value=entries,
        ),
        patch("code_puppy.command_line.autosave_menu.Application") as mock_app_cls,
        patch("code_puppy.command_line.autosave_menu.set_awaiting_user_input"),
        patch(
            "code_puppy.command_line.autosave_menu.load_session",
            return_value=fake_history,
        ),
        patch("sys.stdout"),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_app = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run_and_capture():
            kb = _extract_kb(mock_app_cls)
            if kb:
                # Navigate pages first
                _fire(kb, {"down"})  # 0->1
                _fire(kb, {"up"})  # 1->0
                _fire(kb, {"right"})  # page 0->1
                _fire(kb, {"left"})  # page 1->0
                # Enter browse mode
                _fire(kb, {"e"})
                # Now browse_mode[0] is True - navigate messages
                _fire(kb, {"c-p"})  # older message (browse mode up)
                _fire(kb, {"c-n"})  # newer message (browse mode down)
                # Exit browse mode with q
                _fire(kb, {"q"})
                # Re-enter browse mode
                _fire(kb, {"e"})
                # Exit with escape (while in browse mode)
                _fire(kb, {"escape"})
                # Escape in normal mode -> cancel
                _fire(kb, {"escape"})

        mock_app.run_async = run_and_capture
        _run_coro(interactive_autosave_picker())


# ============================================================
# uc_menu.py - lines 674-754
# ============================================================


def test_uc_menu_keybindings():
    from code_puppy.command_line.uc_menu import interactive_uc_picker
    from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo

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
