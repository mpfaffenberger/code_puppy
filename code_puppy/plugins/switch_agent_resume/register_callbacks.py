"""Register /switch-agent and /sa custom commands.

/switch-agent <agent>  — switch agent + auto-resume last terminal session
/switch-agent          — show interactive agent picker, then switch + resume
/sa                    — alias for /switch-agent
"""

import datetime
import os
from pathlib import Path

from code_puppy.callbacks import register_callback


def _do_switch_and_resume(agent_name: str) -> bool:
    """Switch to agent_name and auto-resume this terminal's last session."""
    import uuid

    from rich.text import Text

    from code_puppy.agents import get_current_agent, set_current_agent
    from code_puppy.config import (
        AUTOSAVE_DIR,
        finalize_autosave_session,
        get_current_autosave_session_name,
        get_last_terminal_session,
        record_terminal_session,
        set_current_autosave_from_session_name,
    )
    from code_puppy.messaging import emit_info, emit_success, emit_warning
    from code_puppy.session_storage import (
        build_session_paths,
        load_session,
        save_session,
    )

    group_id = str(uuid.uuid4())

    current_agent = get_current_agent()
    if current_agent.name == agent_name:
        emit_info(
            f"Already using agent: {current_agent.display_name}",
            message_group=group_id,
        )
        return True

    # Capture the terminal's last real saved session before finalize can rotate and
    # record a fresh empty autosave id. This preserves cross-restart resume when
    # the newly started process has no history yet.
    last_session_to_resume = get_last_terminal_session()

    # Force-save the current session before switching (regardless of auto-save settings)
    # This ensures users without auto-save don't lose their conversation context.
    # When a current conversation is actually saved, resume that just-saved context.
    try:
        history = current_agent.get_message_history()
        if history:  # Only save if there's something to save
            session_name = get_current_autosave_session_name()
            # Record the terminal session mapping before saving
            record_terminal_session(session_name)
            # Force-save the session to disk
            save_session(
                history=history,
                session_name=session_name,
                base_dir=Path(AUTOSAVE_DIR),
                timestamp=datetime.datetime.now().isoformat(),
                token_estimator=current_agent.estimate_tokens_for_message,
                auto_saved=True,
            )
            last_session_to_resume = session_name
    except Exception as e:
        emit_warning(
            f"Failed to save session before switching: {e}. "
            "Your context may not be recoverable.",
            message_group=group_id,
        )

    # Finalize current session, switch agent
    new_session_id = finalize_autosave_session()
    if not set_current_agent(agent_name):
        emit_warning(
            "Agent switch failed after autosave rotation. Your context was preserved.",
            message_group=group_id,
        )
        return True

    new_agent = get_current_agent()
    new_agent.reload_code_generation_agent()

    # Auto-resume the session captured before finalize rotated/recorded a new id.
    if last_session_to_resume:
        try:
            autosave_dir = Path(AUTOSAVE_DIR).resolve()
            session_pickle = build_session_paths(
                autosave_dir, last_session_to_resume
            ).pickle_path.resolve()
            if autosave_dir not in session_pickle.parents:
                raise FileNotFoundError(session_pickle)
            history = load_session(last_session_to_resume, autosave_dir)
            new_agent.set_message_history(history)
            set_current_autosave_from_session_name(last_session_to_resume)
            record_terminal_session(last_session_to_resume)
            total_tokens = sum(
                new_agent.estimate_tokens_for_message(m) for m in history
            )
            emit_success(
                Text.from_markup(
                    f"Switched to [bold]{new_agent.display_name}[/bold] "
                    f"and resumed last session "
                    f"([dim]{len(history)} messages, {total_tokens} tokens[/dim])"
                ),
                message_group=group_id,
            )
            emit_info(f"{new_agent.description}", message_group=group_id)
            emit_info(
                Text.from_markup(
                    f"[dim]Auto-save session: {last_session_to_resume}[/dim]"
                ),
                message_group=group_id,
            )
            # Show resumed history summary
            try:
                from code_puppy.command_line.autosave_menu import (
                    display_resumed_history,
                )

                display_resumed_history(history)
            except Exception:
                pass
        except Exception:
            # Session file gone or any other load error — clean switch, don't crash
            emit_success(
                f"Switched to agent: {new_agent.display_name}",
                message_group=group_id,
            )
            emit_info(f"{new_agent.description}", message_group=group_id)
    else:
        # No previous session for this terminal — fresh start
        emit_success(
            f"Switched to agent: {new_agent.display_name}",
            message_group=group_id,
        )
        emit_info(f"{new_agent.description}", message_group=group_id)
        emit_info(
            Text.from_markup(
                f"[dim]Auto-save session rotated to: {new_session_id}[/dim]"
            ),
            message_group=group_id,
        )

    return True


def _handle_switch_agent(command: str, name: str) -> object:
    """Handle /switch-agent and /sa commands."""
    if name not in ("switch-agent", "sa"):
        return None  # Not our command

    from code_puppy.agents import get_available_agents
    from code_puppy.command_line.agent_menu import interactive_agent_picker

    tokens = command.split()

    # No arg OR unrecognized agent name → interactive picker (same as /agent)
    if len(tokens) == 1:
        agent_name = None
    else:
        candidate = tokens[1].lower()
        available = get_available_agents()
        agent_name = candidate if candidate in available else None

    if agent_name is None:
        # Show interactive picker
        import asyncio
        import concurrent.futures

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(interactive_agent_picker())
                )
                agent_name = future.result(timeout=300)
        except Exception:
            agent_name = None

        # Drain any deferred pin-reloads queued from inside the picker.
        # These MUST run here on the main loop --- doing them inside the
        # picker's worker thread deadlocks MCP autostart on loop shutdown.
        try:
            from code_puppy.command_line.agent_menu import (
                apply_pending_pin_reload,
                consume_pending_pin_reloads,
            )

            for pin_agent, pin_model in consume_pending_pin_reloads():
                apply_pending_pin_reload(pin_agent, pin_model)
        except Exception:
            pass

        if not agent_name:
            from code_puppy.messaging import emit_warning

            emit_warning("Agent selection cancelled")
            return True

    return _do_switch_and_resume(agent_name)


def _handle_help() -> list:
    return [
        (
            "switch-agent",
            "Switch agent + auto-resume last terminal session (alias: /sa)",
        ),
    ]


def _cleanup_orphaned_tty_sessions() -> None:
    """Clean up orphaned TTY session files on startup.

    Removes session files for:
    1. TTY devices that no longer exist (terminal closed)
    2. Files older than 7 days (stale sessions)

    Never crashes — all errors are silently caught.
    """
    from code_puppy.config import CACHE_DIR, get_terminal_tty

    try:
        # Skip cleanup if no TTY available
        current_tty = get_terminal_tty()
        if not current_tty:
            return

        # Get the tty_sessions directory
        tty_sessions_dir = Path(CACHE_DIR) / "tty_sessions"
        if not tty_sessions_dir.exists():
            return

        # Build current terminal's filename to skip it
        current_tty_key = current_tty.replace("/", "_").lstrip("_")
        current_filename = f"{current_tty_key}.txt"

        # Calculate cutoff time (7 days ago)
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=7)

        # Iterate through all .txt files in tty_sessions directory
        for session_file in tty_sessions_dir.glob("*.txt"):
            try:
                # Skip current terminal's file
                if session_file.name == current_filename:
                    continue

                # Reconstruct TTY device path from filename
                # Filename: "dev_ttys057.txt" → tty_key: "dev_ttys057" → TTY: "/dev/ttys057"
                tty_key = session_file.stem  # Remove .txt extension
                tty_path = "/" + tty_key.replace("_", "/")

                # Delete if TTY device no longer exists
                if not os.path.exists(tty_path):
                    session_file.unlink()
                    continue

                # Delete if file is older than 7 days
                file_mtime = datetime.datetime.fromtimestamp(
                    session_file.stat().st_mtime
                )
                if file_mtime < cutoff_time:
                    session_file.unlink()

            except Exception:
                # Skip this file on any error, never crash
                continue

    except Exception:
        # Never crash the app over cleanup
        pass


async def _cleanup_orphaned_tty_sessions_async() -> None:
    """Non-blocking wrapper for TTY session cleanup on startup.

    Fires off the cleanup task in a background thread and immediately returns,
    ensuring zero impact on Mist launch time.
    """
    import asyncio

    # Fire-and-forget: run cleanup in background thread without blocking startup
    asyncio.create_task(asyncio.to_thread(_cleanup_orphaned_tty_sessions))


def _has_user_override() -> bool:
    """Return True if a user-level switch_agent_resume plugin exists.

    Built-in plugins load before user plugins. The callback wrapper below
    returns ``None`` when a user plugin exists so user code can take ownership
    of /switch-agent and /sa without racing the built-in handler.
    """
    user_plugin_file = (
        Path.home()
        / ".mist"
        / "plugins"
        / "switch_agent_resume"
        / "register_callbacks.py"
    )
    return user_plugin_file.exists()


def _handle_switch_agent_callback(command: str, name: str) -> object:
    """Callback wrapper that yields ownership to a user override plugin."""
    if _has_user_override():
        return None
    return _handle_switch_agent(command, name)


register_callback("startup", _cleanup_orphaned_tty_sessions_async)
register_callback("custom_command", _handle_switch_agent_callback)
register_callback("custom_command_help", _handle_help)
