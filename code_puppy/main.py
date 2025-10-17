import argparse
import asyncio
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from dbos import DBOS, DBOSConfig
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy import __version__, callbacks, plugins
from code_puppy.agents import get_current_agent
from code_puppy.command_line.prompt_toolkit_completion import (
    get_input_with_combined_completion,
    get_prompt_with_active_model,
)
from code_puppy.command_line.attachments import parse_prompt_attachments
from code_puppy.config import (
    AUTOSAVE_DIR,
    COMMAND_HISTORY_FILE,
    DBOS_DATABASE_URL,
    get_use_dbos,
    ensure_config_exists,
    finalize_autosave_session,
    initialize_command_history_file,
    save_command_to_history,
)
from code_puppy.session_storage import restore_autosave_interactively
from code_puppy.http_utils import find_available_port
from code_puppy.tools.common import console

# message_history_accumulator and prune_interrupted_tool_calls have been moved to BaseAgent class
from code_puppy.tui_state import is_tui_mode, set_tui_mode
from code_puppy.version_checker import default_version_mismatch_behavior

plugins.load_plugin_callbacks()


async def main():
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
    parser.add_argument("--tui", "-t", action="store_true", help="Run in TUI mode")
    parser.add_argument(
        "--web",
        "-w",
        action="store_true",
        help="Run in web mode (serves TUI in browser)",
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
        "command", nargs="*", help="Run a single command (deprecated, use -p instead)"
    )
    args = parser.parse_args()

    if args.tui or args.web:
        set_tui_mode(True)
    elif args.interactive or args.command or args.prompt:
        set_tui_mode(False)

    message_renderer = None
    if not is_tui_mode():
        from rich.console import Console

        from code_puppy.messaging import (
            SynchronousInteractiveRenderer,
            get_global_queue,
        )

        message_queue = get_global_queue()
        display_console = Console()  # Separate console for rendering messages
        message_renderer = SynchronousInteractiveRenderer(
            message_queue, display_console
        )
        message_renderer.start()

    if (
        not args.tui
        and not args.interactive
        and not args.web
        and not args.command
        and not args.prompt
    ):
        pass

    initialize_command_history_file()
    if args.web:
        from rich.console import Console

        direct_console = Console()
        try:
            # Find an available port for the web server
            available_port = find_available_port()
            if available_port is None:
                direct_console.print(
                    "[bold red]Error:[/bold red] No available ports in range 8090-9010!"
                )
                sys.exit(1)
            python_executable = sys.executable
            serve_command = f"{python_executable} -m code_puppy --tui"
            textual_serve_cmd = [
                "textual",
                "serve",
                "-c",
                serve_command,
                "--port",
                str(available_port),
            ]
            direct_console.print(
                "[bold blue]🌐 Starting Code Puppy web interface...[/bold blue]"
            )
            direct_console.print(f"[dim]Running: {' '.join(textual_serve_cmd)}[/dim]")
            web_url = f"http://localhost:{available_port}"
            direct_console.print(
                f"[green]Web interface will be available at: {web_url}[/green]"
            )
            direct_console.print("[yellow]Press Ctrl+C to stop the server.[/yellow]\n")
            process = subprocess.Popen(textual_serve_cmd)
            time.sleep(0.3)
            try:
                direct_console.print(
                    "[cyan]🚀 Opening web interface in your default browser...[/cyan]"
                )
                webbrowser.open(web_url)
                direct_console.print("[green]✅ Browser opened successfully![/green]\n")
            except Exception as e:
                direct_console.print(
                    f"[yellow]⚠️  Could not automatically open browser: {e}[/yellow]"
                )
                direct_console.print(
                    f"[yellow]Please manually open: {web_url}[/yellow]\n"
                )
            result = process.wait()
            sys.exit(result)
        except Exception as e:
            direct_console.print(
                f"[bold red]Error starting web interface:[/bold red] {str(e)}"
            )
            sys.exit(1)
    from code_puppy.messaging import emit_system_message

    emit_system_message("🐶 Code Puppy is Loading...")

    available_port = find_available_port()
    if available_port is None:
        error_msg = "Error: No available ports in range 8090-9010!"
        emit_system_message(f"[bold red]{error_msg}[/bold red]")
        return

    ensure_config_exists()

    # Handle agent selection from command line
    if args.agent:
        from code_puppy.agents.agent_manager import (
            set_current_agent,
            get_available_agents,
        )

        agent_name = args.agent.lower()
        try:
            # First check if the agent exists by getting available agents
            available_agents = get_available_agents()
            if agent_name not in available_agents:
                emit_system_message(
                    f"[bold red]Error:[/bold red] Agent '{agent_name}' not found"
                )
                emit_system_message(
                    f"Available agents: {', '.join(available_agents.keys())}"
                )
                sys.exit(1)

            # Agent exists, set it
            set_current_agent(agent_name)
            emit_system_message(f"🤖 Using agent: {agent_name}")
        except Exception as e:
            emit_system_message(f"[bold red]Error setting agent:[/bold red] {str(e)}")
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
        emit_system_message(f"[dim]{update_disabled_msg}[/dim]")
    else:
        if len(callbacks.get_callbacks("version_check")):
            await callbacks.on_version_check(current_version)
        else:
            default_version_mismatch_behavior(current_version)

    await callbacks.on_startup()

    # Initialize DBOS if not disabled
    if get_use_dbos():
        dbos_message = f"Initializing DBOS with database at: {DBOS_DATABASE_URL}"
        emit_system_message(dbos_message)

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
            "application_version": current_version,  # Match DBOS app version to Code Puppy version
        }
        try:
            DBOS(config=dbos_config)
            DBOS.launch()
        except Exception as e:
            emit_system_message(f"[bold red]Error initializing DBOS:[/bold red] {e}")
            sys.exit(1)
    else:
        emit_system_message("DBOS is disabled. Running without durable execution.")

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
        elif is_tui_mode():
            try:
                from code_puppy.tui import run_textual_ui

                await run_textual_ui(initial_command=initial_command)
            except ImportError:
                from code_puppy.messaging import emit_error, emit_warning

                emit_error(
                    "Error: Textual UI not available. Install with: pip install textual"
                )
                emit_warning("Falling back to interactive mode...")
                await interactive_mode(message_renderer)
            except Exception as e:
                from code_puppy.messaging import emit_error, emit_warning

                emit_error(f"TUI Error: {str(e)}")
                emit_warning("Falling back to interactive mode...")
                await interactive_mode(message_renderer)
        elif args.interactive or initial_command:
            await interactive_mode(message_renderer, initial_command=initial_command)
        else:
            await prompt_then_interactive_mode(message_renderer)
    finally:
        if message_renderer:
            message_renderer.stop()
        await callbacks.on_shutdown()
        if get_use_dbos():
            DBOS.destroy()


# Add the file handling functionality for interactive mode
async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    from code_puppy.command_line.command_handler import handle_command

    """Run the agent in interactive mode."""

    display_console = message_renderer.console
    from code_puppy.messaging import emit_info, emit_system_message

    emit_info("[bold green]Code Puppy[/bold green] - Interactive Mode")
    emit_system_message("Type '/exit' or '/quit' to exit the interactive mode.")
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message("[dim]Type /help to view all commands[/dim]")
    emit_system_message(
        "Type [bold blue]@[/bold blue] for path completion, or [bold blue]/m[/bold blue] to pick a model. Toggle multiline with [bold blue]Alt+M[/bold blue] or [bold blue]F2[/bold blue]; newline: [bold blue]Ctrl+J[/bold blue]."
    )
    emit_system_message(
        "Press [bold red]Ctrl+C[/bold red] during processing to cancel the current task or inference."
    )
    try:
        from code_puppy.command_line.motd import print_motd

        print_motd(console, force=False)
    except Exception as e:
        from code_puppy.messaging import emit_warning

        emit_warning(f"MOTD error: {e}")
    from code_puppy.messaging import emit_info

    emit_info("[bold cyan]Initializing agent...[/bold cyan]")

    # Initialize the runtime agent manager
    if initial_command:
        from code_puppy.agents import get_current_agent
        from code_puppy.messaging import emit_info, emit_system_message

        agent = get_current_agent()
        emit_info(
            f"[bold blue]Processing initial command:[/bold blue] {initial_command}"
        )

        try:
            # Check if any tool is waiting for user input before showing spinner
            try:
                from code_puppy.tools.command_runner import is_awaiting_user_input

                awaiting_input = is_awaiting_user_input()
            except ImportError:
                awaiting_input = False

            # Run with or without spinner based on whether we're awaiting input
            response = await run_prompt_with_attachments(
                agent,
                initial_command,
                spinner_console=display_console,
                use_spinner=not awaiting_input,
            )
            if response is not None:
                agent_response = response.output

                emit_system_message(
                    f"\n[bold purple]AGENT RESPONSE: [/bold purple]\n{agent_response}"
                )
                emit_system_message("\n" + "=" * 50)
                emit_info("[bold green]🐶 Continuing in Interactive Mode[/bold green]")
                emit_system_message(
                    "Your command and response are preserved in the conversation history."
                )
                emit_system_message("=" * 50 + "\n")

        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(f"Error processing initial command: {str(e)}")

    # Check if prompt_toolkit is installed
    try:
        from code_puppy.messaging import emit_system_message

        emit_system_message(
            "[dim]Using prompt_toolkit for enhanced tab completion[/dim]"
        )
    except ImportError:
        from code_puppy.messaging import emit_warning

        emit_warning("Warning: prompt_toolkit not installed. Installing now...")
        try:
            import subprocess

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "prompt_toolkit"]
            )
            from code_puppy.messaging import emit_success

            emit_success("Successfully installed prompt_toolkit")
        except Exception as e:
            from code_puppy.messaging import emit_error, emit_warning

            emit_error(f"Error installing prompt_toolkit: {e}")
            emit_warning("Falling back to basic input without tab completion")

    await restore_autosave_interactively(Path(AUTOSAVE_DIR))

    while True:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent()
        user_prompt = current_agent.get_user_prompt() or "Enter your coding task:"

        emit_info(f"[bold blue]{user_prompt}[/bold blue]")

        try:
            # Use prompt_toolkit for enhanced input with path completion
            try:
                # Use the async version of get_input_with_combined_completion
                task = await get_input_with_combined_completion(
                    get_prompt_with_active_model(), history_file=COMMAND_HISTORY_FILE
                )
            except ImportError:
                # Fall back to basic input if prompt_toolkit is not available
                task = input(">>> ")

        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D
            from code_puppy.messaging import emit_warning

            emit_warning("\nInput cancelled")
            continue

        # Check for exit commands (plain text or command form)
        if task.strip().lower() in ["exit", "quit"] or task.strip().lower() in [
            "/exit",
            "/quit",
        ]:
            from code_puppy.messaging import emit_success

            emit_success("Goodbye!")
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
            emit_system_message("The agent will not remember previous interactions.\n")
            emit_info(f"[dim]Auto-save session rotated to: {new_session_id}[/dim]")
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
                result = await run_prompt_with_attachments(
                    current_agent,
                    task,
                    spinner_console=message_renderer.console,
                )
                # Check if the task was cancelled (but don't show message if we just killed processes)
                if result is None:
                    continue
                # Get the structured response
                agent_response = result.output
                from code_puppy.messaging import emit_info

                emit_system_message(
                    f"\n[bold purple]AGENT RESPONSE: [/bold purple]\n{agent_response}"
                )

                # Auto-save session if enabled
                from code_puppy.config import auto_save_session_if_enabled

                auto_save_session_if_enabled()

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


def prettier_code_blocks():
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
    """Run the agent after parsing CLI attachments for image/document support."""
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
        emit_system_message(
            "[dim]Attachments detected -> " + ", ".join(summary_parts) + "[/dim]"
        )

    if not processed_prompt.prompt:
        emit_warning(
            "Prompt is empty after removing attachments; add instructions and retry."
        )
        return None

    attachments = [attachment.content for attachment in processed_prompt.attachments]
    link_attachments = [link.url_part for link in processed_prompt.link_attachments]

    if use_spinner and spinner_console is not None:
        from code_puppy.messaging.spinner import ConsoleSpinner

        with ConsoleSpinner(console=spinner_console):
            return await agent.run_with_mcp(
                processed_prompt.prompt,
                attachments=attachments,
                link_attachments=link_attachments,
            )

    return await agent.run_with_mcp(
        processed_prompt.prompt,
        attachments=attachments,
        link_attachments=link_attachments,
    )


async def execute_single_prompt(prompt: str, message_renderer) -> None:
    """Execute a single prompt and exit (for -p flag)."""
    from code_puppy.messaging import emit_info, emit_system_message

    emit_info(f"[bold blue]Executing prompt:[/bold blue] {prompt}")

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
        emit_system_message(
            f"\n[bold purple]AGENT RESPONSE: [/bold purple]\n{agent_response}"
        )

    except asyncio.CancelledError:
        from code_puppy.messaging import emit_warning

        emit_warning("Execution cancelled by user")
    except Exception as e:
        from code_puppy.messaging import emit_error

        emit_error(f"Error executing prompt: {str(e)}")


async def prompt_then_interactive_mode(message_renderer) -> None:
    """Prompt user for input, execute it, then continue in interactive mode."""
    from code_puppy.messaging import emit_info, emit_system_message

    emit_info("[bold green]🐶 Code Puppy[/bold green] - Enter your request")
    emit_system_message(
        "After processing your request, you'll continue in interactive mode."
    )

    try:
        # Get user input
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
            get_prompt_with_active_model,
        )
        from code_puppy.config import COMMAND_HISTORY_FILE

        emit_info("[bold blue]What would you like me to help you with?[/bold blue]")

        try:
            # Use prompt_toolkit for enhanced input with path completion
            user_prompt = await get_input_with_combined_completion(
                get_prompt_with_active_model(), history_file=COMMAND_HISTORY_FILE
            )
        except ImportError:
            # Fall back to basic input if prompt_toolkit is not available
            user_prompt = input(">>> ")

        if user_prompt.strip():
            # Execute the prompt
            await execute_single_prompt(user_prompt, message_renderer)

            # Transition to interactive mode
            emit_system_message("\n" + "=" * 50)
            emit_info("[bold green]🐶 Continuing in Interactive Mode[/bold green]")
            emit_system_message(
                "Your request and response are preserved in the conversation history."
            )
            emit_system_message("=" * 50 + "\n")

            # Continue in interactive mode with the initial command as history
            await interactive_mode(message_renderer, initial_command=user_prompt)
        else:
            # No input provided, just go to interactive mode
            await interactive_mode(message_renderer)

    except (KeyboardInterrupt, EOFError):
        from code_puppy.messaging import emit_warning

        emit_warning("\nInput cancelled. Starting interactive mode...")
        await interactive_mode(message_renderer)
    except Exception as e:
        from code_puppy.messaging import emit_error

        emit_error(f"Error in prompt mode: {str(e)}")
        emit_info("Falling back to interactive mode...")
        await interactive_mode(message_renderer)


def main_entry():
    """Entry point for the installed CLI tool."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Just exit gracefully with no error message
        callbacks.on_shutdown()
        if get_use_dbos():
            DBOS.destroy()
        return 0


if __name__ == "__main__":
    main_entry()
