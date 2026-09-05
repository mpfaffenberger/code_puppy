"""Command handlers for Code Puppy - SESSION commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import logging
from pathlib import Path

from code_puppy.command_line.command_registry import register_command
from code_puppy.config import AUTOSAVE_DIR
from code_puppy.i18n import t
from code_puppy.session_storage import list_sessions, load_session

logger = logging.getLogger(__name__)


def _parse_quick_resume_target(command: str) -> str:
    """Extract the optional PATH arg from a ``/quick-resume`` command string.

    OS-agnostic: splits off only the command word and keeps the remainder
    verbatim so Windows paths (``C:\\Users\\...``) retain their backslashes --
    ``shlex`` POSIX mode would silently strip them. A single pair of matching
    outer quotes (used for paths containing spaces) is removed on every OS.
    Returns ``"."`` (current directory) when no path was given.
    """
    parts = command.split(maxsplit=1)
    target_path = parts[1].strip() if len(parts) > 1 else "."
    if (
        len(target_path) >= 2
        and target_path[0] in ("'", '"')
        and target_path[-1] == target_path[0]
    ):
        target_path = target_path[1:-1]
    return target_path or "."


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
        get_current_session_name,
        rotate_session_name,
    )
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    tokens = command.split()

    if len(tokens) == 1 or tokens[1] == "id":
        session_name = get_current_session_name()
        emit_info(
            t(
                "cmd.session.info",
                name=session_name,
                prefix=str(Path(AUTOSAVE_DIR) / session_name),
            )
        )
        return True
    if tokens[1] == "new":
        new_name = rotate_session_name()
        emit_success(t("cmd.session.new", name=new_name))
        return True
    emit_warning(t("cmd.session.usage"))
    return True


@register_command(
    name="clear",
    description=(
        "Clear conversation history (rotates autosave). Bare word `clear` also works."
    ),
    usage="/clear",
    aliases=["cls", "new"],
    category="session",
    detailed_help="""
    Wipe the current conversation history so the agent starts fresh.

    What it does:
      - Finalizes & rotates the current autosave session (so prior history
        is preserved on disk and recoverable via /autosave_load)
      - Clears the in-memory message history for the active agent
      - Drops any pending clipboard images queued for the next turn

    The bare word `clear` (no slash) also works, for backward compatibility.
    """,
)
def handle_clear_command(command: str) -> bool:
    """Clear conversation history and rotate autosave session."""
    from code_puppy.agents._builder import reset_model_fallback_warnings
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.command_line.clipboard import get_clipboard_manager
    from code_puppy.config import finalize_autosave_session
    from code_puppy.messaging import emit_info, emit_system_message, emit_warning

    agent = get_current_agent()
    new_session_id = finalize_autosave_session()
    agent.clear_message_history()
    # New conversation: a stale pinned-model warning deserves to resurface
    # rather than staying silenced from the previous conversation forever.
    reset_model_fallback_warnings()
    emit_warning(t("cmd.clear.cleared"))
    emit_system_message(t("cmd.clear.agent_notice"))
    emit_info(t("cmd.clear.session_rotated", id=new_session_id))

    # Also clear pending clipboard images so they don't leak into the next turn
    clipboard_manager = get_clipboard_manager()
    clipboard_count = clipboard_manager.get_pending_count()
    clipboard_manager.clear_pending()
    if clipboard_count > 0:
        emit_info(t("cmd.clear.clipboard_cleared", count=clipboard_count))
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
    from code_puppy.config import (
        auto_save_session_if_enabled,
        get_compaction_strategy,
    )
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    try:
        from code_puppy.messaging.run_ui import is_run_active

        if is_run_active():
            from code_puppy.messaging.pause_controller import get_pause_controller

            get_pause_controller().request_compaction()
            emit_info(t("cmd.compact.queued"))
            return True

        agent = get_current_agent()
        history = agent.get_message_history()
        if not history:
            emit_warning(t("cmd.compact.no_history"))
            return True

        before_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)
        compaction_strategy = get_compaction_strategy()
        emit_info(
            t(
                "cmd.compact.compacting",
                count=len(history),
                strategy=compaction_strategy,
                tokens=f"{before_tokens:,}",
            )
        )

        # compact_now applies no trigger of its own, so a manual /compact
        # always compacts — matching the historical command semantics.
        from code_puppy.agents._compaction import (
            build_compaction_strategy,
            resolve_agent_model,
            run_compaction_sync,
        )

        compacted = run_compaction_sync(
            build_compaction_strategy(),
            history,
            model=resolve_agent_model(agent),
        )

        if not compacted:
            emit_error(t("cmd.compact.failed"))
            return True

        agent.set_message_history(list(compacted))

        # Slash commands run outside the normal turn-finalization path, which
        # is where updated history is ordinarily auto-saved. Persist now so a
        # subsequent /quit + --quick-resume restores the compacted history.
        if not auto_save_session_if_enabled(force=True):
            return True

        after_tokens = sum(agent.estimate_tokens_for_message(m) for m in compacted)
        reduction_pct = (
            ((before_tokens - after_tokens) / before_tokens * 100)
            if before_tokens > 0
            else 0
        )

        # Whole-sentence keys per strategy so translators can reorder/inflect;
        # do NOT reintroduce a shared template with a ``{strategy_info}``
        # fragment — gluing doesn't agree grammatically outside English.
        success_key = (
            "cmd.compact.success.truncation"
            if compaction_strategy == "truncation"
            else "cmd.compact.success.summarization"
        )
        emit_success(
            t(
                success_key,
                before_count=len(history),
                after_count=len(compacted),
                strategy=compaction_strategy,
                before_tokens=f"{before_tokens:,}",
                after_tokens=f"{after_tokens:,}",
                reduction_pct=f"{reduction_pct:.1f}",
            )
        )
        return True
    except Exception as e:
        emit_error(t("cmd.compact.error", error=e))
        return True


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
        emit_error(t("cmd.truncate.usage"))
        return True

    try:
        n = int(tokens[1])
        if n < 1:
            emit_error(t("cmd.truncate.must_be_positive"))
            return True
    except ValueError:
        emit_error(t("cmd.truncate.invalid_int"))
        return True

    agent = get_current_agent()
    history = agent.get_message_history()
    if not history:
        emit_warning(t("cmd.truncate.no_history"))
        return True

    if len(history) <= n:
        emit_info(t("cmd.truncate.already_short", current=len(history), n=n))
        return True

    # Keep the first (system) message plus the N-1 most recent, delegating to
    # the harness sliding window so tool_call/tool_return pairs are never
    # severed the way naive list slicing could sever them.
    from pydantic_ai_harness.compaction import SlidingWindowCompaction

    from code_puppy.agents._compaction import (
        resolve_agent_model,
        run_compaction_sync,
    )

    truncated_history = run_compaction_sync(
        # max_messages=1 satisfies constructor validation only — compact_now
        # drives the strategy unconditionally, so no trigger is consulted.
        SlidingWindowCompaction(max_messages=1, keep_messages=max(1, n - 1)),
        history,
        model=resolve_agent_model(agent),
    )

    agent.set_message_history(list(truncated_history))
    emit_success(
        t(
            "cmd.truncate.success",
            before=len(history),
            after=len(truncated_history),
            kept=n - 1,
        )
    )
    return True


@register_command(
    name="autosave_load",
    description="Load an autosave session interactively, or by name",
    usage="/autosave_load [session_name]",
    aliases=["resume"],
    category="session",
    detailed_help="""
    Load an autosave session.

    Commands:
      /resume                    Open interactive session picker
      /resume <session_name>     Load session directly by name

    Examples:
      /resume
      /resume auto_session_20260214_175543
    """,
)
def handle_autosave_load_command(command: str) -> "bool | str":
    """Load an autosave session.

    If no session name is provided, opens interactive picker.
    If session name is provided, loads that session directly.

    Returns:
        "__AUTOSAVE_LOAD__" for picker, "__AUTOSAVE_LOAD_DIRECT__:<name>" for direct load.
    """
    tokens = command.split()

    if len(tokens) == 1:
        # No argument = open picker
        return "__AUTOSAVE_LOAD__"

    # Session name provided = load directly
    session_name = tokens[1]
    return f"__AUTOSAVE_LOAD_DIRECT__:{session_name}"


@register_command(
    name="quick-resume",
    description="Load the latest autosave for a directory/path and git branch",
    usage="/quick-resume [path]",
    hidden_aliases=["qr"],
    category="session",
    detailed_help="""
    Resume the latest autosaved session for a path (defaults to the current
    directory), scoped to the nearest git worktree root and branch when
    available.

    If the path is not inside a git repository (or git is unavailable), this
    gracefully falls back to the relevant directory/workspace scope.
    """,
)
def handle_quick_resume_command(command: str) -> bool:
    """Load the latest autosave for this directory/path + branch into the agent."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import (
        format_quick_resume_scope,
        get_quick_resume_location,
        resolve_quick_resume_pickle,
        set_current_autosave_from_session_name,
    )
    from code_puppy.messaging import emit_error, emit_info, emit_success

    # Parse an optional path argument (OS-agnostic; preserves Windows
    # backslashes -- see _parse_quick_resume_target).
    target_path = _parse_quick_resume_target(command)

    # Diagnostic identifies the scope without leaking full local paths.
    cwd, branch = get_quick_resume_location(target_path)
    emit_info(
        t("cmd.quick_resume.searching", scope=format_quick_resume_scope(cwd, branch))
    )

    quick_resume_pickle = resolve_quick_resume_pickle(target_path)
    if not quick_resume_pickle:
        emit_info(t("cmd.quick_resume.no_session"))
        return True

    session_path = Path(quick_resume_pickle)
    session_name = session_path.stem

    try:
        history = load_session(session_name, session_path.parent)
    except FileNotFoundError:
        logger.warning("Quick-resume session file not found: %s", session_path)
        emit_error(t("cmd.quick_resume.file_not_found"))
        return True
    except Exception:
        logger.exception("Failed to quick-resume from %s", session_path)
        emit_error(t("cmd.quick_resume.failed"))
        return True

    agent = get_current_agent()
    agent.set_message_history(history)
    set_current_autosave_from_session_name(session_name)
    total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

    emit_success(t("cmd.quick_resume.success", count=len(history), tokens=total_tokens))

    # Best-effort history preview; failure must not abort a successful resume.
    try:
        from code_puppy.command_line.autosave_menu import display_resumed_history

        display_resumed_history(history)
    except Exception:
        logger.debug("Unable to display quick-resume history preview", exc_info=True)

    return True


@register_command(
    name="dump_context",
    description="Save current message history to file",
    usage="/dump_context <name>",
    category="session",
)
def handle_dump_context_command(command: str) -> bool:
    """Dump message history to a file."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_warning
    from code_puppy.session_lifecycle import (
        is_valid_session_name,
        persist_named_session,
    )

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning(t("cmd.dump_context.usage"))
        return True

    session_name = tokens[1]
    if not is_valid_session_name(session_name, allow_reserved_prefix=False):
        emit_error(t("cmd.dump_context.invalid_name", name=repr(session_name)))
        return True

    agent = get_current_agent()
    if not agent.get_message_history():
        emit_warning(t("cmd.dump_context.no_history"))
        return True

    try:
        # Success line preserved verbatim via ``success_message_key``; the
        # silent save-back paths (``-r``, periodic autosave) omit it. NOTE:
        # pass a catalog KEY, not raw text — ``t()`` is the only safe
        # interpolator (docs/I18N.md); ``str.format`` on catalog text is
        # forbidden.
        persist_named_session(
            agent,
            session_name,
            base_dir=Path(AUTOSAVE_DIR),
            success_message_key="cmd.dump_context.success",
        )
        return True

    except Exception as exc:
        emit_error(t("cmd.dump_context.failed", error=exc))
        return True


@register_command(
    name="load_context",
    description="Load message history from file",
    usage="/load_context <name>",
    category="session",
)
def handle_load_context_command(command: str) -> bool:
    """Load message history from a file."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import rotate_session_name
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.session_storage import compute_scope_key

    tokens = command.split()
    # Opt-in scoping: a trailing "cwd"/"--cwd" token filters the
    # not-found fallback listing to the current directory's sessions.
    # Default (no trailing token) keeps behaviour byte-for-byte identical.
    cwd_flag = len(tokens) == 3 and tokens[2] in ("cwd", "--cwd")
    if cwd_flag:
        tokens = tokens[:2]
    if len(tokens) != 2:
        emit_warning(t("cmd.load_context.usage"))
        return True

    session_name = tokens[1]
    sessions_dir = Path(AUTOSAVE_DIR)
    session_path = sessions_dir / f"{session_name}.json"

    try:
        history = load_session(session_name, sessions_dir)
    except FileNotFoundError:
        emit_error(t("cmd.load_context.not_found", path=session_path))
        scope_key = compute_scope_key(Path.cwd()) if cwd_flag else None
        available = list_sessions(sessions_dir, scope_key=scope_key)
        if available:
            emit_info(t("cmd.load_context.available", contexts=", ".join(available)))
        return True
    except Exception as exc:
        emit_error(t("cmd.load_context.failed", error=exc))
        return True

    agent = get_current_agent()
    agent.set_message_history(history)
    total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

    # Rotate the singleton to a fresh ``auto_session_<TS>`` so autosaves don't
    # overwrite the loaded snapshot — an INTENTIONAL asymmetry with ``-r NAME``
    # (which pins and saves back in place). The verbs encode two intents:
    #   * /dump + /load are a snapshot pair (pg_dump/restore, save games): the
    #     named file stays a stable reference point you branch from.
    #   * -r/--resume is a continuation verb: pins and saves back.
    # Origin: commit ``cc04629b`` (2025-10-11) introduced rotate-on-load; ``-r``
    # came 4 months later (``92bb0f90``) and the asymmetry was kept on purpose.
    # Do NOT "unify" these paths — you'd delete the snapshot-vs-resume
    # distinction. To keep working in place, /load_context then dump later, or
    # relaunch with -r.
    new_autosave_id = rotate_session_name()

    emit_success(
        t(
            "cmd.load_context.success",
            count=len(history),
            tokens=total_tokens,
            path=session_path,
            session_id=new_autosave_id,
            file=session_path.name,
        )
    )

    # Display recent message history for context
    from code_puppy.command_line.autosave_menu import display_resumed_history

    display_resumed_history(history)

    return True
