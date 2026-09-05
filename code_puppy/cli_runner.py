"""CLI runner for Code Puppy.

Contains the main application logic, interactive mode, and entry point.
"""

# Apply pydantic-ai patches BEFORE any pydantic-ai imports
from code_puppy.pydantic_patches import apply_all_patches

apply_all_patches()

import argparse
import asyncio
import time
import json
import os
import signal
import sys
import traceback
from pathlib import Path

from rich.console import Console

from code_puppy import __version__, callbacks, get_core_plugins_version, plugins
from code_puppy.agents import get_current_agent
from code_puppy.asyncio_cleanup import install_httpcore2_shutdown_filter
from code_puppy.i18n import t, use_detected_locale
from code_puppy.command_line.attachments import (
    parse_prompt_attachments,
    resolve_user_prompt,
)
from code_puppy.config import (
    AUTOSAVE_DIR,
    COMMAND_HISTORY_FILE,
    ensure_config_exists,
    finalize_autosave_session,
    get_current_session_name,
    initialize_command_history_file,
    record_terminal_session,
    save_command_to_history,
)
from code_puppy.http_utils import find_available_port
from code_puppy.keymap import (
    KeymapError,
    validate_cancel_agent_key,
)
from code_puppy.messaging import emit_info
from code_puppy.platform_utils import startup_banner_text
from code_puppy.terminal_utils import (
    print_truecolor_warning,
    reset_unix_terminal,
    reset_windows_terminal_ansi,
    reset_windows_terminal_full,
)
from code_puppy.version_checker import default_version_mismatch_behavior

plugins.load_plugin_callbacks()

_HEADLESS_AUTONOMY_PROMPT = """\
This is an unattended, non-interactive run. Never ask for confirmation, approval,
clarification, or manual verification, including through tools or MCP servers. Use
reasonable defaults, proceed autonomously, and validate with the tools available to
you. State any assumptions or optional manual checks only in the final response.\
"""


def _render_turn_exception(exc: Exception) -> None:
    """Render a turn-level exception without ever taking down the REPL.

    Transient model/connection failures (a dropped socket, a VPN/WiFi blip, a
    provider rate limit) are environment hiccups, not Code Puppy bugs. They get
    a friendly one-liner instead of a 60-line traceback, because a wall of
    stack frames makes a recoverable blip look fatal. Genuine errors still get
    the full traceback so they stay debuggable.

    The transient/not-transient decision reuses the same classifier that drives
    streaming auto-retries, so the two stay in lock-step by construction.

    Either way -- friendly one-liner OR full traceback -- the exception is
    persisted to ``~/.code_puppy/logs/errors.log`` so SRE / support can still
    see what actually happened upstream. The friendly UI is for the human,
    not for the audit trail.
    """
    from code_puppy.agents.base_agent import should_retry_streaming_exception
    from code_puppy.error_logging import log_error

    if should_retry_streaming_exception(exc):
        log_error(
            exc,
            context=(
                "cli_runner._render_turn_exception: transient model/connection "
                "error reached the REPL after auto-retry exhaustion (or from a "
                "non-streaming code path). User saw the friendly one-liner."
            ),
        )
        from code_puppy.messaging import emit_error

        emit_error(t("cli.error.model_transient", error_type=type(exc).__name__))
        return

    log_error(
        exc,
        context=(
            "cli_runner._render_turn_exception: non-transient turn exception "
            "reached the REPL. User saw the full traceback in the console."
        ),
    )
    from code_puppy.messaging.queue_console import get_queue_console

    get_queue_console().print_exception()


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

        # Powered-by tagline under the big banner (prints even without pyfiglet).
        display_console.print(
            f"[dim]{t('cli.banner.powered_by')}[/dim] "
            "[link=https://github.com/pydantic/pydantic-ai-harness]"
            "[cyan]https://github.com/pydantic/pydantic-ai-harness[/cyan][/link]"
        )
        display_console.print(
            f"[dim]{t('cli.banner.observability_pitch')}[/dim] "
            "[link=https://pydantic.dev/logfire]"
            "[cyan]https://pydantic.dev/logfire[/cyan][/link]\n"
        )

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
            await interactive_mode(message_renderer, initial_command=initial_command)
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


def _use_persistent_prompt() -> bool:
    """Should the REPL use the persistent bottom-bar prompt (Phase A)?

    False (-> classic plain-input path) when:
      * rollback flag: env CODE_PUPPY_CLASSIC_PROMPT=1 or config
        ``classic_prompt`` truthy — protects the eyeball-testing period;
      * CODE_PUPPY_NO_TUI=1 (tests / pexpect harnesses);
      * stdin/stdout isn't a real TTY (pipes, CI) — automatic degrade,
        not just the env flag;
      * the console can't be confirmed VT-capable (legacy Windows
        conhost) — the bar writes raw escapes to ``__stdout__``, so
        without VT it would render as escape soup at spinner speed.
    """
    truthy = {"1", "true", "yes", "on"}
    if os.environ.get("CODE_PUPPY_CLASSIC_PROMPT", "").strip().lower() in truthy:
        return False
    if os.environ.get("CODE_PUPPY_NO_TUI", "").strip() == "1":
        return False
    try:
        from code_puppy.config import get_value

        if str(get_value("classic_prompt") or "").strip().lower() in truthy:
            return False
    except Exception:
        pass
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except Exception:
        return False
    # Raw-VT gate: verify Windows VT processing up front (no-op on POSIX);
    # unconfirmed VT → classic prompt (bar never starts, no spinner tickers).
    try:
        from code_puppy.terminal_utils import ensure_windows_vt_processing

        if not ensure_windows_vt_processing():
            return False
    except Exception:
        pass  # the gate itself must never kill the persistent UI
    return True


def _persistent_prompt_parts() -> tuple:
    """``(plain_prefix, per_char_sgrs)`` for the bottom-bar editor.

    Flattens ``get_prompt_with_active_model()``'s FormattedText (read-only
    use) so idle and running prompts look identical — keeping the style
    classes as an out-of-band per-char SGR list (the bar sanitizes any
    in-band escapes, so colors can't ride inside the string itself).
    """
    try:
        from code_puppy.command_line.completers import (
            PROMPT_STYLES,
            get_prompt_with_active_model,
        )
        from code_puppy.messaging.prompt_prefix_style import (
            flatten_prompt_fragments,
        )

        formatted = get_prompt_with_active_model()
        return flatten_prompt_fragments(formatted, PROMPT_STYLES)
    except Exception:
        return ">>> ", []


def _prompt_echo_text(task: str):
    """Build a transcript echo using the active prompt foreground."""
    from rich.text import Text

    from code_puppy.callbacks import on_prompt_text_color

    prompt_color = on_prompt_text_color()
    style = f"bold {prompt_color}" if prompt_color else "bold"
    return Text(f"\n> {task}", style=style)


def _interactive_sigint_guard(_sig, _frame):
    """Baseline SIGINT handler for the interactive REPL.

    Ctrl+C in Code Puppy is a *cancel* gesture, never a *quit* gesture
    (Ctrl+D quits). During an agent run or a shell command the runtime
    installs its own SIGINT handler that turns Ctrl+C into a task cancel /
    shell kill, saving and later restoring whatever handler was in place.

    Between those windows -- and, critically, during the brief unwind after a
    run is cancelled but before the next handler is installed -- the handler
    would otherwise be Python's default, which raises ``KeyboardInterrupt``.
    A second fast Ctrl+C landing in that gap bubbles all the way up to
    ``main_entry`` and exits the whole process. That is the
    ``Ctrl+C Ctrl+C too fast`` crash.

    Installing this no-op-ish guard for the lifetime of the REPL means the
    saved/restored ``original`` handler is always benign: a stray Ctrl+C in
    any gap is swallowed instead of killing the process. The per-run and
    per-shell handlers still own cancellation while they're active.
    """
    # No cancel-owner is active, so swallow the signal — a fast repeat tap can't
    # escape to main_entry and exit. Windows: any SIGINT reaching Python means
    # console mode regressed; re-clamp (it kills wrapper launchers otherwise).
    try:
        from code_puppy.terminal_utils import ensure_ctrl_c_disabled

        ensure_ctrl_c_disabled()
    except Exception:
        pass
    # Persistent prompt: Ctrl+C clears the buffer (readline feel; Ctrl+D
    # quits), and a second idle Ctrl+C within DOUBLE_CTRL_C_WINDOW_S quits
    # like Ctrl+D. Only out-of-band SIGINTs land here — raw \x03 goes to the
    # key listener, which also owns mid-run cancel (remapped key ->
    # buffer-first clearing).
    try:
        from code_puppy.messaging.run_ui import (
            absorb_ctrl_c_if_composing,
            is_run_active,
            note_idle_ctrl_c,
        )

        if is_run_active():
            absorb_ctrl_c_if_composing()
        else:
            note_idle_ctrl_c()
    except Exception:
        pass
    return


#: How long the quit paths (double Ctrl+C / Ctrl+D / exit) wait for a
#: lingering agent task to finish cancelling before abandoning it. A stuck
#: unwind must never freeze the exit — process teardown reaps the zombie.
_QUIT_CANCEL_TIMEOUT_S = 5.0


async def _shutdown_agent_task(agent_task) -> None:
    """Cancel a lingering agent task on quit, bounded by a timeout.

    ``asyncio.wait`` (not ``wait_for``) on purpose: ``wait_for``'s timeout
    path awaits the inner cancellation, which is exactly the await that can
    wedge. ``wait`` just stops waiting.
    """
    from code_puppy.messaging import emit_warning

    if agent_task is None or agent_task.done():
        return
    emit_info(t("cli.agent.cancelling"))
    agent_task.cancel()
    done, _ = await asyncio.wait({agent_task}, timeout=_QUIT_CANCEL_TIMEOUT_S)
    if agent_task not in done:
        emit_warning(t("cli.agent.quit_cancel_timeout", seconds=_QUIT_CANCEL_TIMEOUT_S))
        return
    try:
        agent_task.result()
    except BaseException:
        pass  # Expected when cancelling — nothing to do with it on the way out.


async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    """Run the agent in interactive mode."""
    from code_puppy.command_line.command_handler import handle_command

    display_console = message_renderer.console
    from rich.text import Text

    from code_puppy.messaging import emit_info, emit_system_message

    # Pass a Text object (not a plain str): the SYSTEM renderer escapes Rich
    # markup in plain strings before printing (see renderers.py), so inline
    # "[bold]...[/bold]" in the i18n string would show up as literal
    # brackets. A Text object bypasses that string branch entirely and
    # renders as one line, actually bold.
    emit_system_message(Text(t("cli.help.press_tab"), style="bold"))
    # Tell the user how relentless the puppy is configured to be.
    from code_puppy.config import get_agency_level

    emit_info(t("cli.agency.status", level=get_agency_level().upper()))
    # Print truecolor warning LAST so it's the most visible thing on startup
    # Big ugly red box should be impossible to miss!
    print_truecolor_warning(display_console)

    # Shell pass-through for initial_command: !<cmd> bypasses the agent
    if initial_command:
        from code_puppy.command_line.shell_passthrough import (
            execute_shell_passthrough,
            is_shell_passthrough,
        )

        if is_shell_passthrough(initial_command):
            execute_shell_passthrough(initial_command)
            initial_command = None

    # Initialize the runtime agent manager
    if initial_command:
        from code_puppy.agents import get_current_agent
        from code_puppy.messaging import emit_info, emit_success, emit_system_message

        agent = get_current_agent()
        emit_info(t("cli.initial_command.processing", command=initial_command))

        try:
            # Skip the run UI if a tool is already waiting for user input
            # (the input prompt owns the terminal in that case).
            try:
                from code_puppy.tools.command_runner import is_awaiting_user_input

                awaiting_input = is_awaiting_user_input()
            except ImportError:
                awaiting_input = False

            response, agent_task = await run_prompt_with_attachments(
                agent,
                initial_command,
                display_console=display_console,
                use_run_ui=not awaiting_input,
            )
            if response is not None:
                agent_response = response.output

                # Update agent history with the complete conversation (incl. final response).
                if hasattr(response, "all_messages"):
                    agent.set_message_history(list(response.all_messages()))

                # Emit structured message for proper markdown rendering
                from code_puppy.messaging import get_message_bus
                from code_puppy.messaging.messages import AgentResponseMessage

                response_msg = AgentResponseMessage(
                    content=agent_response,
                    is_markdown=True,
                )
                get_message_bus().emit(response_msg)

                emit_success(t("cli.initial_command.continuing"))
                emit_system_message(t("cli.initial_command.preserved"))

        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(t("cli.initial_command.error", error=str(e)))

    # Autosave loading is now manual - use /autosave_load command

    record_terminal_session(get_current_session_name(), overwrite=False)
    # Track the current agent task for cancellation on quit
    current_agent_task = None
    # Classic prompt: timestamp of the last idle Ctrl+C, for the
    # double-tap-to-quit gesture (persistent mode tracks its own in run_ui).
    last_idle_ctrl_c = 0.0

    # Baseline SIGINT guard for the REPL's whole life: Ctrl+C = cancel (Ctrl+D
    # quits); without it, a fast double-tap in the handler gap raises
    # KeyboardInterrupt and exits the process. Deliberately never restored.
    try:
        signal.signal(signal.SIGINT, _interactive_sigint_guard)
    except (ValueError, OSError):
        pass

    # Field diagnostics: `kill -USR2 <pid>` dumps thread + asyncio-task
    # stacks to ~/.code_puppy/stackdumps/ — the conviction kit for wedged
    # cancellations (a frozen REPL can't be introspected any other way).
    try:
        from code_puppy.diagnostics import install_stack_dump_handler

        install_stack_dump_handler(asyncio.get_running_loop())
    except Exception:
        pass  # diagnostics must never block the REPL

    # ------------------------------------------------------------------
    # Persistent-prompt mode: the bottom-bar editor is THE prompt (idle AND
    # running) — pinned input row, output scrolls above. Classic path behind
    # rollback flag / non-TTY auto-degrade (see _use_persistent_prompt).
    # ------------------------------------------------------------------
    persistent_prompt = False
    if _use_persistent_prompt():
        try:
            from code_puppy.messaging.run_ui import start_persistent_ui

            _prefix, _prefix_sgrs = _persistent_prompt_parts()
            persistent_prompt = start_persistent_ui(
                prompt_prefix=_prefix, prefix_sgrs=_prefix_sgrs
            )
        except Exception:
            persistent_prompt = False  # degrade to classic on any failure

    while True:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent()
        user_prompt = current_agent.get_user_prompt() or t("cli.prompt.enter_task")

        if not persistent_prompt:
            # Persistent path drops the per-iteration banner — the pinned
            # prompt row + transcript echo replace it.
            emit_info(f"{user_prompt}\n")

        try:
            if persistent_prompt:
                from code_puppy.messaging.run_ui import (
                    set_idle_prompt_prefix,
                    wait_for_idle_submission,
                )

                # Model/agent may have changed since last turn.
                prompt_prefix, prompt_prefix_sgrs = _persistent_prompt_parts()
                set_idle_prompt_prefix(prompt_prefix, prompt_prefix_sgrs)
                # Idle + queued prompts (/queue or cancelled-run leftovers): consume
                # the oldest now; mid-run steers drain in _runtime's loop instead.
                from code_puppy.messaging.pause_controller import (
                    get_pause_controller as _get_pc,
                )

                queued_task = _get_pc().pop_next_steer_queued()
                if queued_task is not None:
                    task = queued_task
                    emit_info(_prompt_echo_text(task))
                    emit_info(t("cli.queue.running"))
                else:
                    # Raises EOFError on Ctrl+D-with-empty-buffer, which the
                    # existing quit branch below handles.
                    task = await wait_for_idle_submission()
                    # Echo the user's text (bold, '> ') into scrollback — the editor
                    # clears its row on submit, and repainting the full prompt chrome
                    # doubled every line's noise. Text() so bracket-y input renders as-is.
                    emit_info(_prompt_echo_text(task))
            else:
                # Classic (non-TTY / rollback) prompt: plain blocking input.
                # No completion here -- the persistent bottom-bar editor is
                # the featured path; this branch exists for pipes, CI, and
                # the CODE_PUPPY_CLASSIC_PROMPT escape hatch.
                reset_windows_terminal_ansi()
                task = input(">>> ")
                from code_puppy.messaging.editor_history import HistoryStore

                HistoryStore(COMMAND_HISTORY_FILE).append(task)

        except (KeyboardInterrupt, asyncio.CancelledError) as cancel_exc:
            # Ctrl+C: cancel input and continue. Reset terminal state on Windows
            # so it doesn't become unresponsive.
            reset_windows_terminal_full()
            from code_puppy.callbacks import on_interactive_turn_cancel
            from code_puppy.messaging import emit_success, emit_warning
            from code_puppy.messaging.run_ui import DOUBLE_CTRL_C_WINDOW_S

            # Double Ctrl+C at the idle prompt quits like Ctrl+D.
            # CancelledError never counts.
            was_plain_ctrl_c = isinstance(cancel_exc, KeyboardInterrupt)
            now = time.monotonic()
            if was_plain_ctrl_c and now - last_idle_ctrl_c <= DOUBLE_CTRL_C_WINDOW_S:
                emit_success("\n" + t("cli.goodbye_ctrld"))
                await _shutdown_agent_task(current_agent_task)
                break
            last_idle_ctrl_c = now if was_plain_ctrl_c else 0.0

            await on_interactive_turn_cancel("", reason="Ctrl+C")
            emit_warning("\n" + t("cli.input.cancelled"))
            continue
        except EOFError:
            # Handle Ctrl+D - exit the application
            from code_puppy.messaging import emit_success

            emit_success("\n" + t("cli.goodbye_ctrld"))

            # Cancel any running agent task for clean shutdown (bounded — a
            # stuck unwind must not freeze Ctrl+D).
            await _shutdown_agent_task(current_agent_task)

            break

        # Shell pass-through: !<command> executes directly, bypassing the agent
        from code_puppy.command_line.shell_passthrough import (
            execute_shell_passthrough,
            is_shell_passthrough,
        )

        if is_shell_passthrough(task):
            # The shell owns the terminal — release the bar + key listener
            # (no-op in classic mode where neither is active at idle).
            from code_puppy.messaging.run_ui import suspended_run_ui

            with suspended_run_ui():
                execute_shell_passthrough(task)
            continue

        # Check for exit commands (plain text or command form)
        if task.strip().lower() in ["exit", "quit"] or task.strip().lower() in [
            "/exit",
            "/quit",
        ]:
            from code_puppy.messaging import emit_success

            emit_success(t("cli.goodbye"))

            # Cancel any running agent task for clean shutdown (bounded — a
            # stuck unwind must not freeze `exit`).
            await _shutdown_agent_task(current_agent_task)

            # The renderer is stopped in the finally block of main().
            break

        # Backward-compat: bare `clear` → `/clear` so session_commands' handler
        # stays the single source of truth.
        if task.strip().lower() == "clear":
            task = "/clear"

        # Parse attachments first so leading paths aren't misread as commands
        processed_for_commands = parse_prompt_attachments(task)
        cleaned_for_commands = (processed_for_commands.prompt or "").strip()

        # Handle / commands based on cleaned prompt (after stripping attachments)
        if cleaned_for_commands.startswith("/"):
            try:
                # Commands may open menus; release the bar for the duration
                # (no-op in classic mode).
                from code_puppy.messaging.run_ui import suspended_run_ui

                with suspended_run_ui():
                    command_result = handle_command(cleaned_for_commands)
            except Exception as e:
                from code_puppy.messaging import emit_error

                emit_error(t("cli.command.error", error=e))
                # Continue interactive loop instead of exiting
                continue
            if command_result is True:
                continue
            elif isinstance(command_result, str):
                if command_result == "__AUTOSAVE_LOAD__":
                    # Handle async autosave loading
                    try:
                        # Check if we're in a real interactive terminal
                        # (not pexpect/tests) - interactive picker requires proper TTY
                        use_interactive_picker = (
                            sys.stdin.isatty() and sys.stdout.isatty()
                        )

                        # Allow environment variable override for tests
                        if os.getenv("CODE_PUPPY_NO_TUI") == "1":
                            use_interactive_picker = False

                        if use_interactive_picker:
                            # Use interactive picker for terminal sessions
                            from code_puppy.agents.agent_manager import (
                                get_current_agent,
                            )
                            from code_puppy.command_line.autosave_menu import (
                                interactive_autosave_picker,
                            )
                            from code_puppy.config import (
                                pin_current_session_name,
                            )
                            from code_puppy.messaging import (
                                emit_error,
                                emit_success,
                                emit_warning,
                            )
                            from code_puppy.session_storage import load_session

                            from code_puppy.messaging.run_ui import (
                                suspended_run_ui,
                            )

                            with suspended_run_ui():
                                chosen_session = await interactive_autosave_picker()

                            if not chosen_session:
                                emit_warning(t("cli.autosave.load_cancelled"))
                                continue

                            # Load the session
                            base_dir = Path(AUTOSAVE_DIR)
                            history = load_session(chosen_session, base_dir)

                            agent = get_current_agent()
                            agent.set_message_history(history)

                            # Set current autosave session
                            pin_current_session_name(chosen_session)

                            total_tokens = sum(
                                agent.estimate_tokens_for_message(msg)
                                for msg in history
                            )
                            session_path = base_dir / f"{chosen_session}.json"

                            emit_success(
                                t(
                                    "cli.autosave.loaded",
                                    messages=len(history),
                                    tokens=total_tokens,
                                )
                            )
                            emit_info(t("cli.autosave.loaded_path", path=session_path))

                            # Display recent message history for context
                            from code_puppy.command_line.autosave_menu import (
                                display_resumed_history,
                            )

                            display_resumed_history(history)
                        else:
                            # No TTY, no picker: the old text-prompt fallback
                            # was an interactive prompt in a non-interactive
                            # environment. Point at the explicit flag instead.
                            from code_puppy.messaging import emit_warning

                            emit_warning(t("cli.autosave.tui_required"))

                    except Exception as e:
                        from code_puppy.messaging import emit_error

                        emit_error(t("cli.autosave.load_failed", error=e))
                    continue
                else:
                    # Command returned a prompt to execute
                    task = command_result
            elif command_result is False:
                # Command not recognized, continue with normal processing
                pass

        if task.strip():
            # Write to the secret file for permanent history with timestamp
            save_command_to_history(task)

            turn_result = None
            turn_success = False
            turn_error = None

            try:
                # No need to get agent directly - use manager's run methods

                # Use our custom helper to enable attachment handling with
                # the bottom-bar run UI active for the duration.
                result, current_agent_task = await run_prompt_with_attachments(
                    current_agent,
                    task,
                    display_console=message_renderer.console,
                )
                # Check if the task was cancelled (but don't show message if we just killed processes)
                if result is None:
                    # Windows-specific: Reset terminal state after cancellation
                    reset_windows_terminal_ansi()
                    # Windows: re-clamp raw-Ctrl+C mode after terminal reset
                    try:
                        from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                        ensure_ctrl_c_disabled()
                    except ImportError:
                        pass
                    from code_puppy.callbacks import on_interactive_turn_cancel

                    await on_interactive_turn_cancel(task, reason="cancellation")
                    continue
                # Get the structured response
                agent_response = result.output

                # Emit structured message for proper markdown rendering
                from code_puppy.messaging import get_message_bus
                from code_puppy.messaging.messages import AgentResponseMessage

                response_msg = AgentResponseMessage(
                    content=agent_response,
                    is_markdown=True,
                )
                get_message_bus().emit(response_msg)

                # Update history with the complete conversation — history_processors
                # may miss the final message, so use result.all_messages().
                if hasattr(result, "all_messages"):
                    current_agent.set_message_history(list(result.all_messages()))

                turn_result = result
                turn_success = True

                # Flush so the next prompt isn't swallowed behind the agent response.
                if hasattr(display_console.file, "flush"):
                    display_console.file.flush()

                await asyncio.sleep(
                    0.1
                )  # Brief pause to ensure all messages are rendered

            except KeyboardInterrupt:
                # Defense-in-depth: a bare KeyboardInterrupt mid-unwind must not
                # escape to main_entry — treat as turn cancel (Ctrl+D exits only).
                if current_agent_task is not None and not current_agent_task.done():
                    current_agent_task.cancel()
                from code_puppy.callbacks import on_interactive_turn_cancel
                from code_puppy.messaging import emit_warning

                await on_interactive_turn_cancel(task, reason="Ctrl+C")
                emit_warning("\n" + t("cli.turn.cancelled"))
                continue
            except Exception as e:
                turn_error = e
                _render_turn_exception(e)

            # Auto-save session if enabled (moved outside the try block to avoid being swallowed)
            from code_puppy.config import auto_save_session_if_enabled

            auto_save_session_if_enabled()

            # ================================================================
            # CONTINUATION LOOP: plugins may request follow-up prompt runs.
            # ================================================================
            from code_puppy.callbacks import (
                on_interactive_turn_cancel,
                on_interactive_turn_end,
            )
            from code_puppy.messaging import emit_system_message

            continuation_prompt = task
            continuation_result = turn_result
            continuation_success = turn_success
            continuation_error = turn_error

            while True:
                continuation_requests = await on_interactive_turn_end(
                    current_agent,
                    continuation_prompt,
                    continuation_result,
                    success=continuation_success,
                    error=continuation_error,
                )
                continuation = next(
                    (r for r in continuation_requests if isinstance(r, dict)),
                    None,
                )
                if not continuation:
                    break

                next_prompt = str(continuation.get("prompt") or "").strip()
                if not next_prompt:
                    break

                if continuation.get("clear_context", False):
                    new_session_id = finalize_autosave_session()
                    current_agent.clear_message_history()
                    emit_system_message(
                        t("cli.context.cleared", session=new_session_id)
                    )

                delay = float(continuation.get("delay") or 0)
                if delay > 0:
                    await asyncio.sleep(delay)

                continuation_prompt = next_prompt
                continuation_result = None
                continuation_success = False
                continuation_error = None

                try:
                    result, current_agent_task = await run_prompt_with_attachments(
                        current_agent,
                        next_prompt,
                        display_console=message_renderer.console,
                    )

                    if result is None:
                        await on_interactive_turn_cancel(
                            next_prompt, reason="cancellation"
                        )
                        break

                    agent_response = result.output
                    response_msg = AgentResponseMessage(
                        content=agent_response,
                        is_markdown=True,
                    )
                    get_message_bus().emit(response_msg)

                    if hasattr(result, "all_messages"):
                        current_agent.set_message_history(list(result.all_messages()))

                    if hasattr(display_console.file, "flush"):
                        display_console.file.flush()
                    await asyncio.sleep(0.1)

                    auto_save_session_if_enabled()
                    continuation_result = result
                    continuation_success = True

                except KeyboardInterrupt:
                    await on_interactive_turn_cancel(next_prompt, reason="Ctrl+C")
                    break
                except Exception as e:
                    continuation_error = e
                    _render_turn_exception(e)
                    auto_save_session_if_enabled()

            # Windows: re-clamp raw-Ctrl+C mode after each iteration, as
            # various operations may restore console mode
            try:
                from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                ensure_ctrl_c_disabled()
            except ImportError:
                pass

    # REPL over: tear down the persistent prompt here; main()'s finally is the
    # belt-and-braces for exception paths.
    if persistent_prompt:
        try:
            from code_puppy.messaging.run_ui import stop_persistent_ui

            stop_persistent_ui()
        except Exception:
            pass


async def run_prompt_with_attachments(
    agent,
    raw_prompt: str,
    *,
    display_console=None,
    use_run_ui: bool = True,
):
    """Run the agent after parsing CLI attachments for image/document support.

    Returns:
        tuple: (result, task) where result is the agent response and task is the asyncio task
    """
    import asyncio

    from code_puppy.messaging import emit_system_message, emit_warning

    # Shared resolver: file paths, URLs, and pending clipboard images.
    # (Same helper powers mid-run steering injection — keep them in sync.)
    resolved = resolve_user_prompt(raw_prompt)

    for warning in resolved.warnings:
        emit_warning(warning)

    # Build summary of all attachments
    summary_parts = []
    if resolved.file_attachments:
        summary_parts.append(
            t("cli.attachments.files", count=len(resolved.file_attachments))
        )
    if resolved.clipboard_images:
        summary_parts.append(
            t(
                "cli.attachments.clipboard_images",
                count=len(resolved.clipboard_images),
            )
        )
    if resolved.link_attachments:
        summary_parts.append(
            t("cli.attachments.urls", count=len(resolved.link_attachments))
        )
    if summary_parts:
        emit_system_message(
            t("cli.attachments.detected", summary=", ".join(summary_parts))
        )

    cleaned_prompt = resolved.text
    if not cleaned_prompt:
        emit_warning(t("cli.attachments.empty_prompt"))
        return None, None

    attachments = resolved.attachments
    link_attachments = resolved.link_attachments

    # IMPORTANT: shared console for all streams (markdown/thinking/tool tokens)
    # so output scrolls inside the bottom bar's scroll region.
    from code_puppy.agents.event_stream_handler import set_streaming_console

    set_streaming_console(display_console)

    # Create the agent task first so we can track and cancel it
    agent_task = asyncio.create_task(
        agent.run_with_mcp(
            cleaned_prompt,  # Use cleaned prompt (clipboard placeholders removed)
            attachments=attachments,
            link_attachments=link_attachments,
        )
    )

    # Escape hatch: a cancelled run can wedge mid-unwind (sub-agent/MCP
    # cancel-scope teardown). Racing the task against a detach event keeps
    # the REPL recoverable — repeated cancel gestures escalate to a detach
    # (see _run_signals.make_schedule_cancel) and we abandon the zombie.
    from code_puppy.agents._run_signals import (
        clear_detach_event,
        install_detach_event,
    )

    detach_event = asyncio.Event()
    install_detach_event(detach_event)

    async def _await_agent():
        detach_wait = asyncio.create_task(detach_event.wait())
        try:
            try:
                done, _ = await asyncio.wait(
                    {agent_task, detach_wait}, return_when=asyncio.FIRST_COMPLETED
                )
            except asyncio.CancelledError:
                # The waiter itself was cancelled (shutdown teardown) — same
                # contract as the old bare ``await agent_task`` path.
                emit_info(t("cli.agent.task_cancelled"))
                return None, agent_task
            if agent_task not in done:
                # Escalated cancel: abandon the stuck unwind, free the REPL.
                emit_warning(t("cli.agent.detached"))
                return None, agent_task
            if agent_task.cancelled():
                emit_info(t("cli.agent.task_cancelled"))
                return None, agent_task
            exc = agent_task.exception()
            if exc is not None:
                raise exc
            return agent_task.result(), agent_task
        finally:
            detach_wait.cancel()
            clear_detach_event()

    if use_run_ui:
        # Interactive run: bottom bar stays up while the agent works. run_ui() is
        # idempotent + exception-safe (no-ops on non-TTY), restoring the terminal.
        from code_puppy.messaging.run_ui import run_ui

        with run_ui():
            return await _await_agent()
    return await _await_agent()


def _write_usage_file(path: Path, usage) -> None:
    """Atomically serialize authoritative model usage for automation clients."""
    cost = getattr(usage, "cost", None)
    payload = {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_tokens", 0),
        "cache_write_tokens": getattr(usage, "cache_write_tokens", 0),
        "requests": getattr(usage, "requests", 0),
        "tool_calls": getattr(usage, "tool_calls", 0),
        "cost_usd": float(cost) if cost is not None else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


async def execute_single_prompt(
    prompt: str,
    message_renderer,
    *,
    session_name: str | None = None,
    usage_file: Path | None = None,
) -> None:
    """Execute one headless ``-p`` prompt, dispatching commands and autosaving.

    Agent turns persist under the explicitly resumed session, when supplied,
    or under this process's generated autosave session otherwise. Handled
    slash commands and shell pass-through do not create or overwrite sessions
    because they never invoke the agent.
    """
    from code_puppy.command_line.shell_passthrough import (
        execute_shell_passthrough,
        is_shell_passthrough,
    )

    if is_shell_passthrough(prompt):
        execute_shell_passthrough(prompt)
        return

    from code_puppy.command_line.command_handler import handle_command
    from code_puppy.config import (
        AUTOSAVE_DIR,
        get_current_session_name,
        record_quick_resume_sessions,
    )
    from code_puppy.messaging import (
        emit_error,
        emit_info,
        emit_warning,
        get_message_bus,
    )
    from code_puppy.messaging.messages import AgentResponseMessage
    from code_puppy.session_lifecycle import persist_named_session

    # Match interactive: strip attachments, run handled commands without an
    # agent run, let command-provided replacement text reach the agent.
    command_prompt = (parse_prompt_attachments(prompt).prompt or "").strip()
    if command_prompt.startswith("/"):
        try:
            command_result = handle_command(command_prompt)
        except Exception as command_error:
            emit_error(t("cli.command.error", error=command_error))
            return

        if command_result is True:
            return
        if command_result == "__AUTOSAVE_LOAD__":
            emit_warning(t("cli.autosave.headless_unsupported"))
            return
        if isinstance(command_result, str):
            prompt = command_result

    effective_session_name = session_name or get_current_session_name()
    agent = None
    emit_info(t("cli.headless.executing", prompt=prompt))

    try:
        agent = get_current_agent()
        # Headless -p mode: no run UI (no bottom bar, no line editor) —
        # output must stay plain for pipes/CI even when stdout is a TTY.
        with agent.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
            result, _agent_task = await run_prompt_with_attachments(
                agent,
                prompt,
                display_console=message_renderer.console,
                use_run_ui=False,
            )
        if result is None:
            return

        get_message_bus().emit(
            AgentResponseMessage(content=result.output, is_markdown=True)
        )
        if usage_file is not None:
            usage = result.usage
            _write_usage_file(usage_file, usage() if callable(usage) else usage)

        # The runtime result includes the final assistant response that the
        # incremental history can otherwise miss.
        if hasattr(result, "all_messages"):
            agent.set_message_history(list(result.all_messages()))

    except asyncio.CancelledError:
        emit_warning(t("cli.headless.cancelled"))
    except Exception as error:
        emit_error(t("cli.headless.error", error=error))
    finally:
        try:
            session_agent = agent or get_current_agent()
            persist_named_session(
                session_agent,
                effective_session_name,
                base_dir=Path(AUTOSAVE_DIR),
                auto_saved=True,
            )
            # Point quick-resume at this session (auto and -r NAME saves). Only
            # on success — persist_named_session exceptions skip this block.
            record_quick_resume_sessions(effective_session_name)
        except Exception as save_error:
            # The response has already been emitted; a persistence failure
            # must not hide the primary result.
            emit_error(
                t(
                    "cli.headless.save_failed",
                    session=effective_session_name,
                    error=save_error,
                )
            )


def _force_utf8_stdio():
    """Ensure stdout/stderr can encode non-ASCII output (e.g. emoji prompts).

    On Windows the console often defaults to a legacy code page (e.g. cp1252),
    so writing UTF-8 characters such as the "🐾" onboarding banner raises
    UnicodeEncodeError and crashes the very first run. Reconfigure the streams
    to UTF-8 where the runtime supports it; no-op otherwise.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _initialize_locale():
    """Select the UI locale before any startup message is translated."""
    from code_puppy.config import get_value

    use_detected_locale(get_value("locale"))


def main_entry():
    """Entry point for the installed CLI tool."""
    _force_utf8_stdio()
    try:
        # Capture main()'s return so plugins / normal paths set the exit status
        # (None → 0 or an int exit code).
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        # Note: Using sys.stderr for crash output - messaging system may not be available
        sys.stderr.write(traceback.format_exc())
        return 0
    finally:
        # Reset terminal on Unix-like systems (not Windows)
        reset_unix_terminal()
    # Guard None -> 0 and propagate to the process exit status.
    sys.exit(rc if rc is not None else 0)
