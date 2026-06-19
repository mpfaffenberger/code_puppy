"""Plugin callbacks for `/tree`, `/fork`, and automatic tree persistence."""

from __future__ import annotations

from pathlib import Path

from code_puppy.callbacks import register_callback
from code_puppy.plugins.tree_sessions.tree import SessionTree


def _tree_path(session_name: str | None = None) -> Path:
    from code_puppy.config import AUTOSAVE_DIR, get_current_autosave_session_name

    name = session_name or get_current_autosave_session_name()
    return Path(AUTOSAVE_DIR) / f"{name}.jsonl"


def _current_tree() -> SessionTree:
    return SessionTree(_tree_path())


async def _record_run(*_args, **_kwargs):
    try:
        from code_puppy.agents import get_current_agent

        _current_tree().sync_history(get_current_agent().get_message_history())
    except Exception:
        return None
    return None


def _command(command: str, name: str):
    if name not in {"tree", "fork"}:
        return None
    from code_puppy.agents import get_current_agent
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tree = _current_tree()
    agent = get_current_agent()
    tree.sync_history(agent.get_message_history())
    parts = command.split()

    if name == "tree":
        if len(parts) >= 3 and parts[1] == "label":
            try:
                tree.set_label(parts[2], " ".join(parts[3:]) or None)
                emit_success("Session tree label updated")
            except KeyError as exc:
                emit_error(str(exc))
        else:
            emit_info(tree.render())
        return True

    if len(parts) < 2:
        emit_warning("Usage: /fork <entry-id> [new-session-name]")
        return True
    entry_id = next(
        (entry.id for entry in tree.entries.values() if entry.id.startswith(parts[1])),
        None,
    )
    if entry_id is None:
        emit_error(f"Unknown or ambiguous tree entry: {parts[1]}")
        return True
    if len(parts) >= 3:
        destination = _tree_path(parts[2])
        try:
            tree.fork_to(destination, entry_id)
            emit_success(f"Forked session path to {destination}")
        except FileExistsError:
            emit_error(f"Session already exists: {destination}")
        return True
    tree.branch(entry_id)
    agent.set_message_history(tree.history())
    agent.invalidate_dynamic_prompt()
    emit_success(f"Moved session to branch point {entry_id[:8]}")
    return True


def _help():
    return [
        ("/tree [label ID TEXT]", "View or label the branching session tree"),
        ("/fork <ID> [NAME]", "Branch in place or extract a new session"),
    ]


register_callback("agent_run_end", _record_run)
register_callback("custom_command", _command)
register_callback("custom_command_help", _help)
