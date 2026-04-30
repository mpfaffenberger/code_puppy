"""Register the Continuity compaction plugin."""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback

from .config import (
    CONFIG_KEYS,
    get_continuity_compaction_archive_retention_count,
    get_continuity_compaction_archive_retention_days,
    get_continuity_compaction_archive_retrieval_count,
    get_continuity_compaction_archive_retrieval_enabled,
    get_continuity_compaction_predictive_trigger_min_ratio,
    get_continuity_compaction_semantic_task_detection,
    get_continuity_compaction_semantic_timeout_seconds,
)
from .engine import compact_continuity
from .archives import (
    archive_preview,
    build_archive_index,
    read_observation_archive,
    search_archive_index,
)
from .storage import read_durable_state

_STRATEGY_NAME = "continuity"


def _register_config_keys() -> tuple[str, ...]:
    return CONFIG_KEYS


def _register_compaction_strategies() -> list[dict[str, str]]:
    return [
        {
            "name": _STRATEGY_NAME,
            "description": "Task-scoped durable memory with archived bulky observations",
        }
    ]


def _compact_message_history(
    strategy: str,
    agent: Any,
    messages: list[Any],
    model_max: int,
    context_overhead: int,
    model_name: str | None = None,
    force: bool = False,
    total_tokens: int | None = None,
    proportion_used: float | None = None,
) -> dict[str, Any] | None:
    if strategy != _STRATEGY_NAME:
        return None

    compacted, dropped = compact_continuity(
        agent=agent,
        messages=messages,
        model_max=model_max,
        context_overhead=context_overhead,
        model_name=model_name,
        force=force,
    )
    return {"handled": True, "messages": compacted, "dropped_messages": dropped}


def _custom_help() -> list[tuple[str, str]]:
    return [
        (
            "continuity",
            "Show Continuity compaction memory, diagnostics, tasks, and archives",
        )
    ]


def _handle_custom_command(command: str, name: str) -> bool | None:
    if name != "continuity":
        return None
    return _handle_continuity_command(command)


def _handle_continuity_command(command: str) -> bool:
    """Inspect continuity memory state for the current session."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_info, emit_warning

    tokens = command.split()
    action = tokens[1].lower() if len(tokens) > 1 else "show"

    try:
        agent = get_current_agent()
        state = read_durable_state(agent)
        archive_index = build_archive_index(agent)
    except Exception as exc:
        emit_error(f"/continuity error: {exc}")
        return True

    if action in {"show", "status"}:
        if state is None:
            emit_warning("No continuity memory has been written for this session yet.")
            return True
        current_constraints = []
        for task in state.tasks:
            if task.task_id == state.current_task_id:
                current_constraints = task.constraints
                break
        lines = [
            "[bold magenta]Continuity Memory[/bold magenta]",
            f"Current task: {state.current_task or 'unknown'}",
            f"Latest request: {state.latest_user_request or 'unknown'}",
            f"Semantic status: {state.semantic_status or 'unknown'}",
            f"Archive count: {len(archive_index)}",
            "Active constraints:",
        ]
        constraints = [*state.global_constraints, *current_constraints]
        lines.extend(f"- {item}" for item in constraints[:12] or ["none"])
        lines.extend(["Task ledger:", *_continuity_task_lines(state.tasks, limit=8)])
        emit_info("\n".join(lines))
        return True

    if action == "tasks":
        if state is None:
            emit_warning("No continuity task memory has been written yet.")
            return True
        lines = [
            "[bold magenta]Continuity Tasks[/bold magenta]",
            *_continuity_task_lines(state.tasks, limit=100),
        ]
        emit_info("\n".join(lines))
        return True

    if action == "diagnostics":
        lines = [
            "[bold magenta]Continuity Diagnostics[/bold magenta]",
            f"semantic_enabled: {get_continuity_compaction_semantic_task_detection()}",
            f"semantic_timeout_seconds: {get_continuity_compaction_semantic_timeout_seconds()}",
            f"predictive_trigger_min_ratio: {get_continuity_compaction_predictive_trigger_min_ratio():.3f}",
            f"archive_retrieval_enabled: {get_continuity_compaction_archive_retrieval_enabled()}",
            f"archive_retrieval_count: {get_continuity_compaction_archive_retrieval_count()}",
            f"archive_retention_days: {get_continuity_compaction_archive_retention_days()}",
            f"archive_retention_count: {get_continuity_compaction_archive_retention_count()}",
            f"archive_count: {len(archive_index)}",
        ]
        if state is not None:
            lines.extend(
                [
                    f"schema_version: {state.schema_version}",
                    f"last_semantic_status: {state.semantic_status or 'unknown'}",
                    f"fallback_reason: {state.semantic_error or 'none'}",
                    f"retrieved_archives: {len(state.retrieved_archive_signals)}",
                ]
            )
        emit_info("\n".join(lines))
        return True

    if action == "archives":
        return _handle_archive_command(tokens, command, agent)

    emit_warning(
        "Usage: /continuity [show|tasks|diagnostics|archives search <query>|archives show <id>]"
    )
    return True


def _handle_archive_command(tokens: list[str], command: str, agent: Any) -> bool:
    from code_puppy.messaging import emit_info, emit_warning

    if len(tokens) < 3:
        emit_warning(
            "Usage: /continuity archives search <query> or /continuity archives show <id>"
        )
        return True
    archive_action = tokens[2].lower()
    if archive_action == "search":
        query = command.split("search", 1)[1].strip() if "search" in command else ""
        if not query:
            emit_warning("Usage: /continuity archives search <query>")
            return True
        results = search_archive_index(agent, query, limit=10)
        if not results:
            emit_info(f"No archive signals matched: {query}")
            return True
        lines = [f"[bold magenta]Archive Search[/bold magenta]: {query}"]
        for item in results:
            signals = "; ".join((item.get("key_signals") or [])[:2])
            lines.append(
                f"- {item.get('observation_id')} [{item.get('status')}] "
                f"{item.get('tool_name')}: "
                f"{signals or item.get('key_signal') or 'no signal'}"
            )
        emit_info("\n".join(lines))
        return True
    if archive_action == "show":
        if len(tokens) < 4:
            emit_warning("Usage: /continuity archives show <id>")
            return True
        record = read_observation_archive(agent, tokens[3])
        if record is None:
            emit_warning(f"Archive observation not found: {tokens[3]}")
            return True
        emit_info(
            "[bold magenta]Archive Observation[/bold magenta]\n"
            + archive_preview(record)
        )
        return True
    emit_warning(
        "Usage: /continuity archives search <query> or /continuity archives show <id>"
    )
    return True


def _continuity_task_lines(tasks: list[Any], *, limit: int) -> list[str]:
    if not tasks:
        return ["- none"]
    lines: list[str] = []
    for task in tasks[-limit:]:
        files = ", ".join(task.active_files[:3])
        files_suffix = f" | files: {files}" if files else ""
        summary_suffix = f" | {task.summary}" if task.summary else ""
        lines.append(
            f"- [{task.status}] {task.task_id}: {task.title}{summary_suffix}{files_suffix}"
        )
    return lines


register_callback("register_config_keys", _register_config_keys)
register_callback("register_compaction_strategies", _register_compaction_strategies)
register_callback("compact_message_history", _compact_message_history)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
