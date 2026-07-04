"""CLI runner for Code Puppy.

Contains the main application logic, interactive mode, and entry point.
"""

# Apply pydantic-ai patches BEFORE any pydantic-ai imports
from code_puppy.pydantic_patches import apply_all_patches

apply_all_patches()

import argparse
import asyncio
import os
import signal
import sys
import traceback
from pathlib import Path

from rich.console import Console

from code_puppy import __version__, callbacks, plugins
from code_puppy.agents import get_current_agent
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
    get_cancel_agent_display_name,
    validate_cancel_agent_key,
)
from code_puppy.messaging import emit_info
from code_puppy.terminal_utils import (
    print_truecolor_warning,
    reset_unix_terminal,
    reset_windows_terminal_ansi,
    reset_windows_terminal_full,
)
from code_puppy.version_checker import default_version_mismatch_behavior

plugins.load_plugin_callbacks()


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

        emit_error(
            f"\U0001f50c The model connection hit a transient error "
            f"({type(exc).__name__}) and didn't recover after auto-retries. "
            "This is almost always a VPN/WiFi/provider blip \u2014 just re-run "
            "your last prompt. Your session history is intact."
        )
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
        "\U0001f50d Quick Resume selected - finding latest session for "
        f"{format_quick_resume_scope(cwd, branch)}"
    )

    quick_resume_pickle = resolve_quick_resume_pickle(target_path)
    if quick_resume_pickle:
        args.resume = quick_resume_pickle
        return True

    emit_info("No previous session found for this scope; starting fresh.")
    return False


async def main():
    """Main async entry point for Code Puppy CLI."""
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
        help="Resume a saved session from a .pkl file (e.g. ~/.code_puppy/contexts/foo.pkl)",
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
        "command", nargs="*", help="Run a single command (deprecated, use -p instead)"
    )

    # Let plugins contribute their own top-level CLI arguments. Plugins are
    # already loaded at import time, so every register_cli_args callback is
    # registered before the parser is built. Duplicate option strings raise
    # here = fail fast.
    callbacks.on_register_cli_args(parser)

    args = parser.parse_args()

    # Give plugins a chance to act on parsed args and short-circuit startup.
    # The first result dict with handled=True wins, exiting with its exit_code.
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

    # Show the awesome Code Puppy logo when entering interactive mode
    # This happens when: no -p flag (prompt-only mode) is used
    # The logo should appear for both `code-puppy` and `code-puppy -i`
    if not args.prompt:
        try:
            import pyfiglet

            intro_lines = pyfiglet.figlet_format(
                "CODE PUPPY", font="ansi_shadow"
            ).split("\n")

            # Simple blue to green gradient (top to bottom)
            gradient_colors = ["bright_blue", "bright_cyan", "bright_green"]
            display_console.print("\n")

            lines = []
            # Apply gradient line by line
            for line_num, line in enumerate(intro_lines):
                if line.strip():
                    # Use line position to determine color (top blue, middle cyan, bottom green)
                    color_idx = min(line_num // 2, len(gradient_colors) - 1)
                    color = gradient_colors[color_idx]
                    lines.append(f"[{color}]{line}[/{color}]")
                else:
                    lines.append("")
            # Print directly to console to avoid the 'dim' style from emit_system_message
            display_console.print("\n".join(lines))
        except ImportError:
            emit_system_message("🐶 Code Puppy is Loading...")

        # Truecolor warning moved to interactive_mode() so it prints LAST
        # after all the help stuff - max visibility for the ugly red box!

    available_port = find_available_port()
    if available_port is None:
        emit_error("No available ports in range 8090-9010!")
        return

    # Early model setting if specified via command line
    # This happens before ensure_config_exists() to ensure config is set up correctly
    early_model = None
    if args.model:
        early_model = args.model.strip()
        from code_puppy.config import set_model_name

        set_model_name(early_model)

    ensure_config_exists()

    # Validate cancel_agent_key configuration early
    try:
        validate_cancel_agent_key()
    except KeymapError as e:
        from code_puppy.messaging import emit_error

        emit_error(str(e))
        sys.exit(1)

    # Show uvx detection notice if we're on Windows + uvx
    # Also disable Ctrl+C at the console level to prevent terminal bricking
    try:
        from code_puppy.uvx_detection import should_use_alternate_cancel_key

        if should_use_alternate_cancel_key():
            from code_puppy.terminal_utils import (
                disable_windows_ctrl_c,
                install_windows_ctrl_c_swallower,
                set_keep_ctrl_c_disabled,
            )

            # Layer 1: Strip ENABLE_PROCESSED_INPUT so the console doesn't
            # translate Ctrl+C into a signal in the first place.
            disable_windows_ctrl_c()

            # Layer 2: Register an OS-level SetConsoleCtrlHandler that
            # swallows CTRL_C_EVENT even if something flips processed-input
            # back on (e.g. prompt_toolkit, a child shell exit, etc).
            install_windows_ctrl_c_swallower()

            # Set flag to keep console mode clamped (prompt_toolkit may
            # re-enable processed input on entry/exit).
            set_keep_ctrl_c_disabled(True)

            # Use print directly - emit_system_message can get cleared by ANSI codes
            print(
                "🔧 Detected uvx launch on Windows - using Ctrl+K for cancellation "
                "(Ctrl+C is disabled to prevent terminal issues)"
            )

            # Layer 3: Python-level SIGINT backup. If a SIGINT somehow
            # squeezes past layers 1 and 2, this handler resets the terminal
            # and re-clamps everything before returning. It deliberately
            # does NOT cancel the agent — Ctrl+K owns that on uvx+Windows.
            import signal

            from code_puppy.terminal_utils import reset_windows_terminal_full

            def _uvx_protective_sigint_handler(_sig, _frame):
                """Protective SIGINT handler for Windows+uvx."""
                reset_windows_terminal_full()
                # Re-arm all the guards in case something dropped them.
                disable_windows_ctrl_c()
                install_windows_ctrl_c_swallower()

            signal.signal(signal.SIGINT, _uvx_protective_sigint_handler)
    except ImportError:
        pass  # uvx_detection module not available, ignore

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

                emit_error(f"Model '{model_name}' not found")
                emit_system_message(f"Available models: {', '.join(available_models)}")
                sys.exit(1)

            # Model is valid, show confirmation (already set earlier)
            emit_system_message(f"🎯 Using model: {model_name}")
        except Exception as e:
            emit_error(f"Error validating model: {str(e)}")
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
                emit_error(f"Agent '{agent_name}' not found")
                emit_system_message(
                    f"Available agents: {', '.join(available_agents.keys())}"
                )
                sys.exit(1)

            # Agent exists, set it
            set_current_agent(agent_name)
            emit_system_message(f"🤖 Using agent: {agent_name}")
        except Exception as e:
            emit_error(f"Error setting agent: {str(e)}")
            sys.exit(1)

    current_version = __version__

    no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if no_version_update:
        version_msg = f"Current version: {current_version}"
        update_disabled_msg = (
            "Update phase disabled because NO_VERSION_UPDATE is set to 1 or true"
        )
        emit_system_message(version_msg)
        emit_system_message(update_disabled_msg)
    else:
        if len(callbacks.get_callbacks("version_check")):
            await callbacks.on_version_check(current_version)
        else:
            default_version_mismatch_behavior(current_version)

    # One-shot sweep of legacy ~/.code_puppy/contexts/ into the unified
    # autosaves/ store. Idempotent via a sentinel; safe to call every
    # startup. MUST run before any plugin startup callback can read
    # AUTOSAVE_DIR (otherwise a plugin could miss freshly-swept files)
    # and before the resume block below resolves -r NAME.
    try:
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        sweep_contexts_to_autosaves()
    except Exception:
        # Sweep failure must never block startup -- it logs internally.
        pass

    await callbacks.on_startup()

    # Resolve --quick-resume [PATH] into --resume so the resume machinery below
    # loads the most recent session for that canonical (git-root + branch) scope.
    apply_quick_resume(args)

    # Holds the resolved (normalised) session name when -r/--resume is in
    # effect, so save-back paths can persist into the same file the resolver
    # opened — not the raw user input (which might be ``foo.pkl`` or an
    # absolute path that the resolver normalised to a bare slug).
    resolved_resume_session: str | None = None

    if args.resume:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.config import AUTOSAVE_DIR, pin_current_session_name
        from code_puppy.messaging import emit_error, emit_info, emit_success
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )
        from code_puppy.session_storage import list_sessions, load_session

        resume_target = args.resume
        sessions_dir = Path(AUTOSAVE_DIR)

        # Lazy-create is symmetric across modes: both headless and
        # interactive accept ``-r missing-name`` and materialise an
        # empty session. The typo-guard concern is preserved by the
        # visible ``Created new session: NAME`` info line plus the
        # empty ``message_count: 0`` initial state.
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
            available = list_sessions(sessions_dir)
            if available:
                emit_info(f"Available sessions: {', '.join(available[:10])}")
            sys.exit(1)

        # When lazy-create fired, announce it so scripts and users can
        # distinguish first-run creation from a normal resume.
        if lazy_created:
            emit_info(f"Created new session: {session_name}")

        try:
            history = load_session(session_name, session_dir)
            agent = get_current_agent()
            agent.set_message_history(history)
            total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

            # Pin the singleton so periodic autosave AND headless save-back
            # both update this named file in place. Replaces the old
            # rotate_autosave_id() call, which under unification would
            # actively undo the named-session wiring we want.
            #
            # Note: even when the user resumed via an absolute path
            # (resolver branches 1 or 3), we pin the *stem* and let
            # subsequent writes land in AUTOSAVE_DIR. That keeps cross-mode
            # resume by name consistent; users who passed a one-off path
            # can copy the resulting AUTOSAVE_DIR file back if they care.
            pin_current_session_name(session_name)

            # Record the resolved name for the headless save-back path below.
            resolved_resume_session = session_name

            if not lazy_created:
                emit_success(
                    f"Resumed: {len(history)} messages "
                    f"({total_tokens} tokens) from {session_name}"
                )
        except Exception as e:
            emit_error(f"Failed to resume from {resume_target}: {e}")
            sys.exit(1)

    global shutdown_flag
    shutdown_flag = False
    try:
        initial_command = None
        prompt_only_mode = False

        if args.prompt:
            initial_command = args.prompt
            prompt_only_mode = True
        elif args.command:
            initial_command = " ".join(args.command)
            prompt_only_mode = False

        if prompt_only_mode:
            await execute_single_prompt(
                initial_command,
                message_renderer,
                session_name=resolved_resume_session,
            )
        else:
            # Default to interactive mode (no args = same as -i)
            await interactive_mode(message_renderer, initial_command=initial_command)
    finally:
        # Persistent prompt teardown FIRST (restores scroll region +
        # cursor + key listener) so the renderer stops on a sane screen.
        # Idempotent no-op when the persistent UI never started.
        try:
            from code_puppy.messaging.run_ui import stop_persistent_ui

            stop_persistent_ui()
        except Exception:
            pass
        if message_renderer:
            message_renderer.stop()
        if bus_renderer:
            bus_renderer.stop()
        # session_end fires BEFORE shutdown so plugins can react to the
        # session ending while the bus / agent state is still coherent.
        try:
            await callbacks.on_session_end()
        except Exception:
            pass
        await callbacks.on_shutdown()


def _use_persistent_prompt() -> bool:
    """Should the REPL use the persistent bottom-bar prompt (Phase A)?

    False (→ classic prompt_toolkit path) when:
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
    # Raw-VT gate: enable + verify Windows VT processing up front (no-op
    # True on POSIX). Unconfirmed VT -> classic prompt, which also keeps
    # the bar inactive so the spinner/panel tickers never start.
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
        from code_puppy.command_line.prompt_toolkit_completion import (
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


def _user_prompt_echo(task: str):
    """Transcript echo for a submitted prompt, banner-tagged.

    The persistent editor clears its row on submit, so scrollback needs
    a record of what was asked. A bare ``> `` marker looked like an
    orphaned prompt row (especially on Windows); tag it like every other
    transcript block (AGENT RESPONSE, SHELL COMMAND, ...) instead.
    Built with ``Text`` (not markup) so bracket-y input renders as-is.
    """
    from rich.text import Text

    from code_puppy.config import get_banner_color

    color = get_banner_color("user_prompt")
    echo = Text("\n")
    echo.append(" USER PROMPT ", style=f"bold white on {color}")
    echo.append(f" {task}", style="bold")
    return echo


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
    # Nothing is running that owns cancellation (otherwise their handler would
    # be installed instead of this one). Swallow the signal so a fast repeat
    # tap can't escape to main_entry and exit the process.
    #
    # Persistent prompt: Ctrl+C with text in the buffer clears it (classic
    # readline feel); with an empty buffer it stays a no-op (Ctrl+D is
    # quit). Mid-run this guard only owns SIGINT when the cancel key is
    # remapped (e.g. Windows defaults to ctrl+k) — buffer-first clearing
    # applies there too; cancellation stays with the remapped hotkey.
    try:
        from code_puppy.messaging.run_ui import (
            absorb_ctrl_c_if_composing,
            clear_idle_buffer,
            is_run_active,
        )

        if is_run_active():
            absorb_ctrl_c_if_composing()
        else:
            clear_idle_buffer()
    except Exception:
        pass
    return


async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    """Run the agent in interactive mode."""
    from code_puppy.command_line.command_handler import handle_command

    display_console = message_renderer.console
    from code_puppy.messaging import emit_info, emit_system_message

    emit_system_message(
        "Type '/exit', '/quit', or press Ctrl+D to exit the interactive mode."
    )
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message("Type /help to view all commands")
    emit_system_message(
        "Type @ for path completion, or /model to pick a model. Toggle multiline with Alt+M or F2; newline: Ctrl+J."
    )
    emit_system_message("Paste images: Ctrl+V (even on Mac!), F3, or /paste command.")
    import platform

    if platform.system() == "Darwin":
        emit_system_message(
            "💡 macOS tip: Use Ctrl+V (not Cmd+V) to paste images in terminal."
        )
    cancel_key = get_cancel_agent_display_name()
    emit_system_message(
        f"Press {cancel_key} during processing to cancel the current task or inference. Use Ctrl+X to interrupt running shell commands."
    )
    emit_system_message(
        "Use /autosave_load to manually load a previous autosave session."
    )
    emit_system_message(
        "Use /diff to configure diff highlighting colors for file changes."
    )
    emit_system_message("To re-run the tutorial, use /tutorial.")
    emit_system_message(
        "!<command> to run shell commands directly (e.g., !git status)",
    )
    # Print truecolor warning LAST so it's the most visible thing on startup
    # Big ugly red box should be impossible to miss! 🔴
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
        emit_info(f"Processing initial command: {initial_command}")

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

                # Update the agent's message history with the complete conversation
                # including the final assistant response
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

                emit_success("🐶 Continuing in Interactive Mode")
                emit_system_message(
                    "Your command and response are preserved in the conversation history."
                )

        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(f"Error processing initial command: {str(e)}")

    # Check if prompt_toolkit is installed
    try:
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
            get_prompt_with_active_model,
        )
    except ImportError:
        from code_puppy.messaging import emit_warning

        emit_warning("Warning: prompt_toolkit not installed. Installing now...")
        try:
            import subprocess

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "prompt_toolkit"]
            )
            from code_puppy.messaging import emit_success

            emit_success("Successfully installed prompt_toolkit")
            from code_puppy.command_line.prompt_toolkit_completion import (
                get_input_with_combined_completion,
                get_prompt_with_active_model,
            )
        except Exception as e:
            from code_puppy.messaging import emit_error, emit_warning

            emit_error(f"Error installing prompt_toolkit: {e}")
            emit_warning("Falling back to basic input without tab completion")

    # Autosave loading is now manual - use /autosave_load command

    record_terminal_session(get_current_session_name(), overwrite=False)
    # Track the current agent task for cancellation on quit
    current_agent_task = None

    # Install a session-wide baseline SIGINT guard for the lifetime of the
    # REPL. Ctrl+C is a *cancel* gesture here (Ctrl+D quits), and the per-run
    # / per-shell handlers own cancellation while they're active, saving and
    # restoring whatever handler preceded them. Without this baseline, the
    # restored handler in the gap between those windows is Python's default,
    # which raises KeyboardInterrupt -- so a fast Ctrl+C double-tap can slip
    # through the unwind after the first cancel and exit the whole process.
    # We deliberately do NOT restore the previous handler: when this loop
    # exits the program is shutting down, so SIGINT ownership for the REPL's
    # whole life belongs here. Best effort -- signal.signal is main-thread only.
    try:
        signal.signal(signal.SIGINT, _interactive_sigint_guard)
    except (ValueError, OSError):
        pass

    # ------------------------------------------------------------------
    # Persistent-prompt mode (Phase A): the bottom-bar editor is THE
    # prompt — idle AND running. The input line stays pinned; output
    # scrolls above it; no prompt swap between turns. Classic
    # prompt_toolkit path remains intact behind the rollback flag /
    # non-TTY auto-degrade (see _use_persistent_prompt).
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
        user_prompt = current_agent.get_user_prompt() or "Enter your coding task:"

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
                # Idle + queued prompts (added via /queue, or a cancelled
                # run's leftovers): consume the oldest as this turn instead
                # of waiting for input. Runs added mid-run normally drain
                # inside _runtime's between-turns loop and never get here.
                from code_puppy.messaging.pause_controller import (
                    get_pause_controller as _get_pc,
                )

                queued_task = _get_pc().pop_next_steer_queued()
                if queued_task is not None:
                    task = queued_task
                    emit_info(_user_prompt_echo(task))
                    emit_info("⏭ running queued prompt")
                else:
                    # Raises EOFError on Ctrl+D-with-empty-buffer, which the
                    # existing quit branch below handles.
                    task = await wait_for_idle_submission()
                    # Echo into the transcript (see _user_prompt_echo) --
                    # repeating the whole prompt chrome doubled every
                    # line's noise, so it's just a tag + the user's text.
                    emit_info(_user_prompt_echo(task))
            else:
                # Use prompt_toolkit for enhanced input with path completion
                try:
                    # Windows-specific: Reset terminal state before prompting
                    reset_windows_terminal_ansi()

                    # Use the async version of get_input_with_combined_completion
                    task = await get_input_with_combined_completion(
                        get_prompt_with_active_model(),
                        history_file=COMMAND_HISTORY_FILE,
                    )

                    # Windows+uvx: Re-disable Ctrl+C after prompt_toolkit
                    # (prompt_toolkit restores console mode which re-enables Ctrl+C)
                    try:
                        from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                        ensure_ctrl_c_disabled()
                    except ImportError:
                        pass
                except ImportError:
                    # Fall back to basic input if prompt_toolkit is not available
                    task = input(">>> ")

        except (KeyboardInterrupt, asyncio.CancelledError):
            # Handle Ctrl+C - cancel input and continue
            # Windows-specific: Reset terminal state after interrupt to prevent
            # the terminal from becoming unresponsive (can't type characters)
            reset_windows_terminal_full()
            from code_puppy.callbacks import on_interactive_turn_cancel
            from code_puppy.messaging import emit_warning

            await on_interactive_turn_cancel("", reason="Ctrl+C")
            emit_warning("\nInput cancelled")
            continue
        except EOFError:
            # Handle Ctrl+D - exit the application
            from code_puppy.messaging import emit_success

            emit_success("\nGoodbye! (Ctrl+D)")

            # Cancel any running agent task for clean shutdown
            if current_agent_task and not current_agent_task.done():
                emit_info("Cancelling running agent task...")
                current_agent_task.cancel()
                try:
                    await current_agent_task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

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

            emit_success("Goodbye!")

            # Cancel any running agent task for clean shutdown
            if current_agent_task and not current_agent_task.done():
                emit_info("Cancelling running agent task...")
                current_agent_task.cancel()
                try:
                    await current_agent_task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

            # The renderer is stopped in the finally block of main().
            break

        # Backward-compat: bare `clear` (no slash) is rewritten to `/clear`
        # so the registered handler in session_commands is the single source
        # of truth. The slash form is dispatched normally below.
        if task.strip().lower() == "clear":
            task = "/clear"

        # Parse attachments first so leading paths aren't misread as commands
        processed_for_commands = parse_prompt_attachments(task)
        cleaned_for_commands = (processed_for_commands.prompt or "").strip()

        # Handle / commands based on cleaned prompt (after stripping attachments)
        if cleaned_for_commands.startswith("/"):
            try:
                # Commands may open prompt_toolkit menus: with the
                # persistent prompt the bar is up even at idle, so release
                # the terminal for the duration (no-op in classic mode).
                from code_puppy.messaging.run_ui import suspended_run_ui

                with suspended_run_ui():
                    command_result = handle_command(cleaned_for_commands)
            except Exception as e:
                from code_puppy.messaging import emit_error

                emit_error(f"Command error: {e}")
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
                            from code_puppy.session_storage import (
                                load_session,
                                restore_autosave_interactively,
                            )

                            from code_puppy.messaging.run_ui import (
                                suspended_run_ui,
                            )

                            with suspended_run_ui():
                                chosen_session = await interactive_autosave_picker()

                            if not chosen_session:
                                emit_warning("Autosave load cancelled")
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
                            session_path = base_dir / f"{chosen_session}.pkl"

                            emit_success(
                                f"✅ Autosave loaded: {len(history)} messages ({total_tokens} tokens)\n"
                                f"📁 From: {session_path}"
                            )

                            # Display recent message history for context
                            from code_puppy.command_line.autosave_menu import (
                                display_resumed_history,
                            )

                            display_resumed_history(history)
                        else:
                            # Fall back to old text-based picker for tests/non-TTY environments
                            await restore_autosave_interactively(Path(AUTOSAVE_DIR))

                    except Exception as e:
                        from code_puppy.messaging import emit_error

                        emit_error(f"Failed to load autosave: {e}")
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
                    # Re-disable Ctrl+C if needed (uvx mode)
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

                # Update the agent's message history with the complete conversation
                # including the final assistant response. The history_processors callback
                # may not capture the final message, so we use result.all_messages()
                # to ensure the autosave includes the complete conversation.
                if hasattr(result, "all_messages"):
                    current_agent.set_message_history(list(result.all_messages()))

                turn_result = result
                turn_success = True

                # Ensure console output is flushed before next prompt
                # This fixes the issue where prompt doesn't appear after agent response
                if hasattr(display_console.file, "flush"):
                    display_console.file.flush()

                await asyncio.sleep(
                    0.1
                )  # Brief pause to ensure all messages are rendered

            except KeyboardInterrupt:
                # Defense-in-depth: even with the session SIGINT guard, a
                # bare KeyboardInterrupt during the unwind of a fast Ctrl+C
                # double-tap must NOT escape to main_entry (that exits the
                # whole process). Treat it as a turn cancel and keep the REPL
                # alive -- Ctrl+D is the only way out.
                if current_agent_task is not None and not current_agent_task.done():
                    current_agent_task.cancel()
                from code_puppy.callbacks import on_interactive_turn_cancel
                from code_puppy.messaging import emit_warning

                await on_interactive_turn_cancel(task, reason="Ctrl+C")
                emit_warning("\nCancelled")
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
                        f"Context cleared. Session rotated to: {new_session_id}"
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

            # Re-disable Ctrl+C if needed (uvx mode) - must be done after
            # each iteration as various operations may restore console mode
            try:
                from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                ensure_ctrl_c_disabled()
            except ImportError:
                pass

    # REPL over (exit/quit/Ctrl+D broke the loop): tear the persistent
    # prompt down here; main()'s finally is the belt-and-braces for
    # exception paths.
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
        summary_parts.append(f"files: {len(resolved.file_attachments)}")
    if resolved.clipboard_images:
        summary_parts.append(f"clipboard images: {len(resolved.clipboard_images)}")
    if resolved.link_attachments:
        summary_parts.append(f"urls: {len(resolved.link_attachments)}")
    if summary_parts:
        emit_system_message("Attachments detected -> " + ", ".join(summary_parts))

    cleaned_prompt = resolved.text
    if not cleaned_prompt:
        emit_warning(
            "Prompt is empty after removing attachments; add instructions and retry."
        )
        return None, None

    attachments = resolved.attachments
    link_attachments = resolved.link_attachments

    # IMPORTANT: Set the shared console for streaming output so every
    # stream (markdown, thinking, tool token lines) writes through the
    # same console — output scrolls inside the bottom bar's scroll region.
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

    async def _await_agent():
        try:
            result = await agent_task
            return result, agent_task
        except asyncio.CancelledError:
            emit_info("Agent task cancelled")
            return None, agent_task

    if use_run_ui:
        # Interactive run: bottom bar (scroll region + status + live prompt
        # via RunningLineEditor) stays up while the agent works. run_ui()
        # is idempotent + exception-safe and silently no-ops on non-TTY
        # stdout, so cancel/exception paths always restore the terminal.
        from code_puppy.messaging.run_ui import run_ui

        with run_ui():
            return await _await_agent()
    return await _await_agent()


async def execute_single_prompt(
    prompt: str,
    message_renderer,
    *,
    session_name: str | None = None,
) -> None:
    """Execute a single prompt and exit (for -p flag).

    When ``session_name`` is supplied (i.e. the user passed ``-r NAME``),
    history is persisted back to that named session in a ``finally`` block
    so partial state still lands on cancel / error paths. The runtime
    prunes interrupted tool calls before returning so the saved history is
    coherent (see ``agents/_runtime.py`` -- the two ``_message_history``
    commit/prune sites around lines 446 and 498).

    Edge case worth knowing: when the agent returns ``(None, None)`` for an
    empty-prompt scenario, the response emit is skipped but the ``finally``
    still fires, producing a no-op idempotent rewrite of an existing
    session (and a phantom ``post_autosave`` event for plugin authors who
    count saves). Acceptable trade-off versus the complexity of a
    'something-actually-ran' tracking flag.
    """
    # Shell pass-through: !<cmd> bypasses the agent even in -p mode
    from code_puppy.command_line.shell_passthrough import (
        execute_shell_passthrough,
        is_shell_passthrough,
    )

    if is_shell_passthrough(prompt):
        execute_shell_passthrough(prompt)
        # Agent never ran — do NOT touch the named session, otherwise
        # `-r mywork -p '!ls'` would clobber existing history with an empty
        # save-back. Return before the try/finally so the save path is
        # genuinely unreachable, not just guarded.
        return

    from code_puppy.messaging import (
        emit_error,
        emit_info,
        emit_warning,
        get_message_bus,
    )
    from code_puppy.messaging.messages import AgentResponseMessage

    # Hoist save-back imports here rather than into the ``finally`` block --
    # if the user passed ``-r`` we will exercise these on every code path,
    # and lazy-importing inside ``finally`` just hides the dependency without
    # buying any actual startup savings (the module is already loaded).
    from code_puppy.config import AUTOSAVE_DIR
    from code_puppy.session_lifecycle import persist_named_session

    emit_info(f"Executing prompt: {prompt}")

    try:
        # Get agent through runtime manager and use helper for attachments
        agent = get_current_agent()
        # Headless -p mode: no run UI (no bottom bar, no line editor) —
        # output must stay plain for pipes/CI even when stdout is a TTY.
        result, _agent_task = await run_prompt_with_attachments(
            agent,
            prompt,
            display_console=message_renderer.console,
            use_run_ui=False,
        )
        if result is not None:
            response_msg = AgentResponseMessage(
                content=result.output,
                is_markdown=True,
            )
            get_message_bus().emit(response_msg)

            # Commit the completed turn (user prompt + assistant response)
            # into the agent's history BEFORE the finally-block save-back.
            # Without this, headless -r save-back persists only user prompts
            # (the normal _do_run path never writes result.all_messages()
            # back to agent._message_history), so resumed sessions feed the
            # model a pile of unanswered prompts and it re-answers them all.
            # Mirrors interactive_mode's post-run set_message_history call.
            if hasattr(result, "all_messages"):
                agent.set_message_history(list(result.all_messages()))

    except asyncio.CancelledError:
        emit_warning("Execution cancelled by user")
    except Exception as e:
        emit_error(f"Error executing prompt: {str(e)}")
    finally:
        if session_name:
            try:
                persist_named_session(
                    get_current_agent(),
                    session_name,
                    base_dir=Path(AUTOSAVE_DIR),
                    # Headless -r save-back is automated (user passed a
                    # flag and walked away) rather than an explicit
                    # /dump_context-style intent, so it carries the same
                    # auto_saved=True bit as autosave proper. Plugins
                    # that filter on `metadata.auto_saved` get the right
                    # signal.
                    auto_saved=True,
                )
            except Exception as save_exc:
                # The user's primary deliverable (the agent response) has
                # already been emitted. Report the save failure but do not
                # re-raise -- a save bug shouldn't mask a successful turn.
                emit_error(f"Failed to save session {session_name}: {save_exc}")


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


def main_entry():
    """Entry point for the installed CLI tool."""
    _force_utf8_stdio()
    try:
        # Capture main()'s return value so handle_cli_args plugins (and the
        # normal return-0 path) actually influence the process exit status.
        # main() may return None (treated as 0) or an int exit code.
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
