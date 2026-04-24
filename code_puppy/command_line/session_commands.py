"""Command handlers for Code Puppy - SESSION commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

from datetime import datetime
from pathlib import Path

from code_puppy.command_line.command_registry import register_command
from code_puppy.config import CONTEXTS_DIR
from code_puppy.session_storage import list_sessions, load_session, save_session


# Import get_commands_help from command_handler to avoid circular imports
# This will be defined in command_handler.py
def get_commands_help():
    """Lazy import to avoid circular dependency."""
    from code_puppy.command_line.command_handler import get_commands_help as _gch

    return _gch()


@register_command(
    name="session",
    description="Show or rotate autosave session ID",
    usage="/session [id|new]",
    aliases=["s"],
    category="session",
    detailed_help="""
    Manage autosave sessions.

    Commands:
      /session        Show current session ID
      /session id     Show current session ID
      /session new    Create new session and rotate ID

    Sessions are used for auto-saving conversation history.
    """,
)
def handle_session_command(command: str) -> bool:
    """Handle /session command."""
    from code_puppy.config import (
        AUTOSAVE_DIR,
        get_current_autosave_id,
        get_current_autosave_session_name,
        rotate_autosave_id,
    )
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    tokens = command.split()

    if len(tokens) == 1 or tokens[1] == "id":
        sid = get_current_autosave_id()
        emit_info(
            f"[bold magenta]Autosave Session[/bold magenta]: {sid}\n"
            f"Files prefix: {Path(AUTOSAVE_DIR) / get_current_autosave_session_name()}"
        )
        return True
    if tokens[1] == "new":
        new_sid = rotate_autosave_id()
        emit_success(f"New autosave session id: {new_sid}")
        return True
    emit_warning("Usage: /session [id|new]")
    return True


@register_command(
    name="compact",
    description="Summarize and compact current chat history (uses compaction_strategy config)",
    usage="/compact",
    category="session",
)
def handle_compact_command(command: str) -> bool:
    """Compact message history using configured strategy."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import get_compaction_strategy, get_protected_token_count
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    try:
        agent = get_current_agent()
        history = agent.get_message_history()
        if not history:
            emit_warning("No history to compact yet. Ask me something first!")
            return True

        current_agent = get_current_agent()
        before_tokens = sum(
            current_agent.estimate_tokens_for_message(m) for m in history
        )
        compaction_strategy = get_compaction_strategy()
        protected_tokens = get_protected_token_count()
        emit_info(
            f"🤔 Compacting {len(history)} messages using {compaction_strategy} strategy... (~{before_tokens} tokens)"
        )

        current_agent = get_current_agent()
        if compaction_strategy == "truncation":
            from code_puppy.agents._compaction import truncate

            compacted = truncate(history, protected_tokens)
            summarized_messages = []  # No summarization in truncation mode
        elif compaction_strategy == "continuity":
            from code_puppy.agents._compaction import compact

            compacted, summarized_messages = compact(
                current_agent,
                history,
                current_agent._get_model_context_length(),
                current_agent._estimate_context_overhead(),
                force=True,
            )
        else:
            # Default to summarization
            compacted, summarized_messages = current_agent.summarize_messages(
                history, with_protection=True
            )

        if not compacted:
            emit_error("Compaction failed. History unchanged.")
            return True

        agent.set_message_history(compacted)
        compacted_hashes = getattr(agent, "_compacted_message_hashes", None)
        if compacted_hashes is not None:
            for message in summarized_messages:
                compacted_hashes.add(agent.hash_message(message))

        current_agent = get_current_agent()
        after_tokens = sum(
            current_agent.estimate_tokens_for_message(m) for m in compacted
        )
        reduction_pct = (
            ((before_tokens - after_tokens) / before_tokens * 100)
            if before_tokens > 0
            else 0
        )

        strategy_info = (
            "via summarization"
            if compaction_strategy == "summarization"
            else f"using {compaction_strategy} strategy"
        )
        emit_success(
            f"✨ Done! History: {len(history)} → {len(compacted)} messages {strategy_info}\n"
            f"🏦 Tokens: {before_tokens:,} → {after_tokens:,} ({reduction_pct:.1f}% reduction)"
        )
        return True
    except Exception as e:
        emit_error(f"/compact error: {e}")
        return True


@register_command(
    name="continuity",
    description="Show continuity compaction memory and archives",
    usage="/continuity [show|tasks|diagnostics|archives search <query>|archives show <id>]",
    category="session",
)
def handle_continuity_command(command: str) -> bool:
    """Inspect continuity memory state for the current session."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.agents.continuity_compaction.storage import (
        archive_preview,
        build_archive_index,
        read_durable_state,
        read_observation_archive,
        search_archive_index,
    )
    from code_puppy.config import (
        get_continuity_compaction_archive_retention_count,
        get_continuity_compaction_archive_retention_days,
        get_continuity_compaction_archive_retrieval_count,
        get_continuity_compaction_archive_retrieval_enabled,
        get_continuity_compaction_predictive_trigger_min_ratio,
        get_continuity_compaction_semantic_task_detection,
        get_continuity_compaction_semantic_timeout_seconds,
    )
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
        lines.extend(
            [
                "Task ledger:",
                *_continuity_task_lines(state.tasks, limit=8),
            ]
        )
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
                    f"{item.get('tool_name')}: {signals or item.get('key_signal') or 'no signal'}"
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
        "Usage: /continuity [show|tasks|diagnostics|archives search <query>|archives show <id>]"
    )
    return True


def _continuity_task_lines(tasks, *, limit: int) -> list[str]:
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


@register_command(
    name="truncate",
    description="Truncate history to N most recent messages (e.g., /truncate 10)",
    usage="/truncate <N>",
    category="session",
)
def handle_truncate_command(command: str) -> bool:
    """Truncate message history to N most recent messages."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_error("Usage: /truncate <N> (where N is the number of messages to keep)")
        return True

    try:
        n = int(tokens[1])
        if n < 1:
            emit_error("N must be a positive integer")
            return True
    except ValueError:
        emit_error("N must be a valid integer")
        return True

    agent = get_current_agent()
    history = agent.get_message_history()
    if not history:
        emit_warning("No history to truncate yet. Ask me something first!")
        return True

    if len(history) <= n:
        emit_info(
            f"History already has {len(history)} messages, which is <= {n}. Nothing to truncate."
        )
        return True

    # Always keep the first message (system message) and then keep the N-1 most recent messages
    truncated_history = [history[0]] + history[-(n - 1) :] if n > 1 else [history[0]]

    agent.set_message_history(truncated_history)
    emit_success(
        f"Truncated message history from {len(history)} to {len(truncated_history)} messages (keeping system message and {n - 1} most recent)"
    )
    return True


@register_command(
    name="autosave_load",
    description="Load an autosave session interactively",
    usage="/autosave_load",
    aliases=["resume"],
    category="session",
)
def handle_autosave_load_command(command: str) -> bool:
    """Load an autosave session."""
    # Return a special marker to indicate we need to run async autosave loading
    return "__AUTOSAVE_LOAD__"


@register_command(
    name="dump_context",
    description="Save current message history to file",
    usage="/dump_context <name>",
    category="session",
)
def handle_dump_context_command(command: str) -> bool:
    """Dump message history to a file."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning("Usage: /dump_context <session_name>")
        return True

    session_name = tokens[1]
    agent = get_current_agent()
    history = agent.get_message_history()

    if not history:
        emit_warning("No message history to dump!")
        return True

    try:
        metadata = save_session(
            history=history,
            session_name=session_name,
            base_dir=Path(CONTEXTS_DIR),
            timestamp=datetime.now().isoformat(),
            token_estimator=agent.estimate_tokens_for_message,
        )
        emit_success(
            f"✅ Context saved: {metadata.message_count} messages ({metadata.total_tokens} tokens)\n"
            f"📁 Files: {metadata.pickle_path}, {metadata.metadata_path}"
        )
        return True

    except Exception as exc:
        emit_error(f"Failed to dump context: {exc}")
        return True


@register_command(
    name="load_context",
    description="Load message history from file",
    usage="/load_context <name>",
    category="session",
)
def handle_load_context_command(command: str) -> bool:
    """Load message history from a file."""
    from rich.text import Text

    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import rotate_autosave_id
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning("Usage: /load_context <session_name>")
        return True

    session_name = tokens[1]
    contexts_dir = Path(CONTEXTS_DIR)
    session_path = contexts_dir / f"{session_name}.pkl"

    try:
        history = load_session(session_name, contexts_dir)
    except FileNotFoundError:
        emit_error(f"Context file not found: {session_path}")
        available = list_sessions(contexts_dir)
        if available:
            emit_info(f"Available contexts: {', '.join(available)}")
        return True
    except Exception as exc:
        emit_error(f"Failed to load context: {exc}")
        return True

    agent = get_current_agent()
    agent.set_message_history(history)
    total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

    # Rotate autosave id to avoid overwriting any existing autosave
    try:
        new_id = rotate_autosave_id()
        autosave_info = Text.from_markup(
            f"\n[dim]Autosave session rotated to: {new_id}[/dim]"
        )
    except Exception:
        autosave_info = Text("")

    # Build the success message with proper Text concatenation
    success_msg = Text(
        f"✅ Context loaded: {len(history)} messages ({total_tokens} tokens)\n"
        f"📁 From: {session_path}"
    )
    success_msg.append_text(autosave_info)
    emit_success(success_msg)

    # Display recent message history for context
    from code_puppy.command_line.autosave_menu import display_resumed_history

    display_resumed_history(history)

    return True
