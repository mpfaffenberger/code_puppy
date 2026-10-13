"""Startup/main dispatch: argument parsing, config/renderer setup, and the
-p/-r vs interactive branch selection, plus --quick-resume resolution.

Depends on: cli_runner.py (facade calls main() via asyncio.run in
main_entry()); interactive_runner.py::interactive_mode();
prompt_runner.py::execute_single_prompt();
interactive_support.py::_save_autosave_snapshot().
"""

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console

from code_puppy import __version__, callbacks, get_core_plugins_version
from code_puppy.asyncio_cleanup import install_httpcore2_shutdown_filter
from code_puppy.config import ensure_config_exists, initialize_command_history_file
from code_puppy.http_utils import find_available_port
from code_puppy.i18n import t, use_detected_locale
from code_puppy.interactive_runner import interactive_mode
from code_puppy.interactive_support import _save_autosave_snapshot
from code_puppy.keymap import KeymapError, validate_cancel_agent_key
from code_puppy.platform_utils import startup_banner_text
from code_puppy.prompt_runner import execute_single_prompt
from code_puppy.version_checker import default_version_mismatch_behavior


def apply_quick_resume(args) -> bool:
    """Resolve ``--quick-resume [PATH]`` into ``args.resume`` so the existing
    resume machinery loads it.

    Looks up the most recent autosave for PATH (defaulting to cwd), scoped to
    the nearest git worktree root + branch when available, with a no-git
    fallback. No-op when ``--quick-resume`` was not requested or ``--resume`` is
    already set (explicit ``--resume`` always wins). Returns True when a target
    was resolved.
    """
    existing_resume = getattr(args, "resume", None)
    quick_resume_target = getattr(args, "quick_resume", None)
    if quick_resume_target is None or (
        existing_resume and str(existing_resume).strip()
    ):
        return False

    from code_puppy.config import (
        format_quick_resume_scope,
        get_quick_resume_location,
        resolve_quick_resume_pickle,
    )
    from code_puppy.messaging import emit_info

    target_path = str(quick_resume_target).strip() or "."

    # Diagnostic identifies the lookup scope without leaking full local paths.
    cwd, branch = get_quick_resume_location(target_path)
    emit_info(
        t(
            "cli.resume.quick_searching",
            scope=format_quick_resume_scope(cwd, branch),
        )
    )

    quick_resume_pickle = resolve_quick_resume_pickle(target_path)
    if quick_resume_pickle:
        args.resume = quick_resume_pickle
        return True

    emit_info(t("cli.resume.none_found"))
    return False


def _initialize_locale():
    """Select the UI locale before any startup message is translated."""
    from code_puppy.config import get_value

    use_detected_locale(get_value("locale"))


async def main():
    """Main async entry point for Code Puppy CLI."""
    install_httpcore2_shutdown_filter()
    parser = argparse.ArgumentParser(description="Code Puppy - A code generation agent")
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"{__version__}",
        help="Show version and exit",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        help="Execute a single prompt and exit (no interactive mode)",
    )
    parser.add_argument(
        "--disable-ask-user-question",
        action="store_true",
        help="Disable only the interactive ask_user_question tool",
    )
    parser.add_argument(
        "--usage-file",
        type=Path,
        metavar="PATH",
        help="Write aggregate headless model usage as JSON",
    )
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        help="Specify which agent to use (e.g., --agent code-puppy)",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        help="Specify which model to use (e.g., --model gpt-5)",
    )
    parser.add_argument(
        "--resume",
        "-r",
        type=str,
        metavar="PATH",
        help=(
            "Resume a saved session by name or file path "
            "(.json envelope; legacy .pkl files migrate automatically)"
        ),
    )
    parser.add_argument(
        "--cwd",
        action="store_true",
        help=(
            "With --resume, only list/consider sessions scoped to the current "
            "working directory (opt-in; default shows all sessions unfiltered)"
        ),
    )
    parser.add_argument(
        "--quick-resume",
        "-qr",
        nargs="?",
        const=".",
        default=None,
        metavar="PATH",
        help=(
            "Resume the most recent session for PATH (defaults to the current "
            "directory; scopes to git root + branch when available)"
        ),
    )
    parser.add_argument(
        "--port-base",
        type=str,
        default=None,
        metavar="PORT",
        help=(
            "Starting port for the local HTTP server (searches PORT..PORT+920). "
            "Bump this if 8090 collides with another local dev server. "
            "Falls back to $CODE_PUPPY_PORT_BASE or 'port_base' in puppy.cfg (default 8090). "
            "Invalid values are warned about and ignored -- next source in the "
            "precedence chain is used instead of crashing."
        ),
    )
    parser.add_argument(
        "command", nargs="*", help="Run a single command (deprecated, use -p instead)"
    )

    # Plugins add CLI args via on_register_cli_args (loaded at import time);
    # duplicate option strings raise here = fail fast.
    callbacks.on_register_cli_args(parser)

    args = parser.parse_args()
    _initialize_locale()
    if args.disable_ask_user_question:
        os.environ["CODE_PUPPY_DISABLE_ASK_USER_QUESTION"] = "1"

    # Plugins may act on parsed args and short-circuit startup; first dict
    # with handled=True wins (exits with its exit_code).
    for result in callbacks.on_handle_cli_args(args):
        if isinstance(result, dict) and result.get("handled"):
            return result.get("exit_code", 0)

    from code_puppy.messaging import (
        RichConsoleRenderer,
        SynchronousInteractiveRenderer,
        get_global_queue,
        get_message_bus,
    )

    # Create a shared console for both renderers
    display_console = Console()

    # Legacy renderer for backward compatibility (emits via get_global_queue)
    message_queue = get_global_queue()
    message_renderer = SynchronousInteractiveRenderer(message_queue, display_console)
    message_renderer.start()

    # New MessageBus renderer for structured messages (tools emit here)
    message_bus = get_message_bus()
    bus_renderer = RichConsoleRenderer(message_bus, display_console)
    bus_renderer.start()

    initialize_command_history_file()
    from code_puppy.messaging import emit_error, emit_system_message

    # Show the logo on entering interactive mode (no -p flag; covers
    # both `code-puppy` and `code-puppy -i`).
    if not args.prompt:
        try:
            import pyfiglet

            # Width-aware banner: full CODE PUPPY when it fits, PUP when
            # the terminal is too narrow (phones, tight splits).
            banner_columns = display_console.width
            intro_lines = pyfiglet.figlet_format(
                startup_banner_text(banner_columns), font="ansi_shadow"
            ).split("\n")

            # Simple blue to green gradient (top to bottom)
            gradient_colors = ["bright_blue", "bright_cyan", "bright_green"]
            display_console.print("\n")

            # Left-justified on purpose -- the full-screen splash handles
            # the centered spectacle; this banner tops the scrollback.
            lines = []
            for line_num, line in enumerate(intro_lines):
                if line.strip():
                    # Top=blue, middle=cyan, bottom=green by line position
                    color_idx = min(line_num // 2, len(gradient_colors) - 1)
                    color = gradient_colors[color_idx]
                    lines.append(f"[{color}]{line}[/{color}]")
                else:
                    lines.append("")
            # Print directly to console to avoid the 'dim' style from emit_system_message
            display_console.print("\n".join(lines))
        except ImportError:
            emit_system_message(t("cli.loading"))

        # Truecolor warning moved to interactive_mode() so it prints last — max visibility.

    from code_puppy.config import PORT_PROBE_WIDTH, resolve_port_base

    port_base = resolve_port_base(cli_value=args.port_base)
    port_end = port_base + PORT_PROBE_WIDTH
    available_port = find_available_port(start_port=port_base, end_port=port_end)
    if available_port is None:
        emit_error(t("cli.error.no_ports", port_base=port_base, port_end=port_end))
        return

    # Set model early (before ensure_config_exists) so config is set up correctly.
    early_model = None
    if args.model:
        early_model = args.model.strip()
        from code_puppy.config import set_model_name

        set_model_name(early_model)

    ensure_config_exists()

    # Opt-in Logfire observability — a no-op unless enable_logfire (or
    # CODE_PUPPY_ENABLE_LOGFIRE) is set. Must run before agents spin up so
    # pydantic-ai instrumentation catches every run.
    from code_puppy.observability import configure_logfire

    configure_logfire()

    # Validate cancel_agent_key configuration early
    try:
        validate_cancel_agent_key()
    except KeymapError as e:
        from code_puppy.messaging import emit_error

        emit_error(str(e))
        sys.exit(1)

    # Windows: raw Ctrl+C all session — no console-wide CTRL_C_EVENT (kills
    # wrapper launchers); Ctrl+C arrives as \x03, handled like any keystroke.
    from code_puppy.terminal_utils import (
        disable_windows_ctrl_c,
        set_keep_ctrl_c_disabled,
    )

    if disable_windows_ctrl_c():
        # Keep the clamp sticky across terminal resets / console mode restores.
        set_keep_ctrl_c_disabled(True)

    # Load API keys from puppy.cfg into environment variables
    from code_puppy.config import load_api_keys_to_environment

    load_api_keys_to_environment()

    # Handle model validation from command line (validation happens here, setting was earlier)
    if args.model:
        from code_puppy.config import _validate_model_exists

        model_name = args.model.strip()
        try:
            # Validate that the model exists in models.json
            if not _validate_model_exists(model_name):
                from code_puppy.model_factory import ModelFactory

                models_config = ModelFactory.load_config()
                available_models = list(models_config.keys()) if models_config else []

                emit_error(t("cli.model.not_found", model=model_name))
                emit_system_message(
                    t("cli.model.available", models=", ".join(available_models))
                )
                sys.exit(1)

            # Model is valid, show confirmation (already set earlier)
            emit_system_message(t("cli.model.using", model=model_name))
        except Exception as e:
            emit_error(t("cli.model.validate_error", error=str(e)))
            sys.exit(1)

    # Handle agent selection from command line
    if args.agent:
        from code_puppy.agents.agent_manager import (
            get_available_agents,
            set_current_agent,
        )

        agent_name = args.agent.lower()
        try:
            # First check if the agent exists by getting available agents
            available_agents = get_available_agents()
            if agent_name not in available_agents:
                emit_error(t("cli.agent.not_found", agent=agent_name))
                emit_system_message(
                    t("cli.agent.available", agents=", ".join(available_agents.keys()))
                )
                sys.exit(1)

            # Agent exists, set it
            set_current_agent(agent_name)
            emit_system_message(t("cli.agent.using", agent=agent_name))
        except Exception as e:
            emit_error(t("cli.agent.set_error", error=str(e)))
            sys.exit(1)

    current_version = __version__

    no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if no_version_update:
        version_msg = t("version.current", version=current_version)
        update_disabled_msg = t("cli.version.update_disabled")
        emit_system_message(version_msg)
        emit_system_message(update_disabled_msg)
    else:
        if len(callbacks.get_callbacks("version_check")):
            await callbacks.on_version_check(current_version)
        else:
            default_version_mismatch_behavior(current_version)

    core_plugins_version = get_core_plugins_version()
    if core_plugins_version is None:
        core_plugins_message = t("version.core_plugins_unknown")
    else:
        core_plugins_message = t("version.core_plugins", version=core_plugins_version)
    emit_system_message(core_plugins_message)

    # One-shot sweep of legacy ~/.code_puppy/contexts/ into autosaves/ (idempotent
    # via sentinel). Must run before plugin startup callbacks read AUTOSAVE_DIR and
    # before the -r resume block resolves.
    try:
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        sweep_contexts_to_autosaves()
    except Exception:
        # Sweep failure must never block startup -- it logs internally.
        pass

    # One-time format migration: legacy pickle sessions -> versioned JSON
    # envelopes (idempotent via marker file). Runs after the location sweep so
    # freshly-moved contexts/ files are migrated in the same boot.
    try:
        from code_puppy.session_format_migration import sweep_legacy_pickle_sessions

        sweep_legacy_pickle_sessions()
    except Exception:
        # Never block startup; failures are logged/warned internally.
        pass

    await callbacks.on_startup()

    # Resolve --quick-resume into --resume for the canonical (git-root + branch) scope.
    apply_quick_resume(args)

    # Resolved (normalised) session name under -r/--resume so save-back writes the
    # same file the resolver opened — not the raw ``foo.pkl`` / absolute-path input.
    resolved_resume_session: str | None = None

    if args.resume:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.config import AUTOSAVE_DIR, pin_current_session_name
        from code_puppy.messaging import emit_error, emit_info, emit_success
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )
        from code_puppy.session_storage import (
            compute_scope_key,
            list_sessions,
            load_session,
        )

        resume_target = args.resume
        sessions_dir = Path(AUTOSAVE_DIR)
        # Opt-in via --cwd: only offer sessions scoped to the current directory.
        # Default (flag absent) keeps the unfiltered listing byte-for-byte.
        resume_scope_key = compute_scope_key(Path.cwd()) if args.cwd else None

        # Both headless and interactive accept ``-r missing-name`` (empty session);
        # typos still surface via the visible ``Created new session: NAME`` line.
        try:
            session_name, session_dir, lazy_created = resolve_or_create_resume_target(
                resume_target,
                sessions_dir=sessions_dir,
                allow_lazy_create=True,
            )
        except ResumeTargetError as resolve_exc:
            emit_error(resolve_exc.message)
            if resolve_exc.hint:
                emit_info(resolve_exc.hint)
            available = list_sessions(sessions_dir, scope_key=resume_scope_key)
            if available:
                emit_info(
                    t(
                        "cli.resume.available_sessions",
                        sessions=", ".join(available[:10]),
                    )
                )
            sys.exit(1)

        # Announce lazy-create so scripts/users can tell it from a normal resume.
        if lazy_created:
            emit_info(t("cli.resume.created", session=session_name))

        try:
            history = load_session(session_name, session_dir)
            agent = get_current_agent()
            agent.set_message_history(history)
            total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

            # Pin the singleton so periodic autosave AND headless save-back update
            # this named file (replaces rotate_autosave_id()). Note: absolute-path
            # resumes pin the stem — writes land in AUTOSAVE_DIR for cross-mode consistency.
            pin_current_session_name(session_name)

            # Record the resolved name for the headless save-back path below.
            resolved_resume_session = session_name

            if not lazy_created:
                emit_success(
                    t(
                        "cli.resume.resumed",
                        messages=len(history),
                        tokens=total_tokens,
                        session=session_name,
                    )
                )
                # Re-render recent history on interactive resume (matching /load and
                # the autosave picker): -r loaded history but left a blank screen.
                # Skipped headless/non-TTY; honors resume_message_count; best-effort.
                if not args.prompt and sys.stdout.isatty():
                    try:
                        from code_puppy.command_line.autosave_menu import (
                            display_resumed_history,
                        )

                        display_resumed_history(history)
                    except Exception:
                        pass
        except Exception as e:
            emit_error(t("cli.resume.failed", target=resume_target, error=e))
            sys.exit(1)

    global shutdown_flag
    shutdown_flag = False
    try:
        initial_command = None
        prompt_only_mode = False

        if args.prompt:
            initial_command = args.prompt
            prompt_only_mode = True
            # Headless runs have nobody at the keyboard to answer check-ins,
            # so agency is always EXTREME regardless of config.
            from code_puppy.config import set_headless_mode

            set_headless_mode(True)
        elif args.command:
            initial_command = " ".join(args.command)
            prompt_only_mode = False

        if prompt_only_mode:
            await execute_single_prompt(
                initial_command,
                message_renderer,
                session_name=resolved_resume_session,
                usage_file=args.usage_file,
            )
        else:
            # Default to interactive mode (no args = same as -i)
            try:
                await interactive_mode(
                    message_renderer, initial_command=initial_command
                )
            finally:
                # Belt-and-braces: Ctrl-D, /exit, or a top-level interrupt must
                # not lose history that a cancelled turn skipped saving.
                # Headless `-p` runs persist themselves in execute_single_prompt's
                # own finally, so this must not run for that branch too.
                _save_autosave_snapshot()
    finally:
        # Tear down the persistent prompt first (restores scroll region, cursor,
        # key listener) so the renderer stops on a sane screen. Idempotent.
        try:
            from code_puppy.messaging.run_ui import stop_persistent_ui

            stop_persistent_ui()
        except Exception:
            pass
        if message_renderer:
            message_renderer.stop()
        if bus_renderer:
            bus_renderer.stop()
        # session_end fires before shutdown so plugins react while bus state is coherent.
        try:
            await callbacks.on_session_end()
        except Exception:
            pass
        await callbacks.on_shutdown()
