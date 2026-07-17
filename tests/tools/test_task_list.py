from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from code_puppy.tools import TOOL_REGISTRY
from code_puppy.tools.task_list import (
    TaskItem,
    _apply_update,
    get_task_list,
    register_update_task_list,
    render_task_list,
)


def test_tool_is_registered_in_registry():
    assert TOOL_REGISTRY.get("update_task_list") is register_update_task_list


def test_mist_agent_advertises_the_tool():
    from code_puppy.agents.agent_code_puppy import MistAgent

    assert "update_task_list" in MistAgent().get_available_tools()


def test_render_uses_status_glyphs():
    rendered = render_task_list(
        [
            {"content": "a", "status": "completed"},
            {"content": "b", "status": "in_progress"},
            {"content": "c", "status": "pending"},
        ]
    )
    assert rendered.splitlines() == ["[x] 1. a", "[→] 2. b", "[ ] 3. c"]


def test_render_empty_list():
    assert render_task_list([]) == "(task list cleared)"


def test_apply_update_stores_and_replaces():
    _apply_update([TaskItem(content="one", status="in_progress")])
    assert [t["content"] for t in get_task_list()] == ["one"]
    # Replace semantics: a second call overwrites, not appends.
    out = _apply_update(
        [
            TaskItem(content="x", status="completed"),
            TaskItem(content="y", status="pending"),
        ]
    )
    assert out.success is True
    assert [t["content"] for t in get_task_list()] == ["x", "y"]


def test_tool_registers_and_runs_on_real_agent():
    agent = Agent(TestModel())
    register_update_task_list(agent)
    # TestModel auto-invokes the tool with generated args; must not raise.
    agent.run_sync("plan the work")
