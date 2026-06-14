"""Phase 3: reusable FilterableListScreen + /model menu interception."""

import pytest

from code_puppy.tui.app import build_app
from code_puppy.tui.menus import open_autosave_picker
from code_puppy.tui.screens.base import FilterableListScreen, ListChoice


@pytest.mark.asyncio
async def test_filterable_list_filters_and_selects():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        chosen = []
        app.push_screen(
            FilterableListScreen(
                "Pick",
                [ListChoice("a", "Apple"), ListChoice("b", "Banana")],
            ),
            lambda r: chosen.append(r),
        )
        await pilot.pause(0.1)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"ban")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert chosen == ["b"]


@pytest.mark.asyncio
async def test_filterable_list_escape_returns_none():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        chosen = []
        app.push_screen(
            FilterableListScreen("Pick", [ListChoice("a", "Apple")]),
            lambda r: chosen.append(r),
        )
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert chosen == [None]


@pytest.mark.asyncio
async def test_model_command_opens_modal():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/model")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_model_command_applies_selection(monkeypatch):
    applied = {}
    monkeypatch.setattr(
        "code_puppy.model_switching.set_model_and_reload_agent",
        lambda model: applied.setdefault("model", model),
    )
    # Force a known model list + active so selection differs from active.
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["alpha", "beta"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.get_active_model",
        lambda: "alpha",
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/model")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"beta")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert applied.get("model") == "beta"


def _stub_agents(monkeypatch, current="code-puppy"):
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_available_agents",
        lambda: {"code-puppy": "Code Puppy", "helios": "Helios"},
    )
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: current,
    )


@pytest.mark.asyncio
async def test_agent_command_opens_modal(monkeypatch):
    _stub_agents(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/agent")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_agent_alias_opens_modal(monkeypatch):
    _stub_agents(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/a")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_agent_selection_switches(monkeypatch):
    _stub_agents(monkeypatch, current="code-puppy")
    switched = {}
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.set_current_agent",
        lambda name: switched.setdefault("to", name) or True,
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/agent")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"helios")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert switched.get("to") == "helios"


@pytest.mark.asyncio
async def test_autosave_picker_opens(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.session_storage.list_sessions",
        lambda base: ["sess-a", "sess-b"],
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        open_autosave_picker(app)
        await pilot.pause(0.1)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_autosave_select_loads(monkeypatch):
    loaded = {}
    monkeypatch.setattr(
        "code_puppy.session_storage.list_sessions",
        lambda base: ["sess-a", "sess-b"],
    )
    monkeypatch.setattr(
        "code_puppy.session_storage.load_session",
        lambda name, base: ["m1", "m2"],
    )

    class _Agent:
        def set_message_history(self, h):
            loaded["hist"] = h

    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: _Agent())
    monkeypatch.setattr(
        "code_puppy.config.set_current_autosave_from_session_name",
        lambda name: loaded.setdefault("name", name),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        open_autosave_picker(app)
        await pilot.pause(0.1)
        await pilot.press(*"sess-b")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert loaded.get("name") == "sess-b"
    assert loaded.get("hist") == ["m1", "m2"]


@pytest.mark.asyncio
async def test_autosave_no_sessions_no_modal(monkeypatch):
    monkeypatch.setattr("code_puppy.session_storage.list_sessions", lambda base: [])
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        open_autosave_picker(app)
        await pilot.pause(0.1)
        assert not isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_colors_command_opens_banner_picker():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/colors")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_colors_three_step_applies(monkeypatch):
    applied = {}
    monkeypatch.setattr(
        "code_puppy.config.set_banner_color",
        lambda banner, color: applied.update({"banner": banner, "color": color}),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/colors")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"thinking")
        await pilot.pause(0.1)
        await pilot.press("enter")  # choose the banner
        await pilot.pause(0.1)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"blue")
        await pilot.pause(0.1)
        await pilot.press("enter")  # choose the color
        await pilot.pause(0.1)
    assert applied.get("banner") == "thinking"
    assert applied.get("color")


@pytest.mark.asyncio
async def test_diff_command_opens_color_picker(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_diff_addition_color", lambda: "#000000")
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/diff")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_diff_two_step_applies_both_colors(monkeypatch):
    applied = {}
    monkeypatch.setattr("code_puppy.config.get_diff_addition_color", lambda: "#000000")
    monkeypatch.setattr("code_puppy.config.get_diff_deletion_color", lambda: "#111111")
    monkeypatch.setattr(
        "code_puppy.config.set_diff_addition_color",
        lambda c: applied.__setitem__("add", c),
    )
    monkeypatch.setattr(
        "code_puppy.config.set_diff_deletion_color",
        lambda c: applied.__setitem__("del", c),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/diff")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press("enter")  # choose first addition color
        await pilot.pause(0.1)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press("enter")  # choose first deletion color
        await pilot.pause(0.1)
    assert "add" in applied and "del" in applied
    assert applied["add"].startswith("#") and applied["del"].startswith("#")


@pytest.mark.asyncio
async def test_set_command_opens_key_picker():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/set")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_set_flow_applies_value(monkeypatch):
    from types import SimpleNamespace

    from textual.widgets import Input

    from code_puppy.tui.screens.interactive import TextInputModal

    applied = {}
    monkeypatch.setattr(
        "code_puppy.command_line.config_apply.apply_setting",
        lambda key, value, reload_agent=True: (
            applied.update({"key": key, "value": value})
            or SimpleNamespace(ok=True, error=None)
        ),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/set")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"yolo_mode")
        await pilot.pause(0.1)
        await pilot.press("enter")  # choose the key
        await pilot.pause(0.1)
        assert isinstance(app.screen, TextInputModal)
        app.screen.query_one("#value", Input).value = "true"
        await pilot.press("enter")  # submit the value
        await pilot.pause(0.1)
    assert applied.get("key") == "yolo_mode"
    assert applied.get("value") == "true"


@pytest.mark.asyncio
async def test_model_command_with_arg_falls_through(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command",
        lambda cmd: calls.append(cmd) or True,
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/model some-model")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, FilterableListScreen)
        assert calls == ["/model some-model"]
