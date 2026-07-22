"""Register Pi-style ``/tree`` navigation without colliding with ``/fork``."""

from __future__ import annotations

from typing import Any, Optional

from code_puppy.callbacks import register_callback
from code_puppy.i18n import t
from code_puppy.plugins.tree.tree_model import ConversationTree

_TREES: dict[tuple[str, str], ConversationTree] = {}


def _tree_key(agent: Any) -> tuple[str, str]:
    from code_puppy.config import get_current_session_name

    return get_current_session_name(), str(getattr(agent, "name", "agent"))


def _tree_for(agent: Any) -> ConversationTree:
    from code_puppy.plugins.tree.tree_storage import load_tree

    key = _tree_key(agent)
    tree = _TREES.get(key)
    if tree is None:
        tree = load_tree(*key) or ConversationTree()
        _TREES[key] = tree
    return tree


def _save_agent_tree(agent: Any, tree: ConversationTree) -> bool:
    from code_puppy.plugins.tree.tree_storage import save_tree

    session_name, agent_name = _tree_key(agent)
    return save_tree(session_name, agent_name, tree)


def _emit(kind: str, message: Any) -> None:
    from code_puppy import messaging

    getattr(messaging, f"emit_{kind}")(message)


def _on_interactive_turn_end(
    agent: Any,
    prompt: str,
    result: Any = None,
    *,
    success: bool = True,
    error: Optional[BaseException] = None,
) -> None:
    """Capture the completed path after the CLI commits result history."""
    del prompt, result, error
    if not success:
        return
    try:
        tree = _tree_for(agent)
        tree.sync(list(agent.get_message_history()))
        if not _save_agent_tree(agent, tree):
            _emit("warning", t("tree.persistence_failed"))
    except Exception:
        # Navigation is an optional UI feature; a custom provider message must
        # never poison the normal agent run.
        return


def _restore_editor_text(text: str) -> bool:
    """Restore a selected user prompt when the persistent editor is idle."""
    try:
        from code_puppy.messaging.run_ui import get_run_editor, is_run_active

        editor = get_run_editor()
        if editor is None or is_run_active() or editor.buffer.strip():
            return False
        editor.replace_buffer_text(text)
        return True
    except Exception:
        return False


def _launch_tree() -> None:
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.plugins.tree.tree_menu import TreeMenu

    try:
        agent = get_current_agent()
        tree = _tree_for(agent)
        tree.sync(list(agent.get_message_history()))
    except Exception as exc:
        _emit("error", t("tree.inspect_failed", error=exc))
        return

    if not tree.nodes:
        _emit("info", t("tree.empty"))
        return

    try:
        selected_id = TreeMenu(tree, initial_id=tree.leaf_id).run()
    except Exception as exc:
        _emit("error", t("tree.selector_failed", error=exc))
        return

    if selected_id is None:
        return

    try:
        navigation = tree.navigate(selected_id)
    except (KeyError, ValueError) as exc:
        _emit("warning", t("tree.selection_missing", error=exc))
        return

    if not navigation.changed:
        _emit("info", t("tree.already_here"))
        return

    agent.set_message_history(navigation.history)
    if navigation.editor_text:
        if not _restore_editor_text(navigation.editor_text):
            _emit(
                "info",
                t("tree.prompt_restored_fallback", prompt=navigation.editor_text),
            )
    _emit("success", t("tree.switched"))


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "tree":
        return None
    if command.strip() != "/tree":
        _emit("warning", t("tree.usage"))
        return True
    _launch_tree()
    return True


def _custom_help() -> list[tuple[str, str]]:
    return [("tree", t("tree.help"))]


register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)
register_callback("interactive_turn_end", _on_interactive_turn_end)


__all__ = [
    "_TREES",
    "_custom_help",
    "_handle_custom_command",
    "_launch_tree",
    "_on_interactive_turn_end",
    "_restore_editor_text",
    "_tree_for",
    "_tree_key",
]
