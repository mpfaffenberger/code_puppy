from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic_ai import ToolReturn

from code_puppy.plugins.computer_use import register_callbacks
from code_puppy.plugins.computer_use import tools
from code_puppy.plugins.computer_use.geometry import CaptureGeometry, Rect
from code_puppy.plugins.computer_use.state import state_store


class FakeAgent:
    def __init__(self):
        self.registered = {}

    def tool(self, function):
        self.registered[function.__name__] = function
        return function


@pytest.fixture(autouse=True)
def disable_real_app_activation(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.backend.activate_state",
        lambda state: None,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.backend.policy_store.require_enabled",
        lambda: None,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.backend.policy_store.require",
        lambda bundle_id: None,
    )


def make_state(tmp_path, elements=None):
    state_store.clear()
    return state_store.create(
        application="TextEdit",
        bundle_id="com.apple.TextEdit",
        pid=123,
        window_id=456,
        window_title="Untitled",
        geometry=CaptureGeometry(Rect(100, 200, 800, 600), 1600, 1200, 2),
        screenshot_path=str(tmp_path / "state.png"),
        elements=elements or {},
    )


def test_plugin_registers_only_when_macos_user_opts_in(monkeypatch):
    monkeypatch.setattr(register_callbacks.sys, "platform", "linux")
    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: True)
    assert register_callbacks._register_tools() == []
    assert register_callbacks._register_agent_tools() == []
    assert register_callbacks._load_prompt() is None

    monkeypatch.setattr(register_callbacks.sys, "platform", "darwin")
    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: False)
    assert register_callbacks._register_tools() == []
    assert register_callbacks._register_agent_tools() == []
    assert register_callbacks._load_prompt() is None

    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: True)
    definitions = register_callbacks._register_tools()
    assert {item["name"] for item in definitions} == set(tools.REGISTRARS)
    assert set(register_callbacks._register_agent_tools()) == set(tools.REGISTRARS)
    prompt = register_callbacks._load_prompt()
    assert "always call the appropriate Computer Use state tool again" in prompt
    assert "tool's current result is authoritative" in prompt


def test_startup_explains_how_to_opt_in_on_macos(monkeypatch):
    messages = []
    monkeypatch.setattr(register_callbacks.sys, "platform", "darwin")
    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: False)
    monkeypatch.setattr(register_callbacks, "emit_info", messages.append)

    register_callbacks._startup()

    assert messages == [
        "macOS Computer Use is off by default. Run `/computer-use enable` to opt in."
    ]


def test_startup_is_silent_when_enabled_or_not_on_macos(monkeypatch):
    messages = []
    monkeypatch.setattr(register_callbacks, "emit_info", messages.append)
    monkeypatch.setattr(register_callbacks.sys, "platform", "darwin")
    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: True)
    register_callbacks._startup()

    monkeypatch.setattr(register_callbacks.sys, "platform", "linux")
    monkeypatch.setattr(register_callbacks.policy_store, "is_enabled", lambda: False)
    register_callbacks._startup()

    assert messages == []


def test_model_state_removes_repetitive_accessibility_bookkeeping():
    compact = tools._compact_state_for_model(
        {
            "success": True,
            "state_revision": "revision",
            "nodes": [
                {
                    "id": 7,
                    "depth": 18,
                    "source_order": 92,
                    "role": "AXButton",
                    "title": "",
                    "description": "Play",
                    "value": "",
                    "enabled": True,
                    "focused": False,
                    "actions": ["AXPress", "AXShowMenu", "AXScrollToVisible"],
                }
            ],
        }
    )
    assert compact["nodes"] == [
        {
            "id": 7,
            "role": "AXButton",
            "description": "Play",
            "actions": ["AXPress"],
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_registration():
    agent = FakeAgent()
    tools.register_snapshot(agent)
    with patch.object(
        tools.backend, "get_app_state", return_value={"success": True, "nodes": []}
    ):
        result = await agent.registered["computer_snapshot"](None, "Safari", 25, False)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_batch_stops_on_failure(tmp_path):
    agent = FakeAgent()
    tools.register_batch(agent)
    state = make_state(tmp_path)
    with (
        patch.object(tools.backend, "click", return_value={"success": True}),
        patch.object(
            tools.backend,
            "set_value",
            side_effect=tools.ComputerUseError("stale element"),
        ),
    ):
        result = await agent.registered["computer_use_batch"](
            None,
            state.revision,
            [
                {"action": "click", "element_id": 1},
                {"action": "set_value", "element_id": 2, "value": "hello"},
                {"action": "scroll", "amount": -3},
            ],
        )
    assert result["success"] is False
    assert len(result["completed_steps"]) == 2
    assert "stale element" in result["completed_steps"][1]["result"]["error"]


@pytest.mark.asyncio
async def test_successful_batch_attaches_inline_screenshot(tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    agent = FakeAgent()
    tools.register_batch(agent)
    state = make_state(tmp_path)
    updated = {
        "success": True,
        "state_revision": "updated",
        "screenshot_path": str(image),
        "nodes": [],
    }
    with (
        patch.object(tools.backend, "click", return_value={"success": True}),
        patch.object(tools.backend, "get_app_state", return_value=updated),
        patch.object(tools, "emit_inline_image", return_value=True),
        patch.object(
            tools,
            "wait_for_ui_settle",
            return_value={"settled": True, "observations": 3},
        ),
    ):
        result = await agent.registered["computer_use_batch"](
            None, state.revision, [{"action": "click", "element_id": 1}]
        )
    assert isinstance(result, ToolReturn)
    assert result.metadata["displayed_inline"] is True
    assert result.metadata["screenshot_path"] == str(image)
    assert result.return_value["state_revision"] == "updated"


@pytest.mark.asyncio
async def test_batch_rejects_unknown_and_oversized_actions(tmp_path):
    agent = FakeAgent()
    tools.register_batch(agent)
    invoke = agent.registered["computer_use_batch"]
    oversized = await invoke(None, "unused", [{"action": "wait"}] * 21)
    assert oversized["success"] is False
    state = make_state(tmp_path)
    unknown = await invoke(None, state.revision, [{"action": "launch_missiles"}])
    assert unknown["success"] is False


@pytest.mark.asyncio
async def test_batch_activation_bridge_error_is_returned_not_raised(tmp_path):
    agent = FakeAgent()
    tools.register_batch(agent)
    state = make_state(tmp_path)
    with patch.object(
        tools.backend,
        "require_state",
        side_effect=AttributeError("unexpected PyObjC selector"),
    ):
        result = await agent.registered["computer_use_batch"](
            None,
            state.revision,
            [{"action": "click", "element_id": 1}],
        )
    assert result["success"] is False
    assert "unexpected PyObjC selector" in result["error"]
