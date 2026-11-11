"""Prompt helpers preserve rewrite composition and attachment routing."""

from unittest.mock import AsyncMock, call

import pytest
from PIL import Image
from pydantic_ai import BinaryContent

from code_puppy import agent_completion_inbox, callbacks
from code_puppy.agents import _runtime
from code_puppy.command_line.attachments import resolve_steer_content
from code_puppy.messaging import pause_controller
from tests.agents.test_agent_exception_recovery import (
    DummyAgent,
    DummyResult,
    ScriptedPydanticAgent,
    isolated_runtime_callbacks,  # noqa: F401
)


@pytest.mark.parametrize("with_attachments", [False, True])
async def test_queued_steer_routes_by_attachment_presence(
    monkeypatch, tmp_path, with_attachments
):
    raw = "queued text"
    if with_attachments:
        image = tmp_path / "steer.png"
        Image.new("RGB", (2, 2), "blue").save(image)
        raw = f"inspect {image}"
    resolved, _ = resolve_steer_content(raw)
    if with_attachments:
        assert isinstance(resolved, list)
        assert any(isinstance(part, BinaryContent) for part in resolved[1:])
    else:
        assert isinstance(resolved, str)

    controller = pause_controller.PauseController()
    controller.request_steer(raw, mode="queue", history_recorded=True)
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: controller)
    general = AsyncMock(wraps=_runtime.apply_user_prompt_submit)
    attachment_free = AsyncMock(wraps=_runtime.apply_attachment_free_user_prompt_submit)
    monkeypatch.setattr(_runtime, "apply_user_prompt_submit", general)
    monkeypatch.setattr(
        _runtime, "apply_attachment_free_user_prompt_submit", attachment_free
    )
    provider = ScriptedPydanticAgent(DummyResult("initial"), DummyResult("steered"))

    result = await _runtime.run_with_mcp(DummyAgent(provider), "initial")

    assert result.data == "steered"
    session_id = general.await_args_list[0].args[1]
    assert session_id
    text = resolved[0] if with_attachments else resolved
    assert general.await_args_list == [
        call("initial", session_id),
        call(text, session_id),
    ]
    if with_attachments:
        attachment_free.assert_not_awaited()
    else:
        attachment_free.assert_awaited_once_with(text, session_id)
    assert provider.calls[1]["prompt"] == resolved


@pytest.mark.parametrize(
    "helper_name",
    ["apply_user_prompt_submit", "apply_attachment_free_user_prompt_submit"],
)
@pytest.mark.parametrize(
    ("rewrites", "expected"),
    [
        (["", 17, "first", None, "last"], "last"),
        (["kept", "", 17, None, True], "kept"),
    ],
)
async def test_prompt_helpers_apply_last_nonempty_string_rewrite(
    monkeypatch, helper_name, rewrites, expected
):
    dispatch = AsyncMock(return_value=rewrites)
    monkeypatch.setattr(_runtime, "on_user_prompt_submit", dispatch)

    assert await getattr(_runtime, helper_name)("original", "session") == expected

    dispatch.assert_awaited_once_with("original", "session")


@pytest.mark.parametrize("with_attachments", [False, True])
async def test_between_turn_completion_bypasses_prompt_hooks(
    monkeypatch, tmp_path, with_attachments
):
    report = "  child report: literal @private /clear\x00  "
    steer = "queued user steer"
    if with_attachments:
        image = tmp_path / "queued.png"
        Image.new("RGB", (2, 2), "blue").save(image)
        steer = f"inspect {image}"
    resolved, _ = resolve_steer_content(steer)
    controller = pause_controller.PauseController()
    controller.request_steer(steer, mode="queue", history_recorded=True)
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: controller)
    seen = []

    def rewrite(prompt, session_id):
        seen.append(prompt)
        return "rewritten: " + prompt

    callbacks.register_callback("user_prompt_submit", rewrite)
    initial = DummyResult("initial")
    initial.all_messages = lambda: ["completed parent history"]
    provider = ScriptedPydanticAgent(
        initial, DummyResult("report"), DummyResult("steer")
    )
    agent = DummyAgent(provider)
    agent_completion_inbox.deliver_completion(agent, report)

    result = await _runtime.run_with_mcp(agent, "initial")

    assert result.data == "steer"
    text = resolved[0] if with_attachments else resolved
    assert seen == ["initial", text]
    assert provider.calls[1]["prompt"] == report
    assert provider.calls[1]["message_history"] == ["completed parent history"]
    expected = (
        ["rewritten: " + text, *resolved[1:]]
        if with_attachments
        else "rewritten: " + text
    )
    assert provider.calls[2]["prompt"] == expected
    assert agent_completion_inbox.pop_completion(agent) is None
