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
    HistoryNode,
    build_nodes,
    history_before,
    history_through,
    message_text,
    resolve_node,
    selectable_nodes,
    user_nodes,
)

_LABELS: dict[str, str] = {}


def _emit_error(message: Any) -> None:
    from code_puppy.messaging import emit_error

    emit_error(message)


def _emit_info(message: Any) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_success(message: Any) -> None:
    from code_puppy.messaging import emit_success

    emit_success(message)


def _emit_warning(message: Any) -> None:
    from code_puppy.messaging import emit_warning

    emit_warning(message)


def _current_history() -> tuple[Any, list[Any]]:
    from code_puppy.agents.agent_manager import get_current_agent

    agent = get_current_agent()
    return agent, list(agent.get_message_history())


def _help_entries() -> list[tuple[str, str]]:
    return [
        (
            "tree",
            "Open a TUI to inspect, restore, fork, or summarize prior conversation points",
        ),
        ("fork", "Create a new branch/session from a previous user message"),
        ("clone", "Duplicate the current active branch into a new autosave session"),
    ]


def _render_nodes(title: str, nodes: list[HistoryNode]) -> None:
    lines = [title]
    for ordinal, node in enumerate(nodes, start=1):
        marker = "*" if node.is_system else " "
        label = f" [{node.label}]" if node.label else ""
        lines.append(
            f"  {ordinal}. [{node.node_id}] {marker}{node.role}: {node.preview}{label}"
        )
    _emit_info("\n".join(lines))


def _tree_args(command: str) -> tuple[bool, str]:
    parts = command.split(maxsplit=2)
    if len(parts) >= 2 and parts[1].lower() in {"summary", "summarize"}:
        return True, parts[2].strip() if len(parts) == 3 else ""
    return False, parts[1].strip() if len(parts) >= 2 else ""


def _selection_from_command(command: str) -> str:
    return _tree_args(command)[1]


def _markdown_result(prompt: str) -> Any:
    from code_puppy.plugins.customizable_commands.register_callbacks import (
        MarkdownCommandResult,
    )

    return MarkdownCommandResult(prompt)


def _run_tree_menu(history: list[Any]) -> Any:
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(
            lambda: asyncio.run(
                TreeSelectionMenu(history=history, labels=_LABELS).run_async()
            )
        )
        return future.result(timeout=300)


def _resolve_or_menu(
    command: str, history: list[Any]
) -> tuple[HistoryNode | None, bool]:
    summarize, selection = _tree_args(command)
    if selection:
        nodes = selectable_nodes(history)
        node = resolve_node(selection, nodes)
        if node is None:
            _emit_warning(f"/tree: no history point matches '{selection}'")
        return node, summarize

    result = _run_tree_menu(history)
    if result.cancelled:
        _emit_warning("/tree: selection cancelled")
        return None, False
    return result.node, result.summarize


def _summarize_through(history: list[Any], node: HistoryNode) -> list[Any]:
    from code_puppy.agents._compaction import _run_summarization_core

    compacted, _summarized = _run_summarization_core(
        history_through(history, node.index),
        protected_tokens=0,
        with_protection=False,
        model_name=None,
    )
    return list(compacted)


def _restore_summary(agent: Any, history: list[Any], node: HistoryNode) -> bool:
    try:
        summarized_history = _summarize_through(history, node)
        agent.set_message_history(summarized_history)
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"/tree summary: failed to summarize history - {exc}")
        return True

    _emit_success(
        f"Summarized conversation through {node.role} message {node.index} "
        f"[{node.node_id}] into a fresh conversation ({len(summarized_history)} messages)."
    )
    return True


def _handle_tree(command: str) -> bool | Any:
    try:
        agent, history = _current_history()
    except Exception as exc:  # noqa: BLE001 - commands must fail soft.
        _emit_error(f"/tree: could not read current history - {exc}")
        return True

    nodes = selectable_nodes(history)
    if not nodes:
        _emit_warning("/tree: conversation history is empty - nothing to restore")
        return True

    try:
        node, summarize = _resolve_or_menu(command, history)
    except Exception as exc:  # noqa: BLE001
        _emit_warning(f"/tree TUI failed, falling back to text view: {exc}")
        _render_nodes("Conversation Tree:", build_nodes(history, _LABELS))
        return True

    if node is None:
        return True

    if summarize:
        return _restore_summary(agent, history, node)

    try:
        if node.is_userish:
            prompt = message_text(history[node.index]).strip()
            agent.set_message_history(history_before(history, node.index))
            _emit_success(
                f"Moved to parent of {node.role} message {node.index} [{node.node_id}]. "
                "Edit the restored prompt to create a branch."
            )
            return _markdown_result(prompt) if prompt else True

        agent.set_message_history(history_through(history, node.index))
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"/tree: failed to restore history - {exc}")
        return True

    _emit_success(
        f"Restored conversation to {node.role} message {node.index} [{node.node_id}]"
    )
    return True


def _handle_fork(command: str) -> bool | Any:
    try:
        agent, history = _current_history()
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"/fork: could not read current history - {exc}")
        return True

    nodes = user_nodes(history)
    if not nodes:
        _emit_warning("/fork: no previous user messages are available to fork")
        return True

    selection = _selection_from_command(command)
    if not selection:
        _render_nodes("Forkable User Messages:", nodes)
        _emit_warning("Usage: /fork <number|id>")
        return True

    node = resolve_node(selection, nodes)
    if node is None:
        _emit_warning(f"/fork: no user message matches '{selection}'")
        return True

    prompt = message_text(history[node.index]).strip()
    try:
        agent.set_message_history(history_before(history, node.index))
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"/fork: failed to create branch history - {exc}")
        return True

    _emit_success(
        f"Created branch before user message {node.index} [{node.node_id}]. "
        "Edit the restored prompt to continue from this branch."
    )
    return _markdown_result(prompt) if prompt else True


def _handle_clone() -> bool:
    try:
        agent, history = _current_history()
        if not history:
            _emit_warning("/clone: no active branch to clone")
            return True

        from code_puppy.config import AUTOSAVE_DIR, rotate_autosave_id
        from code_puppy.session_storage import save_session

        session_id = rotate_autosave_id()
        session_name = f"autosave_{session_id}"
        metadata = save_session(
            history=history,
            session_name=session_name,
            base_dir=Path(AUTOSAVE_DIR),
            timestamp=datetime.now().isoformat(),
            token_estimator=agent.estimate_tokens_for_message,
            auto_saved=True,
        )
        _emit_success(
            f"Cloned current active branch to new autosave session {session_id} "
            f"({metadata.message_count} messages)."
        )
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"/clone: failed to clone active branch - {exc}")
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


__all__ = [
    "_handle_custom_command",
    "_handle_fork",
    "_handle_tree",
    "_help_entries",
]
