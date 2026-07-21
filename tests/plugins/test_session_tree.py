"""Tests for persistent /tree, /fork, and /clone navigation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from code_puppy.plugins.session_tree.tree_model import (
    FilterMode,
    build_nodes,
    resolve_node,
    selectable_nodes,
    visible_nodes,
)
from code_puppy.plugins.session_tree.tree_store import SessionTree, TreeStore


class Message(SimpleNamespace):
    pass


def _plugin_module():
    sys.modules.setdefault("dbos", MagicMock())
    return importlib.import_module("code_puppy.plugins.session_tree.register_callbacks")


def _history() -> list[Message]:
    return [
        Message(role="system", content="system prompt"),
        Message(role="user", content="first task"),
        Message(role="assistant", content="first answer"),
        Message(role="toolResult", content="tool output"),
        Message(role="user", content="second task"),
        Message(role="assistant", content="second answer"),
    ]


def _tree(history=None) -> SessionTree:
    tree = SessionTree()
    tree.sync_history(history or _history())
    return tree


def _command_context(tmp_path: Path, history: list[Message]):
    agent = MagicMock()
    agent.get_message_history.return_value = history
    manager = SimpleNamespace(get_current_agent=lambda: agent)
    config = SimpleNamespace(
        AUTOSAVE_DIR=str(tmp_path), get_current_autosave_id=lambda: "current"
    )
    return agent, patch.dict(
        sys.modules,
        {
            "code_puppy.agents.agent_manager": manager,
            "code_puppy.config": config,
        },
    )


def test_sync_history_is_stable_and_builds_real_branches():
    history = _history()
    tree = _tree(history)
    original_ids = tree.path_ids(tree.active_leaf_id)

    tree.sync_history(history)
    assert tree.path_ids(tree.active_leaf_id) == original_ids

    tree.sync_history([*history[:4], Message(role="user", content="alternate")])
    branch_parent = original_ids[3]
    assert len(tree.children(branch_parent)) == 2
    assert len(tree.nodes) == len(history) + 1


def test_duplicate_messages_on_one_path_remain_distinct():
    repeated = Message(role="user", content="same")
    tree = _tree([repeated, repeated])
    path = tree.path_ids(tree.active_leaf_id)

    assert len(path) == 2
    assert path[0] != path[1]


def test_store_persists_branches_labels_and_active_leaf(tmp_path):
    store = TreeStore(tmp_path / "tree.pkl")
    tree = _tree()
    selected = selectable_nodes(tree)[0]
    tree.set_label(selected.node_id, "keeper")
    store.save(tree)

    restored = store.load()
    assert restored.nodes[selected.node_id].label == "keeper"
    assert restored.active_leaf_id == tree.active_leaf_id


def test_model_marks_active_path_and_renders_branch_depth():
    history = _history()
    tree = _tree(history)
    first_path = tree.path_ids(tree.active_leaf_id)
    tree.sync_history([*history[:3], Message(role="user", content="alternate")])
    nodes = build_nodes(tree)

    assert sum(node.is_active for node in nodes) == 1
    assert all(
        node.is_on_active_path
        for node in nodes
        if node.node_id in tree.path_ids(tree.active_leaf_id)
    )
    assert any(node.depth > 0 and not node.is_on_active_path for node in nodes)
    assert first_path[-1] in tree.nodes


def test_filters_search_and_unique_resolution():
    tree = _tree()
    nodes = build_nodes(tree)
    assistant = next(node for node in nodes if node.role == "assistant")
    tree.set_label(assistant.node_id, "keeper")
    nodes = build_nodes(tree)

    assert {node.role for node in visible_nodes(nodes, FilterMode.USER_ONLY)} == {
        "user"
    }
    assert all(
        not node.is_toolish for node in visible_nodes(nodes, FilterMode.NO_TOOLS)
    )
    assert [node.node_id for node in visible_nodes(nodes, FilterMode.LABELED_ONLY)] == [
        assistant.node_id
    ]
    assert (
        visible_nodes(nodes, FilterMode.ALL, "first answer")[0].node_id
        == assistant.node_id
    )
    selectable = selectable_nodes(tree)
    assert resolve_node("1", selectable) == selectable[0]
    assert resolve_node(assistant.node_id[:6], selectable).node_id == assistant.node_id


def test_abandoned_history_starts_after_common_ancestor():
    history = _history()
    tree = _tree(history)
    old_leaf = tree.active_leaf_id
    target = tree.path_ids(old_leaf)[2]

    abandoned = tree.abandoned_history(target)
    assert abandoned == history[3:]


def test_tree_user_selection_restores_parent_and_preserves_old_branch(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)
    with context, patch.object(plugin, "_emit"):
        result = plugin._handle_custom_command("/tree 4", "tree")

    assert str(result) == "second task"
    agent.set_message_history.assert_called_once_with(history[:4])
    stored = TreeStore(tmp_path / "session_trees/current.pkl").load()
    assert len(stored.nodes) == len(history)
    assert stored.history_through(stored.active_leaf_id) == history[:4]


def test_new_turn_after_navigation_creates_sibling_branch(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)
    with context, patch.object(plugin, "_emit"):
        plugin._handle_custom_command("/tree 4", "tree")

    alternate = [*history[:4], Message(role="user", content="replacement")]
    agent, context = _command_context(tmp_path, alternate)
    with context, patch.object(plugin, "_emit"):
        plugin._handle_custom_command("/tree nope", "tree")

    stored = TreeStore(tmp_path / "session_trees/current.pkl").load()
    parent = stored.path_ids(stored.active_leaf_id)[3]
    assert len(stored.children(parent)) == 2


def test_tree_non_user_selection_restores_through_selected_node(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)
    with context, patch.object(plugin, "_emit"):
        result = plugin._handle_custom_command("/tree 2", "tree")

    assert result is True
    agent.set_message_history.assert_called_once_with(history[:3])


def test_summary_receives_only_abandoned_tail_and_attaches_at_target(tmp_path):
    plugin = _plugin_module()
    history = _history()
    summary = Message(role="user", content="branch summary")
    agent, context = _command_context(tmp_path, history)
    with (
        context,
        patch.object(plugin, "_emit"),
        patch.object(plugin, "_summary_messages", return_value=[summary]) as summarize,
    ):
        plugin._handle_custom_command("/tree summary 2", "tree")

    assert summarize.call_args.args[1] == history[3:]
    agent.set_message_history.assert_called_once_with([*history[:3], summary])


def test_summary_failure_does_not_mutate_history(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)
    with (
        context,
        patch.object(plugin, "_emit"),
        patch.object(
            plugin, "_summary_messages", side_effect=RuntimeError("no biscuits")
        ),
    ):
        result = plugin._handle_custom_command("/tree summary 2", "tree")

    assert result is True
    agent.set_message_history.assert_not_called()


def test_fork_without_argument_uses_tree_selector(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)

    def select_last_user(tree, **_kwargs):
        selected = [node for node in selectable_nodes(tree) if node.is_userish][-1]
        return SimpleNamespace(node=selected, cancelled=False)

    with (
        context,
        patch.object(plugin, "_emit"),
        patch.object(plugin, "_run_tree_menu", side_effect=select_last_user),
    ):
        result = plugin._handle_custom_command("/fork", "fork")

    assert str(result) == "second task"
    agent.set_message_history.assert_called_once_with(history[:4])


def test_clone_does_not_rotate_current_session_id(tmp_path):
    plugin = _plugin_module()
    history = _history()
    agent, context = _command_context(tmp_path, history)
    agent.estimate_tokens_for_message.return_value = 1
    with context, patch.object(plugin, "_emit"):
        assert plugin._handle_custom_command("/clone", "clone") is True

    assert len(list(tmp_path.glob("auto_session_*.pkl"))) == 1


def test_unknown_command_is_ignored():
    assert _plugin_module()._handle_custom_command("/nope", "nope") is None
