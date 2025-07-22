import argparse
import asyncio
import os
import socket
import subprocess
import sys

# HTTP server imports
import uvicorn
from dotenv import load_dotenv
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy import __version__
from code_puppy.agent import (
    get_code_generation_agent,
    get_custom_usage_limits,
    session_memory,
)
from code_puppy.auth import authenticate_puppy, get_puppy_token
from code_puppy.command_line.prompt_toolkit_completion import (
    get_input_with_combined_completion,
    get_prompt_with_active_model,
)
from code_puppy.config import ensure_config_exists
from code_puppy.globals import set_tui_mode, is_tui_mode

# HTTP server imports
from code_puppy.http_server import app as http_app

# Initialize rich console for pretty output
from code_puppy.tools.common import console
from code_puppy.urls import get_setup_url
from code_puppy.version_checker import fetch_latest_version, versions_are_equal


# Use the existing console from tools.common to maintain consistency with tests

# from code_puppy.tools import *  # noqa: F403


def display_disclaimer():
    """Display a disclaimer message about data sensitivity and usage guidelines."""
    from code_puppy.messaging import emit_system_message
    
    message = "\n[bold yellow]DISCLAIMER : Be a responsible Puppy Owner[/bold yellow]"
    emit_system_message(message)
    
    message = "[yellow]Prompt responsibly: Only use internal data available to all HO associates. No permission based data should be included in prompts.[/yellow]"
    emit_system_message(message)
    
    message = ("[yellow]All information entered will be monitored in accordance with "
        "applicable Walmart policies and used for enhancement of this tool and "
        "AI adoption at Walmart. Refer to "
        "[link=https://one.walmart.com/content/uswire/en_us/work1/policies/"
        "people-policies/company-issued-equipment-useage.html]usage[/link] "
        "for best practices on secure usage.[/yellow]\n")
    emit_system_message(message)


# Define a function to get the secret file path
def get_secret_file_path():
    hidden_directory = os.path.join(os.path.expanduser("~"), ".agent_secret")
    if not os.path.exists(hidden_directory):
        os.makedirs(hidden_directory)
    return os.path.join(hidden_directory, "history.txt")


def find_available_port(start_port=8090, end_port=9010, host="127.0.0.1"):
    """Find an available port in the given range.

    Args:
        start_port: First port to try (default: 8090)
        end_port: Last port to try (default: 9010)
        host: Host to bind to (default: 127.0.0.1)

    Returns:
        int: Available port number, or None if no ports available
    """
    for port in range(start_port, end_port + 1):
        try:
            # Try to bind to the port to check if it's available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                return port
        except OSError:
            # Port is in use, try the next one
            continue
    return None


async def main():
    # Parse arguments FIRST to determine if we're in TUI mode
    parser = argparse.ArgumentParser(description="Code Puppy - A code generation agent")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument("--tui", "-t", action="store_true", help="Run in TUI mode")
    parser.add_argument("command", nargs="*", help="Run a single command")
    args = parser.parse_args()

    # Determine if we're in TUI mode early and set it globally
    if args.tui:
        set_tui_mode(True)
    elif args.interactive:
        set_tui_mode(False)

    # Set up message renderer for interactive mode
    message_renderer = None
    if args.interactive and not is_tui_mode():
        from code_puppy.messaging import (
            get_global_queue,
            SynchronousInteractiveRenderer,
        )
        from rich.console import Console

        message_queue = get_global_queue()
        display_console = Console()  # Separate console for rendering messages
        message_renderer = SynchronousInteractiveRenderer(message_queue, display_console)
        message_renderer.start()

    # Import message queue functions early
    from code_puppy.messaging import emit_system_message

    # Show immediate loading feedback to user
    emit_system_message("🐶 Code Puppy is Loading...")

    # Find an available port for the HTTP server
    available_port = find_available_port()
    if available_port is None:
        error_msg = "Error: No available ports in range 8090-9010!"
        emit_system_message(f"[bold red]{error_msg}[/bold red]")
        return

    # HTTP server starts silently in the background

    # Start the HTTP server in the background
    async def run_http_server():
        try:
            config = uvicorn.Config(
                http_app,
                host="127.0.0.1",
                port=available_port,
                log_level="critical",  # suppress most logs
                access_log=False,  # suppress access logs
            )
            server = uvicorn.Server(config)
            await server.serve()
        except Exception as e:
            # Log HTTP server errors but don't crash the main application
            emit_system_message(f"[dim red]HTTP server error: {e}[/dim red]")

    # Store the HTTP server task for proper lifecycle management
    http_server_task = asyncio.create_task(run_http_server())

    # Ensure the config directory and puppy.cfg with name info exist (prompt user if needed)
    ensure_config_exists()
    current_version = __version__

    # Check if auto-update is disabled via environment variable
    no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    # Print startup messages
    if no_version_update:
        version_msg = f"Current version: {current_version}"
        update_disabled_msg = (
            "Auto-update disabled via NO_VERSION_UPDATE environment variable"
        )

        emit_system_message(version_msg)
        emit_system_message(f"[dim]{update_disabled_msg}[/dim]")
    else:
        latest_version = fetch_latest_version("code-puppy")
        version_msg = f"Current version: {current_version}"
        latest_msg = f"Latest version: {latest_version}"

        emit_system_message(version_msg)
        emit_system_message(latest_msg)

        if latest_version and not versions_are_equal(current_version, latest_version):
            update_available_msg = (
                f"A new version of code puppy is available: {latest_version}"
            )
            updating_msg = "Auto-updating now..."

            emit_system_message(f"[bold yellow]{update_available_msg}[/bold yellow]")
            emit_system_message("[bold green]Auto-updating now...[/bold green]")

            try:
                # Run the update command
                setup_url = get_setup_url()
                emit_system_message(f"[dim]{setup_url}[/dim]")

                result = subprocess.run(
                    [
                        "curl",
                        "-skSL",
                        setup_url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    # Pipe the output to bash
                    bash_result = subprocess.run(
                        ["bash"], input=result.stdout, text=True, timeout=120
                    )

                    if bash_result.returncode == 0:
                        success_msg = "✅ Update completed successfully!"
                        restart_msg = "Restarting code-puppy..."
                        emit_system_message(f"[bold green]{success_msg}[/bold green]")
                        emit_system_message(f"[yellow]{restart_msg}[/yellow]")
                        sys.exit(0)
                    else:
                        error_msg = (
                            f"❌ Update failed with exit code: {bash_result.returncode}"
                        )
                        continue_msg = "Continuing with current version..."
                        emit_system_message(f"[bold red]{error_msg}[/bold red]")
                        emit_system_message(f"[yellow]{continue_msg}[/yellow]")
                else:
                    error_msg = f"❌ Failed to download update script: {result.stderr}"
                    continue_msg = "Continuing with current version..."
                    emit_system_message(f"[bold red]{error_msg}[/bold red]")
                    emit_system_message(f"[yellow]{continue_msg}[/yellow]")

            except subprocess.TimeoutExpired:
                timeout_msg = "❌ Update timed out"
                continue_msg = "Continuing with current version..."
                emit_system_message(f"[bold red]{timeout_msg}[/bold red]")
                emit_system_message(f"[yellow]{continue_msg}[/yellow]")
            except Exception as e:
                error_msg = f"❌ Update failed: {str(e)}"
                continue_msg = "Continuing with current version..."
                emit_system_message(f"[bold red]{error_msg}[/bold red]")
                emit_system_message(f"[yellow]{continue_msg}[/yellow]")

    # Display the disclaimer message
    display_disclaimer()

    global shutdown_flag
    shutdown_flag = False  # ensure this is initialized

    # Load environment variables from .env file
    load_dotenv()

    # Import the modified authenticate_puppy that accepts tui_mode
    await authenticate_puppy(available_port)

    token = get_puppy_token()
    os.environ["puppy_token"] = token

    history_file_path = get_secret_file_path()

    try:
        if args.command:
            # Join the list of command arguments into a single string command
            command = " ".join(args.command)
            try:
                while not shutdown_flag:
                    # Show thinking message, then processing message, then spinner
                    # console.print(SpinnerBase.THINKING_MESSAGE)

                    # Check if any tool is waiting for user input before showing spinner
                    try:
                        from code_puppy.tools.command_runner import (
                            is_awaiting_user_input,
                        )

                        awaiting_input = is_awaiting_user_input()
                    except ImportError:
                        awaiting_input = False

                    # Get the agent
                    agent = get_code_generation_agent()

                    # Run with or without spinner based on whether we're awaiting input
                    if awaiting_input:
                        # No spinner - just run the agent
                        async with agent.run_mcp_servers():
                            response = await agent.run(
                                command, usage_limits=get_custom_usage_limits()
                            )
                    else:
                        # Use our custom spinner for better compatibility with user input
                        from code_puppy.messaging.spinner import ConsoleSpinner
                        from rich.console import Console as RichConsole

                        rich_console = RichConsole()
                        with ConsoleSpinner(console=rich_console):
                            async with agent.run_mcp_servers():
                                response = await agent.run(
                                    command, usage_limits=get_custom_usage_limits()
                                )
                    agent_response = response.output
                    from code_puppy.messaging import emit_agent_reasoning
                    emit_agent_reasoning(agent_response.output_message)
                    # Log to session memory
                    session_memory().log_task(
                        f"Command executed: {command}",
                        extras={
                            "output": agent_response.output_message,
                            "awaiting_user_input": agent_response.awaiting_user_input,
                        },
                    )
                    if agent_response.awaiting_user_input:
                        from code_puppy.messaging import emit_warning
                        emit_warning(
                            "[bold red]The agent requires further input. Interactive mode is recommended for such tasks."
                        )
                    break
            except AttributeError as e:
                from code_puppy.messaging import emit_error, emit_warning
                emit_error(f"AttributeError: {str(e)}")
                emit_warning(
                    "\u26a0 The response might not be in the expected format, missing attributes like 'output_message'."
                )
            except Exception as e:
                from code_puppy.messaging import emit_error
                emit_error(f"Unexpected Error: {str(e)}")
        elif is_tui_mode():
            # Import here to avoid dependency issues if textual is not available
            try:
                from code_puppy.tui import run_textual_ui

                await run_textual_ui()
            except ImportError:
                from code_puppy.messaging import emit_error, emit_warning
                emit_error("Error: Textual UI not available. Install with: pip install textual")
                emit_warning("Falling back to interactive mode...")
                await interactive_mode(history_file_path)
            except Exception as e:
                from code_puppy.messaging import emit_error, emit_warning
                emit_error(f"TUI Error: {str(e)}")
                emit_warning("Falling back to interactive mode...")
                await interactive_mode(history_file_path)
        elif args.interactive:
            await interactive_mode(history_file_path, message_renderer)
        else:
            parser.print_help()
    finally:
        # Stop the message renderer if it was started
        if message_renderer:
            message_renderer.stop()

        # Clean up the HTTP server task when exiting
        if not http_server_task.done():
            http_server_task.cancel()
            try:
                await http_server_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            except Exception as e:
                # Log cleanup errors but don't crash
                emit_system_message(f"[dim red]HTTP server cleanup error: {e}[/dim red]")


# Add the file handling functionality for interactive mode
async def interactive_mode(history_file_path: str, message_renderer) -> None:
    from code_puppy.command_line.meta_command_handler import handle_meta_command

    """Run the agent in interactive mode."""
    message_history = []

    # The message_renderer is now started in main() and passed in.
    # We just need to make sure we stop it when we exit.
    display_console = message_renderer.console

    # Now that the renderer is started, we can safely emit messages and see the output
    from code_puppy.messaging import emit_system_message, emit_info
    
    emit_info("[bold green]Code Puppy[/bold green] - Interactive Mode")
    emit_system_message("Type 'exit' or 'quit' to exit the interactive mode.")
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message(
        "Type [bold blue]@[/bold blue] for path completion, or [bold blue]~m[/bold blue] to pick a model."
    )

    # Show meta commands right at startup - DRY!
    from code_puppy.command_line.meta_command_handler import META_COMMANDS_HELP

    emit_system_message(META_COMMANDS_HELP)
    # Show MOTD if user hasn't seen it after an update
    try:
        from code_puppy.command_line.motd import print_motd

        print_motd(console, force=False)
    except Exception as e:
        from code_puppy.messaging import emit_warning
        emit_warning(f"MOTD error: {e}")

    # Check if prompt_toolkit is installed
    try:
        from code_puppy.messaging import emit_system_message
        emit_system_message("[dim]Using prompt_toolkit for enhanced tab completion[/dim]")
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

    # Set up history file in home directory
    history_file_path_prompt = os.path.expanduser("~/.code_puppy_history.txt")
    history_dir = os.path.dirname(history_file_path_prompt)

    # Ensure history directory exists
    if history_dir and not os.path.exists(history_dir):
        try:
            os.makedirs(history_dir, exist_ok=True)
        except Exception as e:
            from code_puppy.messaging import emit_warning
            emit_warning(f"Warning: Could not create history directory: {e}")

    while True:
        from code_puppy.messaging import emit_info
        emit_info("[bold blue]Enter your coding task:[/bold blue]")

        try:
            # Use prompt_toolkit for enhanced input with path completion
            try:
                # Use the async version of get_input_with_combined_completion
                task = await get_input_with_combined_completion(
                    get_prompt_with_active_model(),
                    history_file=history_file_path_prompt,
                )
            except ImportError:
                # Fall back to basic input if prompt_toolkit is not available
                task = input(">>> ")

        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D
            from code_puppy.messaging import emit_warning
            emit_warning("\nInput cancelled")
            continue

        # Check for exit commands
        if task.strip().lower() in ["exit", "quit"]:
            from code_puppy.messaging import emit_success
            emit_success("Goodbye!")
            # The renderer is stopped in the finally block of main().
            break

        # Check for clear command (supports both `clear` and `~clear`)
        if task.strip().lower() in ("clear", "~clear"):
            message_history = []
            from code_puppy.messaging import emit_warning, emit_system_message
            emit_warning("Conversation history cleared!")
            emit_system_message("The agent will not remember previous interactions.\n")
            continue

        # Handle ~ meta/config commands before anything else
        if task.strip().startswith("~"):
            if handle_meta_command(task.strip(), console):
                continue
        if task.strip():
            # Write to the secret file for permanent history
            with open(history_file_path, "a") as f:
                f.write(f"{task}\n")

            try:
                prettier_code_blocks()

                # Store agent's full response
                agent_response = None

                # Show thinking message, then processing message, then spinner
                # console.print(SpinnerBase.THINKING_MESSAGE)

                # Just get the agent and run it with spinner
                agent = get_code_generation_agent()

                # Use our custom spinner for better compatibility with user input
                from code_puppy.messaging.spinner import ConsoleSpinner

                with ConsoleSpinner(console=display_console):
                    async with agent.run_mcp_servers():
                        result = await agent.run(
                            task,
                            message_history=message_history,
                            usage_limits=get_custom_usage_limits(),
                        )
                # Get the structured response
                agent_response = result.output
                from code_puppy.messaging import emit_agent_reasoning
                emit_agent_reasoning(agent_response.output_message)
                # Log to session memory
                session_memory().log_task(
                    f"Interactive task: {task}",
                    extras={
                        "output": agent_response.output_message,
                        "awaiting_user_input": agent_response.awaiting_user_input,
                    },
                )

                # Update message history but apply filters & limits
                new_msgs = result.new_messages()
                # 1. Drop any system/config messages (e.g., "agent loaded with model")
                filtered = [
                    m
                    for m in new_msgs
                    if not (isinstance(m, dict) and m.get("role") == "system")
                ]
                # 2. Append to existing history and keep only the most recent set by config
                from code_puppy.config import get_message_history_limit

                message_history.extend(filtered)

                # --- BEGIN GROUP-AWARE TRUNCATION LOGIC ---
                limit = get_message_history_limit()
                if len(message_history) > limit:

                    def group_by_tool_call_id(msgs):
                        grouped = {}
                        no_group = []
                        for m in msgs:
                            # Find all tool_call_id in message parts
                            tool_call_ids = set()
                            for part in getattr(m, "parts", []):
                                if hasattr(part, "tool_call_id") and part.tool_call_id:
                                    tool_call_ids.add(part.tool_call_id)
                            if tool_call_ids:
                                for tcid in tool_call_ids:
                                    grouped.setdefault(tcid, []).append(m)
                            else:
                                no_group.append(m)
                        return grouped, no_group

                    grouped, no_group = group_by_tool_call_id(message_history)
                    # Flatten into groups or singletons
                    grouped_msgs = list(grouped.values()) + [[m] for m in no_group]
                    # Keep complete tool_call_id groups together while preserving chronological order
                    groups_to_keep = []
                    count = 0
                    for group in reversed(grouped_msgs):
                        if count + len(group) > limit:
                            break
                        groups_to_keep.append(group)
                        count += len(group)
                    # Reverse to restore chronological order, then flatten
                    message_history = [
                        msg for group in reversed(groups_to_keep) for msg in group
                    ]
                # --- END GROUP-AWARE TRUNCATION LOGIC ---

                if agent_response and agent_response.awaiting_user_input:
                    from code_puppy.messaging import emit_warning
                    emit_warning("\n\u26a0 Agent needs your input to continue.")

                # Show context status
                from code_puppy.messaging import emit_system_message
                emit_system_message(f"Context: {len(message_history)} messages in history\n")

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


def main_entry():
    """Entry point for the installed CLI tool."""
    asyncio.run(main())


if __name__ == "__main__":
    main_entry()
