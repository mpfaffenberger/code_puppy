import argparse
import asyncio
import os
import subprocess
import sys
import time
import webbrowser

from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy import __version__, callbacks, plugins
from code_puppy.agent import get_custom_usage_limits
from code_puppy.agents.runtime_manager import get_runtime_agent_manager
from code_puppy.command_line.prompt_toolkit_completion import (
    get_input_with_combined_completion,
    get_prompt_with_active_model,
)
from code_puppy.config import (
    COMMAND_HISTORY_FILE,
    ensure_config_exists,
    initialize_command_history_file,
    save_command_to_history,
)
from code_puppy.http_utils import find_available_port
from code_puppy.message_history_processor import (
    message_history_accumulator,
    prune_interrupted_tool_calls,
)
from code_puppy.state_management import is_tui_mode, set_message_history, set_tui_mode
from code_puppy.tools.common import console
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


# Add the file handling functionality for interactive mode
async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    from code_puppy.command_line.command_handler import handle_command

    """Run the agent in interactive mode."""
    from code_puppy.state_management import clear_message_history, get_message_history

    clear_message_history()
    display_console = message_renderer.console
    from code_puppy.messaging import emit_info, emit_system_message

    emit_info("[bold green]Code Puppy[/bold green] - Interactive Mode")
    emit_system_message("Type '/exit' or '/quit' to exit the interactive mode.")
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message(
        "Type [bold blue]@[/bold blue] for path completion, or [bold blue]/m[/bold blue] to pick a model. Use [bold blue]Esc+Enter[/bold blue] for multi-line input."
    )
    emit_system_message(
        "Press [bold red]Ctrl+C[/bold red] during processing to cancel the current task or inference."
    )
    from code_puppy.command_line.command_handler import get_commands_help

    help_text = get_commands_help()
    emit_system_message(help_text)
    try:
        from code_puppy.command_line.motd import print_motd

        print_motd(console, force=False)
    except Exception as e:
        from code_puppy.messaging import emit_warning

        emit_warning(f"MOTD error: {e}")
    from code_puppy.agents.runtime_manager import get_runtime_agent_manager
    from code_puppy.messaging import emit_info

    emit_info("[bold cyan]Initializing agent...[/bold cyan]")
    # Initialize the runtime agent manager
    agent_manager = get_runtime_agent_manager()
    agent_manager.get_agent()
    if initial_command:
        from code_puppy.messaging import emit_info, emit_system_message

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
            if awaiting_input:
                # No spinner - use agent_manager's run_with_mcp method
                response = await agent_manager.run_with_mcp(
                    initial_command,
                    message_history=get_message_history(),
                    usage_limits=get_custom_usage_limits(),
                )
            else:
                # Use our custom spinner for better compatibility with user input
                from code_puppy.messaging.spinner import ConsoleSpinner

                with ConsoleSpinner(console=display_console):
                    # Use agent_manager's run_with_mcp method
                    response = await agent_manager.run_with_mcp(
                        initial_command,
                        message_history=prune_interrupted_tool_calls(
                            get_message_history()
                        ),
                        usage_limits=get_custom_usage_limits(),
                    )
                    set_message_history(
                        prune_interrupted_tool_calls(get_message_history())
                    )

            agent_response = response.output

            emit_system_message(
                f"\n[bold purple]AGENT RESPONSE: [/bold purple]\n{agent_response}"
            )
            new_msgs = response.all_messages()
            message_history_accumulator(new_msgs)
            set_message_history(prune_interrupted_tool_calls(get_message_history()))
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

    while True:
        from code_puppy.agents.agent_manager import get_current_agent_config
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent_config()
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
            clear_message_history()
            from code_puppy.messaging import emit_system_message, emit_warning

            emit_warning("Conversation history cleared!")
            emit_system_message("The agent will not remember previous interactions.\n")
            continue

        # Handle / commands before anything else
        if task.strip().startswith("/"):
            command_result = handle_command(task.strip())
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

                # Use our custom spinner for better compatibility with user input
                from code_puppy.messaging import emit_warning
                from code_puppy.messaging.spinner import ConsoleSpinner

                runtime_manager = get_runtime_agent_manager()
                with ConsoleSpinner(console=message_renderer.console):
                    result = await runtime_manager.run_with_mcp(
                        task,
                        get_custom_usage_limits(),
                        message_history=prune_interrupted_tool_calls(
                            get_message_history()
                        ),
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

                # Update message history - the agent's history processor will handle truncation
                new_msgs = result.all_messages()
                message_history_accumulator(new_msgs)

                emit_system_message(
                    f"Context: {len(get_message_history())} messages in history\n"
                )

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


async def execute_single_prompt(prompt: str, message_renderer) -> None:
    """Execute a single prompt and exit (for -p flag)."""
    from code_puppy.messaging import emit_info, emit_system_message

    emit_info(f"[bold blue]Executing prompt:[/bold blue] {prompt}")

    try:
        # Get agent through runtime manager and use its run_with_mcp method
        agent_manager = get_runtime_agent_manager()

        from code_puppy.messaging.spinner import ConsoleSpinner

        with ConsoleSpinner(console=message_renderer.console):
            response = await agent_manager.run_with_mcp(
                prompt,
                usage_limits=get_custom_usage_limits(),
            )

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
        return 0


if __name__ == "__main__":
    main_entry()
