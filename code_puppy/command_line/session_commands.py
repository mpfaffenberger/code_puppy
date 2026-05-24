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
