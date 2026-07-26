"""Behavior and integration tests for the Pi-style ``/tree`` plugin."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.plugins.tree.tree_menu import TreeMenu
from code_puppy.plugins.tree.tree_model import ConversationTree, describe_message


def user(text: str, *, system: bool = False) -> ModelRequest:
    parts = [UserPromptPart(content=text)]
    if system:
        parts.insert(0, SystemPromptPart(content="be a puppy"))
    return ModelRequest(parts=parts)


def assistant(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def tool_call() -> ModelResponse:
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="read",
                args={"path": "README.md"},
                tool_call_id="call-1",
            )
        ]
    )


def tool_result(text: str = "ok") -> ModelRequest:
    return ModelRequest(
        parts=[ToolReturnPart(tool_name="read", content=text, tool_call_id="call-1")]
    )


def test_describe_real_pydantic_messages() -> None:
    assert describe_message(user("hello", system=True)) == ("user", "hello")
    assert describe_message(assistant("world")) == ("assistant", "world")
    assert describe_message(tool_result())[0] == "tool"


def test_selecting_user_rewinds_before_prompt_and_restores_text() -> None:
    tree = ConversationTree()
    history = [
        user("first", system=True),
        assistant("one"),
        user("second"),
        assistant("two"),
    ]
    tree.sync(history)

    selected = tree.active_path[-2]
    navigation = tree.navigate(selected)

    assert navigation.changed is True
    assert navigation.editor_text == "second"
    assert navigation.history == history[:2]
    assert tree.leaf_id == tree.active_path[-1]


def test_selecting_root_user_rewinds_to_empty_history() -> None:
    tree = ConversationTree()
    tree.sync([user("first", system=True), assistant("one")])

    navigation = tree.navigate(tree.active_path[0])

    assert navigation.history == []
    assert navigation.editor_text == "first"
    assert navigation.leaf_id is None


def test_selecting_non_user_keeps_selected_message() -> None:
    tree = ConversationTree()
    history = [user("first"), assistant("one"), user("second"), assistant("two")]
    tree.sync(history)

    navigation = tree.navigate(tree.active_path[1])

    assert navigation.history == history[:2]
    assert navigation.editor_text is None


def test_resubmitting_after_rewind_preserves_both_branches() -> None:
    tree = ConversationTree()
    original = [user("first"), assistant("one"), user("old"), assistant("old answer")]
    tree.sync(original)
    original_leaf = tree.leaf_id
    old_prompt_id = tree.active_path[2]
    parent_id = tree.nodes[old_prompt_id].parent_id

    navigation = tree.navigate(old_prompt_id)
    replacement = navigation.history + [user("new"), assistant("new answer")]
    tree.sync(replacement)

    assert original_leaf in tree.nodes
    assert len(tree.nodes[parent_id].children) == 2
    assert {tree.nodes[item].text for item in tree.nodes[parent_id].children} == {
        "old",
        "new",
    }
    assert tree.nodes[tree.leaf_id].text == "new answer"


def test_same_leaf_is_noop() -> None:
    tree = ConversationTree()
    tree.sync([user("first"), assistant("one")])
    assert tree.navigate(tree.leaf_id).changed is False


def test_compacted_prefix_retains_inactive_branches() -> None:
    tree = ConversationTree()
    tree.sync([user("first"), assistant("one"), user("old"), assistant("old answer")])
    old_nodes = set(tree.nodes)
    tree.navigate(tree.active_path[2])
    tree.sync(tree.current_history() + [user("new"), assistant("new answer")])

    tree.sync([user("compacted summary"), assistant("continued")])

    assert old_nodes <= set(tree.nodes)
    assert {node.text for node in tree.nodes.values()} >= {
        "old",
        "new",
        "compacted summary",
    }


def test_empty_history_rewind_does_not_erase_branches() -> None:
    tree = ConversationTree()
    tree.sync([user("first"), assistant("one")])
    existing = set(tree.nodes)
    tree.navigate(tree.active_path[0])

    tree.sync([])

    assert set(tree.nodes) == existing
    assert tree.active_path == []


def test_filters_search_and_active_branch_ordering() -> None:
    tree = ConversationTree()
    tree.sync([user("first"), assistant("one"), tool_result(), user("old")])
    tree.navigate(tree.active_path[-1])
    tree.sync(tree.current_history() + [user("replacement")])

    assert all(tree.nodes[item].role == "user" for item in tree.visible_nodes("user"))
    assert all(
        tree.nodes[item].role != "tool" for item in tree.visible_nodes("no-tools")
    )
    matches = tree.visible_nodes(query="REPLACE")
    assert len(matches) == 1
    assert tree.nodes[matches[0]].text == "replacement"


def test_tool_only_assistant_is_hidden_by_default_and_no_tools() -> None:
    tree = ConversationTree()
    tree.sync([user("read it"), tool_call(), tool_result(), assistant("done")])
    tool_call_id = tree.active_path[1]

    assert tree.nodes[tool_call_id].role == "tool-call"
    assert tool_call_id not in tree.visible_nodes("default")
    assert tool_call_id not in tree.visible_nodes("no-tools")
    assert "README.md" in tree.nodes[tool_call_id].text
    assert "ok" in tree.nodes[tree.active_path[2]].text


def test_menu_search_escape_and_nearest_visible_ancestor() -> None:
    tree = ConversationTree()
    tree.sync([user("first"), assistant("one"), user("second")])
    menu = TreeMenu(tree)
    selected = tree.leaf_id
    menu.query = "does-not-exist"
    menu.refresh()
    assert menu.rows == []

    menu.query = ""
    menu.refresh()
    assert menu.current_id == selected

    menu.filter_mode = "user"
    menu._preferred_id = tree.active_path[1]
    menu.cursor = 0
    menu.refresh()
    assert menu.current_id in tree.active_path


def test_custom_command_end_to_end_switches_history_and_prefills_editor() -> None:
    from code_puppy.plugins.tree import register_callbacks as plugin

    history = [
        user("first", system=True),
        assistant("one"),
        user("edit me"),
        assistant("old answer"),
    ]
    agent = MagicMock()
    agent.get_message_history.return_value = history
    tree = ConversationTree()
    tree.sync(history)
    plugin._TREES.clear()
    plugin._TREES[plugin._tree_key(agent)] = tree
    selected = tree.active_path[-2]

    menu = MagicMock()
    menu.run.return_value = selected
    editor = SimpleNamespace(buffer="", replace_buffer_text=MagicMock())

    with (
        patch("code_puppy.agents.agent_manager.get_current_agent", return_value=agent),
        patch("code_puppy.plugins.tree.tree_menu.TreeMenu", return_value=menu),
        patch("code_puppy.messaging.run_ui.get_run_editor", return_value=editor),
        patch("code_puppy.messaging.run_ui.is_run_active", return_value=False),
        patch.object(plugin, "_emit"),
    ):
        assert plugin._handle_custom_command("/tree", "tree") is True

    agent.set_message_history.assert_called_once_with(history[:2])
    editor.replace_buffer_text.assert_called_once_with("edit me")


def test_tree_sidecar_round_trip_preserves_inactive_branch(tmp_path) -> None:
    from code_puppy.plugins.tree import tree_storage

    tree = ConversationTree()
    tree.sync([user("first"), assistant("one"), user("old"), assistant("old answer")])
    tree.navigate(tree.active_path[2])
    tree.sync(tree.current_history() + [user("new"), assistant("new answer")])
    sidecar = tmp_path / "session.pkl"

    with patch.object(tree_storage, "storage_path", return_value=sidecar):
        tree_storage.save_tree("session", "code-puppy", tree)
        restored = tree_storage.load_tree("session", "code-puppy")

    assert restored is not None
    assert len(restored.nodes) == len(tree.nodes)
    assert {node.text for node in restored.nodes.values()} >= {"old", "new"}
    assert restored.active_path == tree.active_path


@pytest.mark.skipif(os.name == "nt", reason="PTY smoke test is POSIX-only")
def test_tree_selector_pty_end_to_end() -> None:
    """Drive the real selector and plugin boundary through a pseudo-terminal."""
    import pexpect

    script = r"""
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from code_puppy.agents import agent_manager
from code_puppy.plugins.tree import register_callbacks as plugin

class Agent:
    name = "code-puppy"
    def __init__(self):
        self.history = [
            ModelRequest(parts=[UserPromptPart(content="first")]),
            ModelResponse(parts=[TextPart(content="one")]),
            ModelRequest(parts=[UserPromptPart(content="edit me")]),
            ModelResponse(parts=[TextPart(content="old answer")]),
        ]
    def get_message_history(self):
        return self.history
    def set_message_history(self, history):
        self.history = history

agent = Agent()
agent_manager.get_current_agent = lambda: agent
plugin._TREES.clear()
plugin._handle_custom_command("/tree", "tree")
assert len(agent.history) == 2, len(agent.history)
print("TREE_E2E_OK", flush=True)
"""
    child = pexpect.spawn(
        sys.executable,
        ["-c", script],
        cwd=os.getcwd(),
        encoding="utf-8",
        timeout=15,
        dimensions=(40, 120),
    )
    child.expect("Session Tree")
    child.send("\u001b[A")
    child.send("\r")
    child.expect("TREE_E2E_OK")
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_tree_does_not_claim_fork_or_arguments() -> None:
    from code_puppy.plugins.tree import register_callbacks as plugin

    assert plugin._handle_custom_command("/fork do work", "fork") is None
    with patch.object(plugin, "_emit") as emit:
        assert plugin._handle_custom_command("/tree nope", "tree") is True
    emit.assert_called_once()
