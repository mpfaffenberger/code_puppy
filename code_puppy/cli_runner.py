"""CLI runner for Code Puppy.

Contains the main application logic, interactive mode, and entry point.
"""

# Apply pydantic-ai patches BEFORE any pydantic-ai imports
from code_puppy.pydantic_patches import apply_all_patches

apply_all_patches()

import argparse
from typing import Any, Literal


import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

from dbos import DBOS, DBOSConfig
from rich.console import Console

from code_puppy import __version__, callbacks, plugins
from code_puppy.agents import get_current_agent
from code_puppy.command_line.attachments import parse_prompt_attachments
from code_puppy.command_line.clipboard import get_clipboard_manager
from code_puppy.command_line.interactive_command import BackgroundInteractiveCommand
from code_puppy.command_line.interactive_runtime import (
    PromptRuntimeState,
    QueuedPrompt,
    clear_active_interactive_runtime,
    register_active_interactive_runtime,
)
from code_puppy.config import (
    AUTOSAVE_DIR,
    COMMAND_HISTORY_FILE,
    DBOS_DATABASE_URL,
    ensure_config_exists,
    finalize_autosave_session,
    get_use_dbos,
    initialize_command_history_file,
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
from code_puppy.tools.common import console
from code_puppy.version_checker import default_version_mismatch_behavior
try:
    from code_puppy.debug_capture import (
        get_active_capture,
        log_event,
        set_active_capture,
        start_capture_session,
    )
except ImportError:
    # Keep CLI usable in checkouts that don't include debug_capture.
    def get_active_capture():
        return None

    def log_event(*args, **kwargs):
        return None

    def set_active_capture(*args, **kwargs):
        return None

    def start_capture_session():
        return None

plugins.load_plugin_callbacks()


def emit_interject_queue_lifecycle(
    runtime_state: PromptRuntimeState,
    action: str,
    *,
    item: QueuedPrompt | None = None,
    reason: str | None = None,
    position: int | None = None,
    level: str = "info",
) -> dict[str, Any]:
    """Emit interject/queue lifecycle to UI, debug log, and frontend emitter."""
    payload: dict[str, Any] = {
        "action": action,
        "kind": item.kind if item else None,
        "text": item.text if item else None,
        "reason": reason,
        "position": position,
        "queue_size": len(runtime_state.queue),
        "running": runtime_state.running,
    }
    try:
        from code_puppy.plugins.frontend_emitter.emitter import emit_event

        emit_event("interject_queue", payload)
    except Exception:
        pass

    log_event("interject_queue", **payload)

    try:
        from code_puppy.messaging import MessageLevel, TextMessage, get_message_bus

        text = _format_queue_lifecycle_text(
            action,
            item=item,
            reason=reason,
            position=position,
        )
        if text is None:
            return payload

        level_map = {
            "error": MessageLevel.ERROR,
            "warning": MessageLevel.WARNING,
            "success": MessageLevel.SUCCESS,
            "info": MessageLevel.INFO,
        }
        get_message_bus().emit(
            TextMessage(level=level_map.get(level, MessageLevel.INFO), text=text)
        )
    except Exception:
        pass
    return payload


def _format_queue_lifecycle_text(
    action: str,
    *,
    item: QueuedPrompt | None = None,
    reason: str | None = None,
    position: int | None = None,
) -> str | None:
    """Translate internal queue lifecycle steps into user-facing copy."""
    if action == "dequeued":
        return None

    if item is None:
        if action == "rejected":
            return "[QUEUE] couldn't save that prompt"
        return f"[QUEUE] {action}"

    if item.kind == "interject":
        if action in {"started", "completed"}:
            return None
        if action == "cancelled" and reason == "run_cancelled":
            return None
        action_text = {
            "queued": "stopping current work",
            "cancelled": "cancelled",
            "failed": "failed",
            "rejected": "couldn't apply",
        }.get(action, action.replace("_", " "))
        return f"[INTERJECT] {action_text}: {item.text}"

    if action == "queued":
        if position is not None:
            return f"[Queued][{position}] {item.text}"
        return f"[Queued] {item.text}"

    if action == "started":
        return None
    if action == "completed" and reason is None:
        return None
    if action == "cancelled" and reason == "run_cancelled":
        return None

    action_text = {
        "completed": "finished",
        "cancelled": "cancelled",
        "failed": "failed",
        "rejected": "couldn't save",
    }.get(action, action.replace("_", " "))
    return f"[QUEUE] {action_text}: {item.text}"


def _build_interject_submission_text(text: str) -> str:
    """Wrap an interjected prompt so the agent resumes the interrupted task."""
    return (
        "user interjects - "
        f"{text} - "
        "please affirm you've seen this interjection, continue the interrupted task, "
        "and proceed with that in mind"
    )


def _seed_spinner_context(agent, prompt: str, *, link_attachments: list[str]) -> None:
    """Seed context usage immediately so the prompt status line is not stale."""
    from code_puppy.messaging.spinner import (
        SpinnerBase,
        clear_spinner_context,
        update_spinner_context,
    )

    clear_spinner_context()

    try:
        history = (
            agent.get_message_history()
            if hasattr(agent, "get_message_history")
            else []
        ) or []
        estimate_tokens_for_message = getattr(agent, "estimate_tokens_for_message", None)
        estimate_context_overhead_tokens = getattr(
            agent, "estimate_context_overhead_tokens", None
        )
        estimate_token_count = getattr(agent, "estimate_token_count", None)
        get_model_context_length = getattr(agent, "get_model_context_length", None)

        if not callable(estimate_token_count) or not callable(get_model_context_length):
            return

        history_tokens = 0
        if callable(estimate_tokens_for_message):
            history_tokens = sum(
                estimate_tokens_for_message(message) for message in history
            )

        overhead_tokens = (
            estimate_context_overhead_tokens()
            if callable(estimate_context_overhead_tokens)
            else 0
        )
        prompt_tokens = estimate_token_count(prompt) if prompt else 0
        link_tokens = sum(estimate_token_count(url) for url in link_attachments)
        total_tokens = max(0, history_tokens + overhead_tokens + prompt_tokens + link_tokens)
        capacity = max(1, int(get_model_context_length()))

        update_spinner_context(
            SpinnerBase.format_context_info(
                total_tokens,
                capacity,
                total_tokens / capacity,
            )
        )
    except Exception:
        return


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
        "--debug-capture",
        action="store_true",
        help="Write timestamped interactive terminal capture artifacts",
    )
    parser.add_argument(
        "command", nargs="*", help="Run a single command (deprecated, use -p instead)"
    )
    args = parser.parse_args()

    from code_puppy.messaging import (
        LegacyQueueToBusBridge,
        RichConsoleRenderer,
        get_global_queue,
        get_message_bus,
    )

    capture_session = None
    if args.debug_capture:
        capture_session = start_capture_session()
        if capture_session is not None:
            set_active_capture(capture_session)
            log_event(
                "debug_capture_enabled", session_dir=str(capture_session.session_dir)
            )
        else:
            print(
                "Warning: --debug-capture requested but debug_capture module is unavailable."
            )

    # Create one shared console to avoid multi-renderer race conditions.
    display_console = Console()

    # Bridge legacy queue emitters into the structured bus.
    message_queue = get_global_queue()
    message_bus = get_message_bus()
    legacy_bridge = LegacyQueueToBusBridge(message_queue, message_bus)
    legacy_bridge.start()

    # Single UI renderer in interactive mode.
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
                set_keep_ctrl_c_disabled,
            )

            # Disable Ctrl+C at the console input level
            # This prevents Ctrl+C from being processed as a signal at all
            disable_windows_ctrl_c()

            # Set flag to keep it disabled (prompt_toolkit may re-enable it)
            set_keep_ctrl_c_disabled(True)

            # Use print directly - emit_system_message can get cleared by ANSI codes
            print(
                "🔧 Detected uvx launch on Windows - using Ctrl+K for cancellation "
                "(Ctrl+C is disabled to prevent terminal issues)"
            )

            # Also install a SIGINT handler as backup
            import signal

            from code_puppy.terminal_utils import reset_windows_terminal_full

            def _uvx_protective_sigint_handler(_sig, _frame):
                """Protective SIGINT handler for Windows+uvx."""
                reset_windows_terminal_full()
                # Re-disable Ctrl+C in case something re-enabled it
                disable_windows_ctrl_c()

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

    await callbacks.on_startup()

    # Initialize DBOS if not disabled
    if get_use_dbos():
        # Append a Unix timestamp in ms to the version for uniqueness
        dbos_app_version = os.environ.get(
            "DBOS_APP_VERSION", f"{current_version}-{int(time.time() * 1000)}"
        )
        dbos_config: DBOSConfig = {
            "name": "dbos-code-puppy",
            "system_database_url": DBOS_DATABASE_URL,
            "run_admin_server": False,
            "conductor_key": os.environ.get(
                "DBOS_CONDUCTOR_KEY"
            ),  # Optional, if set in env, connect to conductor
            "log_level": os.environ.get(
                "DBOS_LOG_LEVEL", "ERROR"
            ),  # Default to ERROR level to suppress verbose logs
            "application_version": dbos_app_version,  # Match DBOS app version to Code Puppy version
        }
        try:
            DBOS(config=dbos_config)
            DBOS.launch()
        except Exception as e:
            emit_error(f"Error initializing DBOS: {e}")
            sys.exit(1)
    else:
        pass

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
            await execute_single_prompt(initial_command, bus_renderer)
        else:
            # Default to interactive mode (no args = same as -i)
            await interactive_mode(bus_renderer, initial_command=initial_command)
    finally:
        if bus_renderer:
            bus_renderer.stop()
        if legacy_bridge:
            legacy_bridge.stop()
        if capture_session:
            capture_session.stop(exit_reason="shutdown")
            set_active_capture(None)
        await callbacks.on_shutdown()
        if get_use_dbos():
            DBOS.destroy()


async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    """Run the agent in interactive mode."""
    from code_puppy.command_line.command_handler import handle_command

    runtime = PromptRuntimeState()
    register_active_interactive_runtime(runtime)
    runtime.mark_idle()
    try:
        display_console = message_renderer.console
        from code_puppy.messaging import emit_info, emit_system_message

        emit_system_message(
            "Type '/exit', '/quit', or press Ctrl+D to exit the interactive mode."
        )
        log_event("interactive_mode_start")
        emit_system_message("Type 'clear' to reset the conversation history.")
        emit_system_message("Type /help to view all commands")
        emit_system_message(
            "Type @ for path completion, or /model to pick a model. Toggle multiline with Alt+M or F2; newline: Ctrl+J."
        )
        emit_system_message(
            "Paste images: Ctrl+V (even on Mac!), F3, or /paste command."
        )
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
            "!<command> to run shell commands directly (e.g., !git status)"
        )
        try:
            from code_puppy.command_line.motd import print_motd

            print_motd(console, force=False)
        except Exception as e:
            from code_puppy.messaging import emit_warning

            emit_warning(f"MOTD error: {e}")

        # Print truecolor warning LAST so it's the most visible thing on startup
        # Big ugly red box should be impossible to miss! 🔴
        print_truecolor_warning(display_console)

        # Shell pass-through for initial_command: !<cmd> bypasses the agent.
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
                # Check if any tool is waiting for user input before showing spinner
                try:
                    from code_puppy.tools.command_runner import is_awaiting_user_input

                    awaiting_input = is_awaiting_user_input()
                except ImportError:
                    awaiting_input = False

                # Run with or without spinner based on whether we're awaiting input
                response, agent_task = await run_prompt_with_attachments(
                    agent,
                    initial_command,
                    spinner_console=display_console,
                    use_spinner=not awaiting_input,
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
                get_prompt_with_active_model,
                prompt_for_submission,
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
                    get_prompt_with_active_model,
                    prompt_for_submission,
                )
            except Exception as e:
                from code_puppy.messaging import emit_error, emit_warning

                emit_error(f"Error installing prompt_toolkit: {e}")
                emit_warning("Falling back to basic input without tab completion")

        # Autosave loading is now manual - use /autosave_load command

        startup_oauth_command: str | None = None

        # Auto-run tutorial on first startup
        try:
            from code_puppy.command_line.onboarding_wizard import should_show_onboarding

            if should_show_onboarding():
                import concurrent.futures

                from code_puppy.command_line.onboarding_wizard import (
                    run_onboarding_wizard,
                )
                from code_puppy.messaging import emit_info

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(run_onboarding_wizard()))
                    result = future.result(timeout=300)

                if result == "chatgpt":
                    emit_info("🔐 Starting ChatGPT OAuth flow...")
                    startup_oauth_command = "/chatgpt-auth"
                elif result == "claude":
                    emit_info("🔐 Starting Claude Code OAuth flow...")
                    startup_oauth_command = "/claude-code-auth"
                elif result == "completed":
                    emit_info("🎉 Tutorial complete! Happy coding!")
                elif result == "skipped":
                    emit_info("⏭️ Tutorial skipped. Run /tutorial anytime!")
        except Exception as e:
            from code_puppy.messaging import emit_warning

            emit_warning(f"Tutorial auto-start failed: {e}")

        queue_start_lock = asyncio.Lock()
        shutdown_requested = False
        suppress_next_input_cancel_message = False
        active_cancel_state = {"reason": None}

        def stop_wiggum_with_notice(message: str) -> bool:
            nonlocal suppress_next_input_cancel_message
            from code_puppy.command_line.wiggum_state import (
                is_wiggum_active,
                stop_wiggum,
            )
            from code_puppy.messaging import emit_warning

            if not is_wiggum_active():
                return False
            stop_wiggum()
            suppress_next_input_cancel_message = True
            emit_warning(message)
            return True

        async def cancel_active_run(reason: str) -> None:
            """Aggressively stop shell + agent execution and wait for cancellation."""
            try:
                from code_puppy.tools.command_runner import (
                    get_running_shell_process_count,
                    kill_all_running_shell_processes,
                )
            except ImportError:
                get_running_shell_process_count = lambda: 0
                kill_all_running_shell_processes = lambda: None

            active_task = runtime.bg_task
            active_cancel_hook = runtime.active_cancel_hook

            if active_task is None or active_task.done():
                runtime.mark_idle_if_task(active_task)
                return

            runtime.cancelling = True
            active_cancel_state["reason"] = reason
            if is_manual_cancel_reason(reason):
                runtime.suppress_queue_autodrain()
            log_event("cancel_start", reason=reason)

            if active_cancel_hook is not None:
                try:
                    active_cancel_hook()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(asyncio.shield(active_task), timeout=1.5)
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                if active_task.done():
                    runtime.mark_idle_if_task(active_task)
                    log_event("cancel_done", reason=reason)
                    return

            # First kill nested shell activity, repeating briefly if needed.
            for _ in range(3):
                kill_all_running_shell_processes()
                if get_running_shell_process_count() == 0:
                    break
                await asyncio.sleep(0.15)

            # Then cancel the active background agent task and await completion.
            if active_task.done():
                runtime.mark_idle_if_task(active_task)
                log_event("cancel_done", reason=reason)
                return

            active_task.cancel()
            try:
                await asyncio.wait_for(active_task, timeout=6.0)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                pass
            except Exception:
                pass
            finally:
                runtime.mark_idle_if_task(active_task)
                log_event("cancel_done", reason=reason)
    except Exception:
        clear_active_interactive_runtime(runtime)
        raise

    async def shutdown_interactive_session(message: str, *, reason: str) -> None:
        """Exit interactive mode and cancel active work if needed."""
        nonlocal shutdown_requested
        from code_puppy.messaging import emit_info, emit_success

        shutdown_requested = True
        emit_success(message)
        if runtime.running and runtime.bg_task is not None and not runtime.bg_task.done():
            emit_info("Cancelling running task...")
            await cancel_active_run(reason)

    runtime.set_active_cancel_requester(
        lambda reason: asyncio.create_task(cancel_active_run(reason))
    )

    async def restore_autosave_state() -> None:
        """Handle the /autosave_load command."""
        try:
            # Check if we're in a real interactive terminal
            # (not pexpect/tests) - interactive picker requires proper TTY
            use_interactive_picker = sys.stdin.isatty() and sys.stdout.isatty()

            # Allow environment variable override for tests
            if os.getenv("CODE_PUPPY_NO_TUI") == "1":
                use_interactive_picker = False

            if use_interactive_picker:
                # Use interactive picker for terminal sessions
                from code_puppy.agents.agent_manager import get_current_agent
                from code_puppy.command_line.autosave_menu import (
                    interactive_autosave_picker,
                )
                from code_puppy.config import (
                    set_current_autosave_from_session_name,
                )
                from code_puppy.messaging import emit_error, emit_success, emit_warning
                from code_puppy.session_storage import (
                    load_session,
                    restore_autosave_interactively,
                )

                chosen_session = await interactive_autosave_picker()

                if not chosen_session:
                    emit_warning("Autosave load cancelled")
                    return

                # Load the session
                base_dir = Path(AUTOSAVE_DIR)
                history = load_session(chosen_session, base_dir)

                agent = get_current_agent()
                agent.set_message_history(history)

                # Set current autosave session
                set_current_autosave_from_session_name(chosen_session)

                total_tokens = sum(
                    agent.estimate_tokens_for_message(msg) for msg in history
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
                from code_puppy.session_storage import restore_autosave_interactively

                await restore_autosave_interactively(Path(AUTOSAVE_DIR))

        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(f"Failed to load autosave: {e}")

    async def clear_conversation_history() -> None:
        """Reset the current session history and clipboard attachments."""
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.command_line.clipboard import get_clipboard_manager
        from code_puppy.messaging import emit_info, emit_system_message, emit_warning

        agent = get_current_agent()
        new_session_id = finalize_autosave_session()
        agent.clear_message_history()
        emit_warning("Conversation history cleared!")
        emit_system_message("The agent will not remember previous interactions.")
        emit_info(f"Auto-save session rotated to: {new_session_id}")

        clipboard_manager = get_clipboard_manager()
        clipboard_count = clipboard_manager.get_pending_count()
        clipboard_manager.clear_pending()
        if clipboard_count > 0:
            emit_info(f"Cleared {clipboard_count} pending clipboard image(s)")

    def is_exit_text(text: str) -> bool:
        """Check if text should terminate interactive mode."""
        return text.strip().lower() in {"exit", "quit", "/exit", "/quit"}

    def is_manual_cancel_reason(reason: str) -> bool:
        """Return whether a cancel reason should pause queue autodrain."""
        return reason in {"ctrl_c", "ctrl+k", "ctrl+q"}

    def queue_level(item: QueuedPrompt) -> str:
        """Return the lifecycle level for a queued item."""
        return "warning" if item.kind == "interject" else "success"

    async def emit_queue_dispatch(item: QueuedPrompt) -> None:
        """Emit UI markers before a queued/interjected item is dispatched."""
        if item.kind == "queued":
            try:
                from code_puppy.command_line.prompt_toolkit_completion import (
                    render_transcript_notice,
                )
            except Exception:
                render_transcript_notice = None

            notice_text = f"[QUEUE TRIGGERED] {item.text.strip()}"
            if notice_text.strip() and render_transcript_notice is not None:
                if runtime.has_prompt_surface():
                    rendered = await runtime.run_above_prompt_async(
                        lambda: render_transcript_notice(notice_text)
                    )
                    if not rendered:
                        render_transcript_notice(notice_text)
                else:
                    render_transcript_notice(notice_text)
        emit_interject_queue_lifecycle(
            runtime,
            "dequeued",
            item=item,
            level=queue_level(item),
        )

    async def echo_dispatched_prompt(item: QueuedPrompt) -> None:
        """Echo queued/interjected prompts into the transcript before launch."""
        try:
            from code_puppy.command_line.prompt_toolkit_completion import (
                render_submitted_prompt_echo,
            )
        except Exception:
            return

        prompt_text = item.text.strip()
        if not prompt_text:
            return

        if runtime.has_prompt_surface():
            if await runtime.run_above_prompt_async(
                lambda: render_submitted_prompt_echo(prompt_text)
            ):
                return

        render_submitted_prompt_echo(prompt_text)

    async def echo_direct_prompt_if_needed(
        prompt_text: str, *, echo_in_transcript: bool
    ) -> None:
        """Echo direct submissions only when the prompt line was erased."""
        if not echo_in_transcript:
            return
        try:
            from code_puppy.command_line.prompt_toolkit_completion import (
                render_submitted_prompt_echo,
            )
        except Exception:
            return

        visible_text = prompt_text.strip()
        if not visible_text:
            return

        if runtime.has_prompt_surface():
            if await runtime.run_above_prompt_async(
                lambda: render_submitted_prompt_echo(visible_text)
            ):
                return

        render_submitted_prompt_echo(visible_text)

    def complete_queue_item(item: QueuedPrompt, reason: str) -> None:
        """Mark a queued item as handled without launching the agent."""
        emit_interject_queue_lifecycle(
            runtime,
            "completed",
            item=item,
            reason=reason,
            level=queue_level(item),
        )

    async def run_agent_bg(
        task_text, agent, source_item: QueuedPrompt | None = None
    ):
        try:
            log_event("agent_start", prompt=task_text)
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "started",
                    item=source_item,
                    level="warning" if source_item.kind == "interject" else "success",
                )
            result, _ = await run_prompt_with_attachments(
                agent,
                task_text,
                spinner_console=message_renderer.console,
            )
            if result is None:
                cancel_reason = active_cancel_state["reason"]
                reset_windows_terminal_ansi()
                try:
                    from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                    ensure_ctrl_c_disabled()
                except ImportError:
                    pass
                if cancel_reason != "interject" and stop_wiggum_with_notice(
                    "🍩 Wiggum loop stopped due to cancellation"
                ):
                    log_event("wiggum_stopped", reason="cancelled_active_run")
                if source_item:
                    emit_interject_queue_lifecycle(
                        runtime,
                        "cancelled",
                        item=source_item,
                        reason="run_cancelled",
                        level="warning",
                    )
                return
            agent_response = result.output

            from code_puppy.messaging import get_message_bus
            from code_puppy.messaging.messages import AgentResponseMessage

            response_msg = AgentResponseMessage(
                content=agent_response,
                is_markdown=True,
            )
            get_message_bus().emit(response_msg)

            if hasattr(result, "all_messages"):
                agent.set_message_history(list(result.all_messages()))

            if hasattr(display_console.file, "flush"):
                display_console.file.flush()

            await asyncio.sleep(0.1)
            from code_puppy.config import auto_save_session_if_enabled

            auto_save_session_if_enabled()
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "completed",
                    item=source_item,
                    level="success",
                )

        except Exception:
            from code_puppy.messaging.queue_console import get_queue_console

            get_queue_console().print_exception()
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "failed",
                    item=source_item,
                    reason="exception",
                    level="error",
                )
        finally:
            active_task = asyncio.current_task()
            owns_runtime = runtime.is_active_task(active_task)
            was_cancelling = runtime.cancelling if owns_runtime else False
            runtime.mark_idle_if_task(active_task)
            if owns_runtime:
                active_cancel_state["reason"] = None
            log_event("agent_end", prompt=task_text)
            if not owns_runtime:
                return
            if was_cancelling:
                if shutdown_requested:
                    log_event(
                        "queue_autodrain_skipped",
                        reason="shutdown_requested",
                        remaining=len(runtime.queue),
                    )
                    return
                if runtime.is_queue_autodrain_suppressed():
                    log_event(
                        "queue_autodrain_skipped",
                        reason="manual_cancel_pause",
                        remaining=len(runtime.queue),
                    )
                    return
                log_event(
                    "queue_autodrain_skipped",
                    reason="cancelling",
                    remaining=len(runtime.queue),
                )
                asyncio.create_task(
                    kick_drain_after_cancel_boundary(
                        origin="cancel_boundary_fallback",
                    )
                )
                return
            await drain_pending_work_if_idle(origin="run_complete")

    async def run_interactive_command_bg(
        command_result: BackgroundInteractiveCommand,
        command_text: str,
        *,
        source_item: QueuedPrompt | None = None,
    ) -> None:
        """Run a long-lived interactive command without blocking the composer."""
        try:
            log_event("interactive_command_start", command=command_text)
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "started",
                    item=source_item,
                    level="warning" if source_item.kind == "interject" else "success",
                )

            await asyncio.to_thread(command_result.run, command_result.cancel_event)

            if source_item and not command_result.cancel_event.is_set():
                emit_interject_queue_lifecycle(
                    runtime,
                    "completed",
                    item=source_item,
                    level="success",
                )
        except asyncio.CancelledError:
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "cancelled",
                    item=source_item,
                    reason="run_cancelled",
                    level="warning",
                )
        except Exception:
            from code_puppy.messaging.queue_console import get_queue_console

            get_queue_console().print_exception()
            if source_item:
                emit_interject_queue_lifecycle(
                    runtime,
                    "failed",
                    item=source_item,
                    reason="exception",
                    level="error",
                )
        finally:
            active_task = asyncio.current_task()
            owns_runtime = runtime.is_active_task(active_task)
            was_cancelling = runtime.cancelling if owns_runtime else False
            runtime.mark_idle_if_task(active_task)
            if owns_runtime:
                active_cancel_state["reason"] = None
            log_event("interactive_command_end", command=command_text)
            if not owns_runtime:
                return
            if was_cancelling:
                if shutdown_requested:
                    log_event(
                        "queue_autodrain_skipped",
                        reason="shutdown_requested",
                        remaining=len(runtime.queue),
                    )
                    return
                if runtime.is_queue_autodrain_suppressed():
                    log_event(
                        "queue_autodrain_skipped",
                        reason="manual_cancel_pause",
                        remaining=len(runtime.queue),
                    )
                    return
                log_event(
                    "queue_autodrain_skipped",
                    reason="cancelling",
                    remaining=len(runtime.queue),
                )
                asyncio.create_task(
                    kick_drain_after_cancel_boundary(
                        origin="cancel_boundary_fallback",
                    )
                )
                return
            await drain_pending_work_if_idle(origin="interactive_command_complete")

    async def dispatch_submission(
        task_text: str,
        *,
        requested_action: Literal["submit", "queue", "interject"] = "submit",
        source_item: QueuedPrompt | None = None,
        echo_in_transcript: bool = False,
        save_history: bool = True,
        allow_command_dispatch: bool = True,
    ) -> str:
        """Normalize a submitted prompt into exit, command handling, or agent work."""
        raw_task = task_text
        stripped_task = raw_task.strip()
        if not stripped_task:
            if source_item:
                complete_queue_item(source_item, "empty")
            return "noop"

        if source_item is None and is_exit_text(stripped_task):
            await shutdown_interactive_session("Goodbye!", reason="user_exit")
            return "exit"

        if source_item is None and requested_action in {"queue", "interject"}:
            from code_puppy.messaging import emit_warning

            save_command_to_history(raw_task)
            log_event("interject_choice", action=requested_action, prompt=stripped_task)

            if requested_action == "interject":
                log_event("interject_banner", text=stripped_task)
                await cancel_active_run("interject")
                ok, position, item = runtime.request_interject(
                    stripped_task,
                    allow_command_dispatch=allow_command_dispatch,
                )
                if not ok:
                    emit_warning("Queue full (25). Cannot interject right now.")
                    emit_interject_queue_lifecycle(
                        runtime,
                        "rejected",
                        reason="full_interject",
                        level="error",
                    )
                    log_event(
                        "queue_reject",
                        prompt=stripped_task,
                        reason="full_interject",
                    )
                    return "consumed"

                emit_interject_queue_lifecycle(
                    runtime,
                    "queued",
                    item=item,
                    position=position,
                    level="warning",
                )
                log_event(
                    "queued_interject",
                    text=stripped_task,
                    position=1,
                    size=len(runtime.queue),
                )
                handled = await drain_pending_work_if_idle(origin="interject_enqueued")
                log_event(
                    "interject_queue_kick_attempted",
                    remaining=len(runtime.queue),
                    running=runtime.running,
                    handled=handled,
                )
                return "consumed"

            ok, position, item = runtime.request_queue(
                stripped_task,
                allow_command_dispatch=allow_command_dispatch,
            )
            if not ok:
                emit_warning("Queue full (25). Prompt was not queued.")
                emit_interject_queue_lifecycle(
                    runtime,
                    "rejected",
                    reason="full",
                    level="error",
                )
                log_event("queue_reject", prompt=stripped_task, reason="full")
                return "consumed"

            emit_interject_queue_lifecycle(
                runtime,
                "queued",
                item=item,
                position=position,
                level="info",
            )
            log_event(
                "queued_prompt",
                text=stripped_task,
                position=position,
                size=len(runtime.queue),
            )
            await drain_pending_work_if_idle(origin="queue_enqueued")
            return "consumed"

        if source_item is None and runtime.running:
            log_event("busy_submission_ignored", prompt=stripped_task)
            return "consumed"

        if source_item:
            await emit_queue_dispatch(source_item)
            await echo_dispatched_prompt(source_item)
        else:
            await echo_direct_prompt_if_needed(
                raw_task,
                echo_in_transcript=echo_in_transcript,
            )

        if allow_command_dispatch and stripped_task.lower() in {"clear", "/clear"}:
            await clear_conversation_history()
            if source_item:
                complete_queue_item(source_item, "clear")
            return "consumed"

        candidate_task = raw_task
        if allow_command_dispatch:
            processed_for_commands = parse_prompt_attachments(raw_task)
            cleaned_for_commands = (processed_for_commands.prompt or "").strip()

            if source_item and is_exit_text(cleaned_for_commands or stripped_task):
                from code_puppy.messaging import emit_warning

                emit_warning("Skipping queued exit command. Use /exit directly.")
                complete_queue_item(source_item, "exit_skipped")
                return "consumed"

            if cleaned_for_commands.startswith("/"):
                try:
                    command_result = handle_command(cleaned_for_commands)
                except Exception as e:
                    from code_puppy.messaging import emit_error

                    emit_error(f"Command error: {e}")
                    if source_item:
                        complete_queue_item(source_item, "command_error")
                    return "consumed"

                if command_result is True:
                    if source_item:
                        complete_queue_item(source_item, "command_consumed")
                    return "consumed"

                if isinstance(command_result, str):
                    if command_result == "__AUTOSAVE_LOAD__":
                        await restore_autosave_state()
                        if source_item:
                            complete_queue_item(source_item, "autosave_load")
                        return "consumed"
                    candidate_task = command_result
                elif isinstance(command_result, BackgroundInteractiveCommand):
                    if save_history:
                        save_command_to_history(raw_task)
                    runtime.mark_running(
                        asyncio.create_task(
                            run_interactive_command_bg(
                                command_result,
                                cleaned_for_commands,
                                source_item=source_item,
                            )
                        ),
                        kind="interactive_command",
                        cancel_hook=command_result.request_cancel,
                    )
                    return "launched"

        candidate_task = candidate_task.strip()
        if not candidate_task:
            if source_item:
                complete_queue_item(source_item, "empty")
            return "noop"

        if save_history:
            save_command_to_history(raw_task)

        from code_puppy.agents.agent_manager import get_current_agent

        runtime.mark_running(
            asyncio.create_task(
                run_agent_bg(
                    candidate_task,
                    get_current_agent(),
                    source_item=source_item,
                )
            )
        )
        return "launched"

    async def dispatch_wiggum_if_idle() -> str:
        """Start the next wiggum loop iteration when no queued work exists."""
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_prompt,
            increment_wiggum_count,
            is_wiggum_active,
            stop_wiggum,
        )
        from code_puppy.messaging import emit_system_message, emit_warning

        if not is_wiggum_active():
            return "noop"

        wiggum_prompt = get_wiggum_prompt()
        if not wiggum_prompt:
            stop_wiggum()
            return "consumed"

        loop_num = increment_wiggum_count()
        emit_warning(f"\n🍩 WIGGUM RELOOPING! (Loop #{loop_num})")
        emit_system_message(f"Re-running prompt: {wiggum_prompt}")

        current_agent = get_current_agent()
        new_session_id = finalize_autosave_session()
        current_agent.clear_message_history()
        emit_system_message(f"Context cleared. Session rotated to: {new_session_id}")
        await asyncio.sleep(0.5)

        try:
            return await dispatch_submission(
                wiggum_prompt,
                save_history=False,
                allow_command_dispatch=False,
            )
        except KeyboardInterrupt:
            runtime.suppress_queue_autodrain()
            stop_wiggum_with_notice("\n🍩 Wiggum loop stopped!")
            return "consumed"
        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(f"Wiggum loop error: {e}")
            stop_wiggum()
            return "consumed"

    async def drain_pending_work_if_idle(*, origin: str) -> bool:
        """Single-flight idle drain for queued prompts and wiggum reruns."""
        handled_any = False

        async with queue_start_lock:
            while True:
                if runtime.has_pending_submission():
                    log_event(
                        "queue_autodrain_noop",
                        origin=origin,
                        reason="pending_submission",
                    )
                    return handled_any

                if runtime.is_queue_autodrain_suppressed():
                    log_event(
                        "queue_autodrain_noop",
                        origin=origin,
                        reason="manual_cancel_pause",
                    )
                    return handled_any

                if runtime.running:
                    active_task = runtime.bg_task
                    if active_task is None or active_task.done():
                        runtime.mark_idle()
                        log_event(
                            "queue_autodrain_reconciled",
                            origin=origin,
                            had_task=active_task is not None,
                            task_done=active_task.done() if active_task is not None else None,
                        )
                    else:
                        log_event("queue_autodrain_noop", origin=origin, reason="running")
                        return handled_any

                from code_puppy.command_line.wiggum_state import is_wiggum_active

                if is_wiggum_active():
                    next_item = runtime.dequeue_next_interject()
                    if next_item is not None:
                        outcome = await dispatch_submission(
                            _build_interject_submission_text(next_item.text),
                            source_item=next_item,
                            save_history=False,
                            allow_command_dispatch=next_item.allow_command_dispatch,
                        )
                        handled_any = True
                        if outcome == "launched":
                            log_event(
                                "queue_autodrain_triggered",
                                origin=origin,
                                remaining=len(runtime.queue),
                                kind=next_item.kind,
                                text=next_item.text,
                            )
                            return True
                        continue

                    outcome = await dispatch_wiggum_if_idle()
                    if outcome == "launched":
                        log_event("queue_autodrain_triggered", origin=origin, kind="wiggum")
                        return True
                    if outcome == "consumed":
                        log_event("queue_autodrain_consumed", origin=origin, kind="wiggum")
                        return True

                    log_event("queue_autodrain_noop", origin=origin, reason="wiggum_idle")
                    return handled_any

                next_item = runtime.dequeue()
                if next_item is not None:
                    outcome = await dispatch_submission(
                        next_item.text
                        if next_item.kind == "queued"
                        else _build_interject_submission_text(next_item.text),
                        source_item=next_item,
                        save_history=False,
                        allow_command_dispatch=next_item.allow_command_dispatch,
                    )
                    handled_any = True
                    if outcome == "launched":
                        log_event(
                            "queue_autodrain_triggered",
                            origin=origin,
                            remaining=len(runtime.queue),
                            kind=next_item.kind,
                            text=next_item.text,
                        )
                        return True
                    continue

                outcome = await dispatch_wiggum_if_idle()
                if outcome == "launched":
                    log_event("queue_autodrain_triggered", origin=origin, kind="wiggum")
                    return True
                if outcome == "consumed":
                    log_event("queue_autodrain_consumed", origin=origin, kind="wiggum")
                    return True

                log_event("queue_autodrain_noop", origin=origin, reason="empty")
                return handled_any

    async def kick_drain_after_cancel_boundary(*, origin: str) -> bool:
        """Yield once before draining, so cancellation state fully settles."""
        await asyncio.sleep(0)
        return await drain_pending_work_if_idle(origin=origin)

    if startup_oauth_command:
        startup_outcome = await dispatch_submission(
            startup_oauth_command,
            save_history=False,
            allow_command_dispatch=True,
        )
        if startup_outcome == "exit":
            clear_active_interactive_runtime(runtime)
            return

    while True:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent()
        user_prompt = current_agent.get_user_prompt() or "Enter your coding task:"
        if not runtime.running:
            handled = await drain_pending_work_if_idle(origin="loop_idle_check")
            if handled:
                continue

        if not runtime.running and not runtime.has_pending_submission():
            emit_info(f"{user_prompt}\n")

        try:
            # Use prompt_toolkit for enhanced input with path completion
            try:
                # Windows-specific: Reset terminal state before prompting
                reset_windows_terminal_ansi()

                submission = await prompt_for_submission(
                    get_prompt_with_active_model,
                    history_file=COMMAND_HISTORY_FILE,
                    erase_when_done=runtime.running,
                )
                log_event(
                    "input_received",
                    action=submission.action,
                    text=submission.text,
                )
                if submission.text.strip():
                    suppress_next_input_cancel_message = False

                # Windows+uvx: Re-disable Ctrl+C after prompt_toolkit
                # (prompt_toolkit restores console mode which re-enables Ctrl+C)
                try:
                    from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                    ensure_ctrl_c_disabled()
                except ImportError:
                    pass
            except ImportError:
                # Fall back to basic input if prompt_toolkit is not available
                from code_puppy.command_line.prompt_toolkit_completion import (
                    PromptSubmission,
                )

                submission = PromptSubmission(action="submit", text=input(">>> "))

        except KeyboardInterrupt:
            # Handle Ctrl+C - cancel input and continue
            # Windows-specific: Reset terminal state after interrupt to prevent
            # the terminal from becoming unresponsive (can't type characters)
            reset_windows_terminal_full()
            # Stop wiggum mode on Ctrl+C
            from code_puppy.command_line.wiggum_state import (
                is_wiggum_active,
                stop_wiggum,
            )
            from code_puppy.messaging import emit_warning

            if stop_wiggum_with_notice("\n🍩 Wiggum loop stopped!"):
                runtime.suppress_queue_autodrain()
                continue
            if suppress_next_input_cancel_message:
                suppress_next_input_cancel_message = False
            else:
                emit_warning("\nInput cancelled")
            continue
        except EOFError:
            # Handle Ctrl+D - exit the application
            await shutdown_interactive_session("\nGoodbye! (Ctrl+D)", reason="ctrl_d")
            break

        # Shell pass-through: !<command> executes directly, bypassing the agent.
        from code_puppy.command_line.shell_passthrough import (
            execute_shell_passthrough,
            is_shell_passthrough,
        )

        if is_shell_passthrough(submission.text):
            if submission.text.strip():
                runtime.clear_queue_autodrain_suppression()
            execute_shell_passthrough(submission.text)
            continue

        if submission.text.strip() and runtime.is_queue_autodrain_suppressed():
            runtime.clear_queue_autodrain_suppression()
            log_event(
                "queue_autodrain_resumed",
                reason="explicit_submission",
                text=submission.text.strip(),
            )

        outcome = await dispatch_submission(
            submission.text,
            requested_action=submission.action,
            echo_in_transcript=submission.echo_in_transcript,
            allow_command_dispatch=submission.allow_command_dispatch,
        )
        if outcome == "exit":
            break
        if outcome == "launched":
            await asyncio.sleep(0)
    clear_active_interactive_runtime(runtime)


async def run_prompt_with_attachments(
    agent,
    raw_prompt: str,
    *,
    spinner_console=None,
    use_spinner: bool = True,
):
    """Run the agent after parsing CLI attachments for image/document support.

    Returns:
        tuple: (result, task) where result is the agent response and task is the asyncio task
    """
    import asyncio
    import re

    from code_puppy.messaging import emit_system_message, emit_warning
    from code_puppy.command_line.interactive_runtime import (
        get_active_interactive_runtime,
    )

    processed_prompt = parse_prompt_attachments(raw_prompt)

    for warning in processed_prompt.warnings:
        emit_warning(warning)

    # Get clipboard images and merge with file attachments
    clipboard_manager = get_clipboard_manager()
    clipboard_images = clipboard_manager.get_pending_images()

    # Clear pending clipboard images after retrieval
    clipboard_manager.clear_pending()

    # Build summary of all attachments
    summary_parts = []
    if processed_prompt.attachments:
        summary_parts.append(f"files: {len(processed_prompt.attachments)}")
    if clipboard_images:
        summary_parts.append(f"clipboard images: {len(clipboard_images)}")
    if processed_prompt.link_attachments:
        summary_parts.append(f"urls: {len(processed_prompt.link_attachments)}")
    if summary_parts:
        emit_system_message("Attachments detected -> " + ", ".join(summary_parts))

    # Clean up clipboard placeholders from the prompt text
    cleaned_prompt = processed_prompt.prompt
    if clipboard_images and cleaned_prompt:
        cleaned_prompt = re.sub(
            r"\[📋 clipboard image \d+\]\s*", "", cleaned_prompt
        ).strip()

    if not cleaned_prompt:
        emit_warning(
            "Prompt is empty after removing attachments; add instructions and retry."
        )
        return None, None

    # Combine file attachments with clipboard images
    attachments = [attachment.content for attachment in processed_prompt.attachments]
    attachments.extend(clipboard_images)  # Add clipboard images

    link_attachments = [link.url_part for link in processed_prompt.link_attachments]

    # IMPORTANT: Set the shared console for streaming output so it
    # uses the same console as the spinner. This prevents Live display conflicts
    # that cause line duplication during markdown streaming.
    from code_puppy.agents.event_stream_handler import set_streaming_console

    set_streaming_console(spinner_console)
    _seed_spinner_context(
        agent,
        cleaned_prompt,
        link_attachments=link_attachments,
    )

    # Create the agent task first so we can track and cancel it
    agent_task = asyncio.create_task(
        agent.run_with_mcp(
            cleaned_prompt,  # Use cleaned prompt (clipboard placeholders removed)
            attachments=attachments,
            link_attachments=link_attachments,
        )
    )

    runtime = get_active_interactive_runtime()
    spinner_allowed = not (runtime is not None and runtime.running)

    if use_spinner and spinner_console is not None and spinner_allowed:
        from code_puppy.messaging.spinner import ConsoleSpinner

        with ConsoleSpinner(console=spinner_console):
            try:
                result = await agent_task
                return result, agent_task
            except asyncio.CancelledError:
                emit_info("Agent task cancelled")
                return None, agent_task
    else:
        try:
            result = await agent_task
            return result, agent_task
        except asyncio.CancelledError:
            emit_info("Agent task cancelled")
            return None, agent_task


async def execute_single_prompt(prompt: str, message_renderer) -> None:
    """Execute a single prompt and exit (for -p flag)."""
    from code_puppy.messaging import emit_info

    emit_info(f"Executing prompt: {prompt}")

    from code_puppy.command_line.shell_passthrough import (
        execute_shell_passthrough,
        is_shell_passthrough,
    )

    if is_shell_passthrough(prompt):
        execute_shell_passthrough(prompt)
        return

    try:
        # Get agent through runtime manager and use helper for attachments
        agent = get_current_agent()
        response = await run_prompt_with_attachments(
            agent,
            prompt,
            spinner_console=message_renderer.console,
        )
        if response is None:
            return

        agent_response = response.output

        # Emit structured message for proper markdown rendering
        from code_puppy.messaging import get_message_bus
        from code_puppy.messaging.messages import AgentResponseMessage

        response_msg = AgentResponseMessage(
            content=agent_response,
            is_markdown=True,
        )
        get_message_bus().emit(response_msg)

    except asyncio.CancelledError:
        from code_puppy.messaging import emit_warning

        emit_warning("Execution cancelled by user")
    except Exception as e:
        from code_puppy.messaging import emit_error

        emit_error(f"Error executing prompt: {str(e)}")


def main_entry():
    """Entry point for the installed CLI tool."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Note: Using sys.stderr for crash output - messaging system may not be available
        sys.stderr.write(traceback.format_exc())
        if get_use_dbos():
            DBOS.destroy()
        return 0
    finally:
        # Reset terminal on Unix-like systems (not Windows)
        reset_unix_terminal()
