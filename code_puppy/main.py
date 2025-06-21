import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy import __version__
from code_puppy.agent import get_code_generation_agent, session_memory
from code_puppy.command_line.prompt_toolkit_completion import (
    get_input_with_combined_completion,
    get_prompt_with_active_model,
)
from code_puppy.config import ensure_config_exists

# Initialize rich console for pretty output
from code_puppy.tools.common import console
from code_puppy.version_checker import fetch_latest_version

# from code_puppy.tools import *  # noqa: F403


# Define a function to get the secret file path
def get_secret_file_path():
    hidden_directory = os.path.join(os.path.expanduser("~"), ".agent_secret")
    if not os.path.exists(hidden_directory):
        os.makedirs(hidden_directory)
    return os.path.join(hidden_directory, "history.txt")


async def main():
    # Ensure the config directory and puppy.cfg with name info exist (prompt user if needed)
    ensure_config_exists()
    current_version = __version__
    latest_version = fetch_latest_version("code-puppy")
    console.print(f"Current version: {current_version}")
    console.print(f"Latest version: {latest_version}")
    if latest_version and latest_version != current_version:
        console.print(
            f"[bold yellow]A new version of code puppy is available: {latest_version}[/bold yellow]"
        )
        console.print("[bold green]Please consider updating![/bold green]")
    global shutdown_flag
    shutdown_flag = False  # ensure this is initialized

    # Load environment variables from .env file
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Code Puppy - A code generation agent")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run in interactive mode"
    )
    parser.add_argument("command", nargs="*", help="Run a single command")
    args = parser.parse_args()

    history_file_path = get_secret_file_path()

    if args.command:
        # Join the list of command arguments into a single string command
        command = " ".join(args.command)
        try:
            while not shutdown_flag:
                agent = get_code_generation_agent()
                async with agent.run_mcp_servers():
                    response = await agent.run(command)
                agent_response = response.output
                console.print(agent_response.output_message)
                # Log to session memory
                session_memory().log_task(
                    f"Command executed: {command}",
                    extras={
                        "output": agent_response.output_message,
                        "awaiting_user_input": agent_response.awaiting_user_input,
                    },
                )
                if agent_response.awaiting_user_input:
                    console.print(
                        "[bold red]The agent requires further input. Interactive mode is recommended for such tasks."
                    )
                break
        except AttributeError as e:
            console.print(f"[bold red]AttributeError:[/bold red] {str(e)}")
            console.print(
                "[bold yellow]\u26a0 The response might not be in the expected format, missing attributes like 'output_message'."
            )
        except Exception as e:
            console.print(f"[bold red]Unexpected Error:[/bold red] {str(e)}")
    elif args.interactive:
        await interactive_mode(history_file_path)
    else:
        parser.print_help()


# Add the file handling functionality for interactive mode
async def interactive_mode(history_file_path: str) -> None:
    from code_puppy.command_line.meta_command_handler import handle_meta_command

    """Run the agent in interactive mode."""
    console.print("[bold green]Code Puppy[/bold green] - Interactive Mode")
    console.print("Type 'exit' or 'quit' to exit the interactive mode.")
    console.print("Type 'clear' to reset the conversation history.")
    console.print(
        "Type [bold blue]@[/bold blue] for path completion, or [bold blue]~m[/bold blue] to pick a model."
    )

    # Show meta commands right at startup - DRY!
    from code_puppy.command_line.meta_command_handler import META_COMMANDS_HELP

    console.print(META_COMMANDS_HELP)
    # Show MOTD if user hasn't seen it after an update
    try:
        from code_puppy.command_line.motd import print_motd
        print_motd(console, force=False)
    except Exception as e:
        console.print(f'[yellow]MOTD error: {e}[/yellow]')

    # Check if prompt_toolkit is installed
    try:
        import prompt_toolkit  # noqa: F401

        console.print("[dim]Using prompt_toolkit for enhanced tab completion[/dim]")
    except ImportError:
        console.print(
            "[yellow]Warning: prompt_toolkit not installed. Installing now...[/yellow]"
        )
        try:
            import subprocess

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "prompt_toolkit"]
            )
            console.print("[green]Successfully installed prompt_toolkit[/green]")
        except Exception as e:
            console.print(f"[bold red]Error installing prompt_toolkit: {e}[/bold red]")
            console.print(
                "[yellow]Falling back to basic input without tab completion[/yellow]"
            )

    message_history = []

    # Set up history file in home directory
    history_file_path_prompt = os.path.expanduser("~/.code_puppy_history.txt")
    history_dir = os.path.dirname(history_file_path_prompt)

    # Ensure history directory exists
    if history_dir and not os.path.exists(history_dir):
        try:
            os.makedirs(history_dir, exist_ok=True)
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not create history directory: {e}[/yellow]"
            )

    while True:
        console.print("[bold blue]Enter your coding task:[/bold blue]")

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
            console.print("\n[yellow]Input cancelled[/yellow]")
            continue

        # Check for exit commands
        if task.strip().lower() in ["exit", "quit"]:
            console.print("[bold green]Goodbye![/bold green]")
            break

        # Check for clear command (supports both `clear` and `~clear`)
        if task.strip().lower() in ("clear", "~clear"):
            message_history = []
            console.print("[bold yellow]Conversation history cleared![/bold yellow]")
            console.print(
                "[dim]The agent will not remember previous interactions.[/dim]\n"
            )
            continue

        # Handle ~ meta/config commands before anything else
        if task.strip().startswith("~"):
            if handle_meta_command(task.strip(), console):
                continue
        if task.strip():
            console.print(f"\n[bold blue]Processing task:[/bold blue] {task}\n")

            # Write to the secret file for permanent history
            with open(history_file_path, "a") as f:
                f.write(f"{task}\n")

            try:
                prettier_code_blocks()

                console.log(f"Asking: {task}...", style="cyan")

                # Store agent's full response
                agent_response = None

                agent = get_code_generation_agent()
                async with agent.run_mcp_servers():
                    result = await agent.run(task, message_history=message_history)
                # Get the structured response
                agent_response = result.output
                console.print(agent_response.output_message)
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
                            for part in getattr(m, 'parts', []):
                                if hasattr(part, 'tool_call_id') and part.tool_call_id:
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
                    # Flattened history (latest groups/singletons last, trunc to N messages total),
                    # but always keep complete tool_call_id groups together
                    truncated = []
                    count = 0
                    for group in reversed(grouped_msgs):
                        if count + len(group) > limit:
                            break
                        truncated[:0] = group  # insert at front
                        count += len(group)
                    message_history = truncated
                # --- END GROUP-AWARE TRUNCATION LOGIC ---


                if agent_response and agent_response.awaiting_user_input:
                    console.print(
                        "\n[bold yellow]\u26a0 Agent needs your input to continue.[/bold yellow]"
                    )

                # Show context status
                console.print(
                    f"[dim]Context: {len(message_history)} messages in history[/dim]\n"
                )

            except Exception:
                console.print_exception()


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
