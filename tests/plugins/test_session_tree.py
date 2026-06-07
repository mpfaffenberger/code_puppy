"""Tests for the /tree, /fork, and /clone session navigation plugin."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class Message(SimpleNamespace):
    pass


def _plugin_module():
    sys.modules.setdefault("dbos", MagicMock())
    return importlib.import_module("code_puppy.plugins.session_tree.register_callbacks")


def _tree_model():
    return importlib.import_module("code_puppy.plugins.session_tree.tree_model")


def _agent_manager_module(agent: MagicMock) -> SimpleNamespace:
    return SimpleNamespace(get_current_agent=lambda: agent)


def _history() -> list[Message]:
    return [
        Message(role="system", content="system prompt"),
        Message(role="user", content="first task"),
        Message(role="assistant", content="first answer"),
        Message(role="toolResult", content="tool output"),
        Message(role="user", content="second task"),
        Message(role="assistant", content="second answer"),
    ]


def test_build_nodes_creates_stable_tree_entries():
    nodes = _tree_model().build_nodes(_history())

    assert len(nodes) == 6
    assert nodes[0].is_system is True
    assert nodes[1].role == "user"
    assert nodes[1].preview == "first task"
    assert len(nodes[1].node_id) == 8


def test_visible_nodes_supports_filter_modes_and_labels():
    model = _tree_model()
    history = _history()
    base_nodes = model.build_nodes(history)
    labels = {base_nodes[2].node_id: "keeper"}
    nodes = model.build_nodes(history, labels)

    assert all(
        not node.is_toolish
        for node in model.visible_nodes(nodes, model.FilterMode.NO_TOOLS)
    )
    assert {
        node.role for node in model.visible_nodes(nodes, model.FilterMode.USER_ONLY)
    } == {"user"}
    assert model.visible_nodes(nodes, model.FilterMode.LABELED_ONLY) == [nodes[2]]
    assert len(model.visible_nodes(nodes, model.FilterMode.ALL)) == len(nodes)


def test_resolve_node_accepts_ordinal_index_and_id_prefix():
    model = _tree_model()
    nodes = model.selectable_nodes(_history())

    assert model.resolve_node("1", nodes).preview == "first task"
    assert model.resolve_node("4", nodes).preview == "second task"
    assert model.resolve_node(nodes[1].node_id[:4], nodes) == nodes[1]
    assert model.resolve_node("nope", nodes) is None


def test_history_helpers_preserve_system_prompt_for_forks():
    model = _tree_model()
    history = _history()

    assert model.history_through(history, 2) == history[:3]
    assert model.history_before(history, 1) == history[:1]


def test_help_entries_include_tree_fork_clone_and_summary_language():
    entries = dict(_plugin_module()._help_entries())

    assert "summarize" in entries["tree"]
    assert entries["fork"]
    assert entries["clone"]


def test_handle_custom_command_ignores_unknown_command():
    assert _plugin_module()._handle_custom_command("/nope", "nope") is None


def test_tree_restores_non_user_history_point_from_argument():
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = _plugin_module()._handle_custom_command("/tree 2", "tree")

    assert result is True
    agent.set_message_history.assert_called_once_with(history[:3])


def test_tree_summary_selection_replaces_history_with_summarized_conversation():
    history = _history()
    summarized = [history[0], Message(role="user", content="Summary: compacted")]
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._summarize_through",
            return_value=summarized,
        ) as summarize,
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = _plugin_module()._handle_custom_command("/tree summary 2", "tree")

    assert result is True
    summarize.assert_called_once()
    agent.set_message_history.assert_called_once_with(summarized)


def test_tree_summary_from_tui_result_replaces_history():
    plugin = _plugin_module()
    history = _history()
    summarized = [history[0], Message(role="user", content="Summary: compacted")]
    agent = MagicMock()
    agent.get_message_history.return_value = history
    node = _tree_model().selectable_nodes(history)[1]
    result_obj = SimpleNamespace(node=node, cancelled=False, summarize=True)

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._run_tree_menu",
            return_value=result_obj,
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._summarize_through",
            return_value=summarized,
        ),
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = plugin._handle_custom_command("/tree", "tree")

    assert result is True
    agent.set_message_history.assert_called_once_with(summarized)


def test_tree_summary_failure_does_not_mutate_history():
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._summarize_through",
            side_effect=RuntimeError("no biscuits"),
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._emit_error"
        ) as error,
    ):
        result = _plugin_module()._handle_custom_command("/tree summarize 2", "tree")

    assert result is True
    agent.set_message_history.assert_not_called()
    assert "failed to summarize" in str(error.call_args)


def test_tree_user_selection_returns_prompt_and_restores_parent():
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = _plugin_module()._handle_custom_command("/tree 4", "tree")

    assert str(result) == "second task"
    agent.set_message_history.assert_called_once_with(history[:4])


def test_tree_warns_for_empty_or_system_only_history():
    agent = MagicMock()
    agent.get_message_history.return_value = [Message(role="system", content="system")]

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._emit_warning"
        ) as warning,
    ):
        result = _plugin_module()._handle_custom_command("/tree", "tree")

    assert result is True
    agent.set_message_history.assert_not_called()
    assert "nothing to restore" in str(warning.call_args)


def test_tree_warns_for_invalid_selection():
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._emit_warning"
        ) as warning,
    ):
        result = _plugin_module()._handle_custom_command("/tree nope", "tree")

    assert result is True
    agent.set_message_history.assert_not_called()
    assert "no history point matches" in str(warning.call_args)


def test_fork_returns_selected_prompt_and_trims_history_before_it():
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = _plugin_module()._handle_custom_command("/fork 2", "fork")

    assert str(result) == "second task"
    agent.set_message_history.assert_called_once_with(history[:4])


def test_fork_warns_when_no_user_messages_exist():
    agent = MagicMock()
    agent.get_message_history.return_value = [
        Message(role="system", content="system"),
        Message(role="assistant", content="hello"),
    ]

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.session_tree.register_callbacks._emit_warning"
        ) as warning,
    ):
        result = _plugin_module()._handle_custom_command("/fork", "fork")

    assert result is True
    agent.set_message_history.assert_not_called()
    assert "no previous user messages" in str(warning.call_args)


def test_clone_saves_active_branch_to_new_autosave_session(tmp_path):
    history = _history()
    agent = MagicMock()
    agent.get_message_history.return_value = history
    agent.estimate_tokens_for_message.return_value = 1

    config = SimpleNamespace(
        AUTOSAVE_DIR=str(tmp_path), rotate_autosave_id=lambda: "abc123"
    )
    with (
        patch.dict(
            sys.modules,
            {
                "code_puppy.agents.agent_manager": _agent_manager_module(agent),
                "code_puppy.config": config,
            },
        ),
        patch("code_puppy.plugins.session_tree.register_callbacks._emit_success"),
    ):
        result = _plugin_module()._handle_custom_command("/clone", "clone")

    assert result is True
    assert (tmp_path / "autosave_abc123.pkl").exists()
    assert (tmp_path / "autosave_abc123_meta.json").exists()
