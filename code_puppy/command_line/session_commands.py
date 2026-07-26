"""Command handlers for Code Puppy - SESSION commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import logging
from pathlib import Path

from code_puppy.command_line.command_registry import register_command
from code_puppy.config import AUTOSAVE_DIR
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
            f"[bold magenta]Autosave Session[/bold magenta]: {session_name}\n"
            f"Files prefix: {Path(AUTOSAVE_DIR) / session_name}"
        )
        return True
    if tokens[1] == "new":
        new_name = rotate_session_name()
        emit_success(f"New autosave session: {new_name}")
        return True
    emit_warning("Usage: /session [id|new]")
    return True


@register_command(
    name="clear",
    description="Clear conversation history (rotates autosave; agent forgets prior turns)",
    usage="/clear",
    aliases=["cls"],
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
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.command_line.clipboard import get_clipboard_manager
    from code_puppy.config import finalize_autosave_session
    from code_puppy.messaging import emit_info, emit_system_message, emit_warning

    agent = get_current_agent()
    new_session_id = finalize_autosave_session()
    agent.clear_message_history()
    emit_warning("Conversation history cleared!")
    emit_system_message("The agent will not remember previous interactions.")
    emit_info(f"Auto-save session rotated to: {new_session_id}")

    # Also clear pending clipboard images so they don't leak into the next turn
    clipboard_manager = get_clipboard_manager()
    clipboard_count = clipboard_manager.get_pending_count()
    clipboard_manager.clear_pending()
    if clipboard_count > 0:
        emit_info(f"Cleared {clipboard_count} pending clipboard image(s)")
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
        from code_puppy.messaging.run_ui import is_run_active

        if is_run_active():
            from code_puppy.messaging.pause_controller import get_pause_controller

            get_pause_controller().request_compaction()
            emit_info("Compaction requested; it will run before the next model call.")
            return True

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
        else:
            # Default to summarization
            compacted, summarized_messages = current_agent.summarize_messages(
                history, with_protection=True
            )

        if not compacted:
            emit_error("Compaction failed. History unchanged.")
            return True

        agent.set_message_history(compacted)

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
            f"using {compaction_strategy} strategy"
            if compaction_strategy == "truncation"
            else "via summarization"
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
        "Quick Resume selected - finding latest session for "
        f"{format_quick_resume_scope(cwd, branch)}"
    )

    quick_resume_pickle = resolve_quick_resume_pickle(target_path)
    if not quick_resume_pickle:
        emit_info(
            "No previous session found for this scope; staying in current session."
        )
        return True

    session_path = Path(quick_resume_pickle)
    session_name = session_path.stem

    try:
        history = load_session(session_name, session_path.parent)
    except FileNotFoundError:
        logger.warning("Quick-resume session file not found: %s", session_path)
        emit_error(
            "Quick-resume session file was not found; staying in current session."
        )
        return True
    except Exception:
        logger.exception("Failed to quick-resume from %s", session_path)
        emit_error("Quick-resume failed; staying in current session.")
        return True

    agent = get_current_agent()
    agent.set_message_history(history)
    set_current_autosave_from_session_name(session_name)
    total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

    emit_success(
        f"Quick resume loaded: {len(history)} messages ({total_tokens} tokens)"
    )

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
        emit_warning("Usage: /dump_context <session_name>")
        return True

    session_name = tokens[1]
    # Enforce reserved-prefix + slug rules at every user-input write site
    # (the resolver enforces them for ``-r NAME``; this is the parallel
    # gate for ``/dump_context``). Without it, /dump_context bypasses
    # the validator that ``-r`` runs and lets a user squat the
    # ``auto_session_`` namespace or smuggle in a path-traversal name.
    if not is_valid_session_name(session_name, allow_reserved_prefix=False):
        emit_error(
            f"Invalid session name: {session_name!r}. "
            "Session names must be 1-128 chars of [A-Za-z0-9._-] "
            "and may not start with 'auto_session_' (reserved)."
        )
        return True

    agent = get_current_agent()
    if not agent.get_message_history():
        emit_warning("No message history to dump!")
        return True

    try:
        # The user-facing success line is preserved verbatim via
        # ``success_message_template`` so /dump_context UX doesn't
        # regress. The silent save-back paths (``-r``, periodic
        # autosave) omit the template and stay quiet.
        persist_named_session(
            agent,
            session_name,
            base_dir=Path(AUTOSAVE_DIR),
            success_message_template=(
                "\u2705 Context saved: {message_count} messages "
                "({total_tokens} tokens)\n"
                "\U0001f4c1 Files: {pickle_path}, {metadata_path}"
            ),
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
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import rotate_session_name
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning("Usage: /load_context <session_name>")
        return True

    session_name = tokens[1]
    sessions_dir = Path(AUTOSAVE_DIR)
    session_path = sessions_dir / f"{session_name}.pkl"

    try:
        history = load_session(session_name, sessions_dir)
    except FileNotFoundError:
        emit_error(f"Context file not found: {session_path}")
        available = list_sessions(sessions_dir)
        if available:
            emit_info(f"Available contexts: {', '.join(available)}")
        return True
    except Exception as exc:
        emit_error(f"Failed to load context: {exc}")
        return True

    agent = get_current_agent()
    agent.set_message_history(history)
    total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

    # Rotate the singleton to a fresh ``auto_session_<TS>`` so subsequent
    # autosaves do NOT overwrite the loaded snapshot. This asymmetry with
    # ``-r NAME`` (which pins and saves back in place) is INTENTIONAL --
    # the two verbs encode two different intents:
    #
    #   * ``/dump_context NAME`` + ``/load_context NAME`` are a snapshot
    #     pair (think ``pg_dump`` / ``pg_restore``, save games, git
    #     stash). The named file is a stable reference point; loading
    #     it lets you inspect / branch from it without dirtying the
    #     original.
    #   * ``-r NAME`` / ``--resume NAME`` is a continuation verb (pick
    #     up where you left off). That path pins and saves back.
    #
    # Origin: commit ``cc04629b`` (Mike Pfaffenberger, 2025-10-11)
    # introduced this rotate-on-load behavior as a deliberate design
    # choice; the commit message explicitly says "Automatically rotate
    # session ID when loading saved context to prevent overwrites." The
    # ``-r`` flag was added 4 months later (commit ``92bb0f90``) and
    # the asymmetry was preserved -- on purpose. Do NOT "unify" these
    # two paths in the name of symmetry; you'd be deleting the encoded
    # distinction between snapshot-load and continuation-resume.
    #
    # If a user wants to continue working on the loaded snapshot in
    # place, the explicit move is ``/load_context NAME`` followed by
    # ``/dump_context NAME`` later -- or relaunch via ``-r NAME``.
    new_autosave_id = rotate_session_name()

    emit_success(
        f"\u2705 Context loaded: {len(history)} messages "
        f"({total_tokens} tokens)\n"
        f"\U0001f4c1 From: {session_path}\n"
        f"\U0001f504 Autosave rotated to: {new_autosave_id} "
        f"(snapshot at {session_path.name} is preserved; further "
        f"autosaves land in the new session)"
    )

    # Display recent message history for context
    from code_puppy.command_line.autosave_menu import display_resumed_history

    display_resumed_history(history)

    return True
