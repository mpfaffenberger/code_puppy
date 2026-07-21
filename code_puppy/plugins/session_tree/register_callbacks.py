"""Session navigation commands for Code Puppy."""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Any

from code_puppy.callbacks import register_callback

from .tree_menu import TreeSelectionMenu
from .tree_model import (
    FilterMode,
    HistoryNode,
    message_text,
    resolve_node,
    selectable_nodes,
    user_nodes,
)
from .tree_store import SessionTree, TreeStore


def _emit(kind: str, message: str) -> None:
    from code_puppy import messaging

    getattr(messaging, f"emit_{kind}")(message)


def _current_history() -> tuple[Any, list[Any]]:
    from code_puppy.agents.agent_manager import get_current_agent

    agent = get_current_agent()
    return agent, list(agent.get_message_history())


def _tree_store() -> TreeStore:
    from code_puppy.config import AUTOSAVE_DIR, get_current_autosave_id

    path = Path(AUTOSAVE_DIR) / "session_trees" / f"{get_current_autosave_id()}.pkl"
    return TreeStore(path)


def _load_tree(history: list[Any]) -> tuple[TreeStore, SessionTree]:
    store = _tree_store()
    tree = store.load()
    tree.sync_history(history)
    store.save(tree)
    return store, tree


def _help_entries() -> list[tuple[str, str]]:
    return [
        ("tree", "Navigate the persistent conversation tree and switch branches"),
        ("fork", "Re-edit a previous user message to create a branch"),
        ("clone", "Duplicate the active branch into a new autosave session"),
    ]


def _tree_args(command: str) -> tuple[bool, str]:
    parts = command.split(maxsplit=2)
    if len(parts) >= 2 and parts[1].lower() in {"summary", "summarize"}:
        return True, parts[2].strip() if len(parts) == 3 else ""
    return False, parts[1].strip() if len(parts) >= 2 else ""


def _markdown_result(prompt: str) -> Any:
    from code_puppy.plugins.customizable_commands.register_callbacks import (
        MarkdownCommandResult,
    )

    return MarkdownCommandResult(prompt)


def _run_tree_menu(tree: SessionTree, *, user_only: bool = False) -> Any:
    mode = FilterMode.USER_ONLY if user_only else FilterMode.DEFAULT
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(
            lambda: asyncio.run(TreeSelectionMenu(tree=tree, mode=mode).run_async())
        )
        return future.result(timeout=300)


def _resolve_or_menu(
    command: str, tree: SessionTree, nodes: list[HistoryNode]
) -> tuple[HistoryNode | None, bool]:
    summarize, selection = _tree_args(command)
    if selection:
        node = resolve_node(selection, nodes)
        if node is None:
            _emit("warning", f"/tree: no unique history point matches '{selection}'")
        return node, summarize
    result = _run_tree_menu(tree)
    if result.cancelled:
        return None, False
    return result.node, result.summarize


def _summary_messages(history: list[Any], abandoned: list[Any]) -> list[Any]:
    """Summarize only the abandoned tail and return generated context messages."""
    from code_puppy.agents._compaction import _run_summarization_core

    if not abandoned:
        return []
    system = history[:1]
    compacted, _ = _run_summarization_core(
        [*system, *abandoned],
        protected_tokens=0,
        with_protection=False,
        model_name=None,
    )
    return list(compacted[len(system) :])


def _navigate(
    agent: Any,
    store: TreeStore,
    tree: SessionTree,
    node: HistoryNode,
    *,
    summarize: bool,
) -> bool | Any:
    old_leaf_id = tree.active_leaf_id
    target_id = node.parent_id if node.is_userish else node.node_id
    prompt = (
        message_text(tree.nodes[node.node_id].message).strip()
        if node.is_userish
        else ""
    )
    target_history = tree.history_through(target_id)

    if summarize:
        try:
            target_history.extend(
                _summary_messages(
                    tree.history_through(old_leaf_id),
                    tree.abandoned_history(node.node_id),
                )
            )
        except Exception as exc:  # noqa: BLE001 - command boundary must fail soft
            _emit("error", f"/tree: failed to summarize abandoned branch - {exc}")
            return True

    try:
        agent.set_message_history(target_history)
        tree.sync_history(target_history)
        store.save(tree)
    except Exception as exc:  # noqa: BLE001
        _emit("error", f"/tree: failed to navigate - {exc}")
        return True

    if node.is_userish:
        _emit(
            "success", "Moved before selected user message; edit it to create a branch."
        )
        return _markdown_result(prompt) if prompt else True
    _emit("success", f"Navigated to {node.role} message [{node.node_id}]")
    return True


def _handle_tree(command: str) -> bool | Any:
    try:
        agent, history = _current_history()
        store, tree = _load_tree(history)
    except Exception as exc:  # noqa: BLE001
        _emit("error", f"/tree: could not read session tree - {exc}")
        return True

    nodes = selectable_nodes(tree)
    if not nodes:
        _emit("warning", "/tree: conversation history is empty")
        return True
    try:
        node, summarize = _resolve_or_menu(command, tree, nodes)
        # Label changes made in the selector survive selection and cancellation.
        store.save(tree)
    except Exception as exc:  # noqa: BLE001
        _emit("error", f"/tree: selector failed - {exc}")
        return True
    return (
        True
        if node is None
        else _navigate(agent, store, tree, node, summarize=summarize)
    )


def _handle_fork(command: str) -> bool | Any:
    try:
        agent, history = _current_history()
        store, tree = _load_tree(history)
    except Exception as exc:  # noqa: BLE001
        _emit("error", f"/fork: could not read session tree - {exc}")
        return True
    nodes = user_nodes(tree)
    if not nodes:
        _emit("warning", "/fork: no previous user messages are available")
        return True
    selection = command.split(maxsplit=1)[1].strip() if " " in command else ""
    if selection:
        node = resolve_node(selection, nodes)
    else:
        try:
            result = _run_tree_menu(tree, user_only=True)
            node = result.node if not result.cancelled else None
        except Exception as exc:  # noqa: BLE001
            _emit("error", f"/fork: selector failed - {exc}")
            return True
    if node is None or not node.is_userish:
        if selection:
            _emit("warning", f"/fork: no unique user message matches '{selection}'")
        return True
    return _navigate(agent, store, tree, node, summarize=False)


def _handle_clone() -> bool:
    try:
        agent, history = _current_history()
        if not history:
            _emit("warning", "/clone: no active branch to clone")
            return True
        from code_puppy.config import AUTOSAVE_DIR
        from code_puppy.session_storage import save_session

        # A clone is a new saved artifact, not a mutation of the current session identity.
        clone_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        metadata = save_session(
            history=history,
            session_name=f"auto_session_{clone_id}",
            base_dir=Path(AUTOSAVE_DIR),
            timestamp=datetime.now().isoformat(),
            token_estimator=agent.estimate_tokens_for_message,
            auto_saved=True,
        )
        _emit("success", f"Cloned active branch to {metadata.session_name}.")
    except Exception as exc:  # noqa: BLE001
        _emit("error", f"/clone: failed to clone active branch - {exc}")
    return True


def _handle_custom_command(command: str, name: str) -> bool | str | None:
    if name == "tree":
        return _handle_tree(command)
    if name == "fork":
        return _handle_fork(command)
    if name == "clone":
        return _handle_clone()
    return None


register_callback("custom_command_help", _help_entries)
register_callback("custom_command", _handle_custom_command)

__all__ = ["_handle_custom_command", "_handle_fork", "_handle_tree", "_help_entries"]
