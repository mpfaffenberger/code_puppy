"""CLI runner for Code Puppy.

Contains the main application logic, interactive mode, and entry point.
"""

# Apply pydantic-ai patches BEFORE any pydantic-ai imports
from code_puppy.pydantic_patches import apply_all_patches

apply_all_patches()

import argparse
import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

from dbos import DBOS, DBOSConfig
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy import __version__, callbacks, plugins
from code_puppy.agents import get_current_agent
from code_puppy.command_line.attachments import parse_prompt_attachments
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
    reset_unix_terminal,
    reset_windows_terminal_ansi,
    reset_windows_terminal_full,
)
from code_puppy.tools.common import console
from code_puppy.version_checker import default_version_mismatch_behavior

plugins.load_plugin_callbacks()


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
        "command", nargs="*", help="Run a single command (deprecated, use -p instead)"
    )
    args = parser.parse_args()
    from rich.console import Console

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
            await execute_single_prompt(initial_command, message_renderer)
        else:
            # Default to interactive mode (no args = same as -i)
            await interactive_mode(message_renderer, initial_command=initial_command)
    finally:
        if message_renderer:
            message_renderer.stop()
        if bus_renderer:
            bus_renderer.stop()
        await callbacks.on_shutdown()
        if get_use_dbos():
            DBOS.destroy()


async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    """Run the agent in interactive mode."""
    from code_puppy.command_line.command_handler import handle_command

    display_console = message_renderer.console
    from code_puppy.messaging import emit_info, emit_system_message

    emit_system_message("Type '/exit' or '/quit' to exit the interactive mode.")
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message("Type /help to view all commands")
    emit_system_message(
        "Type @ for path completion, or /model to pick a model. Toggle multiline with Alt+M or F2; newline: Ctrl+J."
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
    try:
        from code_puppy.command_line.motd import print_motd

        print_motd(console, force=False)
    except Exception as e:
        from code_puppy.messaging import emit_warning

        emit_warning(f"MOTD error: {e}")

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

    # Track the current agent task for cancellation on quit
    current_agent_task = None

    while True:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent()
        user_prompt = current_agent.get_user_prompt() or "Enter your coding task:"

        emit_info(f"{user_prompt}\n")

        try:
            # Use prompt_toolkit for enhanced input with path completion
            try:
                # Windows-specific: Reset terminal state before prompting
                reset_windows_terminal_ansi()

                # Use the async version of get_input_with_combined_completion
                task = await get_input_with_combined_completion(
                    get_prompt_with_active_model(), history_file=COMMAND_HISTORY_FILE
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

        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D
            # Windows-specific: Reset terminal state after interrupt to prevent
            # the terminal from becoming unresponsive (can't type characters)
            reset_windows_terminal_full()
            from code_puppy.messaging import emit_warning

            emit_warning("\nInput cancelled")
            continue

        # Check for exit commands (plain text or command form)
        if task.strip().lower() in ["exit", "quit"] or task.strip().lower() in [
            "/exit",
            "/quit",
        ]:
            import asyncio

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

        # Check for clear command (supports both `clear` and `/clear`)
        if task.strip().lower() in ("clear", "/clear"):
            from code_puppy.messaging import (
                emit_info,
                emit_system_message,
                emit_warning,
            )

            agent = get_current_agent()
            new_session_id = finalize_autosave_session()
            agent.clear_message_history()
            emit_warning("Conversation history cleared!")
            emit_system_message("The agent will not remember previous interactions.")
            emit_info(f"Auto-save session rotated to: {new_session_id}")
            continue

        # Parse attachments first so leading paths aren't misread as commands
        processed_for_commands = parse_prompt_attachments(task)
        cleaned_for_commands = (processed_for_commands.prompt or "").strip()

        # Handle / commands based on cleaned prompt (after stripping attachments)
        if cleaned_for_commands.startswith("/"):
            try:
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
                                set_current_autosave_from_session_name,
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
                            set_current_autosave_from_session_name(chosen_session)

                            total_tokens = sum(
                                agent.estimate_tokens_for_message(msg)
                                for msg in history
                            )
                            session_path = base_dir / f"{chosen_session}.pkl"

                            emit_success(
                                f"✅ Autosave loaded: {len(history)} messages ({total_tokens} tokens)\n"
                                f"📁 From: {session_path}"
                            )
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

            try:
                prettier_code_blocks()

                # No need to get agent directly - use manager's run methods

                # Use our custom helper to enable attachment handling with spinner support
                result, current_agent_task = await run_prompt_with_attachments(
                    current_agent,
                    task,
                    spinner_console=message_renderer.console,
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

                # Ensure console output is flushed before next prompt
                # This fixes the issue where prompt doesn't appear after agent response
                display_console.file.flush() if hasattr(
                    display_console.file, "flush"
                ) else None
                import time

                time.sleep(0.1)  # Brief pause to ensure all messages are rendered

            except Exception:
                from code_puppy.messaging.queue_console import get_queue_console

                get_queue_console().print_exception()

            # Auto-save session if enabled (moved outside the try block to avoid being swallowed)
            from code_puppy.config import auto_save_session_if_enabled

            auto_save_session_if_enabled()

            # Re-disable Ctrl+C if needed (uvx mode) - must be done after
            # each iteration as various operations may restore console mode
            try:
                from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                ensure_ctrl_c_disabled()
            except ImportError:
                pass


def prettier_code_blocks():
    """Configure Rich to use prettier code block rendering."""

    class SimpleCodeBlock(CodeBlock):
        def __rich_console__(
            self, console: Console, options: ConsoleOptions
        ) -> RenderResult:
            code = str(self.text).rstrip()
            yield Text(self.lexer_name, style="dim")
            syntax = Syntax(
                code,
                self.lexer_name,
                theme=self.theme,
                background_color="default",
                line_numbers=True,
            )
            yield syntax
            yield Text(f"/{self.lexer_name}", style="dim")

    Markdown.elements["fence"] = SimpleCodeBlock


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

    from code_puppy.messaging import emit_system_message, emit_warning

    processed_prompt = parse_prompt_attachments(raw_prompt)

    for warning in processed_prompt.warnings:
        emit_warning(warning)

    summary_parts = []
    if processed_prompt.attachments:
        summary_parts.append(f"binary files: {len(processed_prompt.attachments)}")
    if processed_prompt.link_attachments:
        summary_parts.append(f"urls: {len(processed_prompt.link_attachments)}")
    if summary_parts:
        emit_system_message("Attachments detected -> " + ", ".join(summary_parts))

    if not processed_prompt.prompt:
        emit_warning(
            "Prompt is empty after removing attachments; add instructions and retry."
        )
        return None, None

    attachments = [attachment.content for attachment in processed_prompt.attachments]
    link_attachments = [link.url_part for link in processed_prompt.link_attachments]

    # IMPORTANT: Set the shared console on the agent so that streaming output
    # uses the same console as the spinner. This prevents Live display conflicts
    # that cause line duplication during markdown streaming.
    if spinner_console is not None:
        agent._console = spinner_console

    # Create the agent task first so we can track and cancel it
    agent_task = asyncio.create_task(
        agent.run_with_mcp(
            processed_prompt.prompt,
            attachments=attachments,
            link_attachments=link_attachments,
        )
    )

    if use_spinner and spinner_console is not None:
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
