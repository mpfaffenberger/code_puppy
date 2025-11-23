"""Command handlers for Code Puppy - CORE commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import os
import shlex
import signal
import subprocess
from typing import Optional

from code_puppy.command_line.command_registry import register_command
from code_puppy.command_line.model_picker_completion import update_model_in_input
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import finalize_autosave_session
from code_puppy.tools.tools_content import tools_content


# =============================================================================
# SHELL COMMAND EXECUTION - SHARED LOGIC
# =============================================================================

# Commands that require interactive TTY access (categorized for maintainability)
INTERACTIVE_COMMANDS = {
    "remote": {"ssh", "telnet", "ftp", "sftp", "mosh"},
    "editors": {"vim", "vi", "nano", "emacs", "nvim"},
    "monitors": {"top", "htop", "watch", "iotop", "nethogs"},
    "pagers": {"less", "more", "man"},
    "repls": {"python", "python3", "ipython", "node", "irb", "ruby"},
    "databases": {"psql", "mysql", "redis-cli", "mongo", "sqlite3"},
    "multiplexers": {"tmux", "screen"},
}


def _get_all_interactive_commands() -> set:
    """Flatten the categorized interactive commands into a single set."""
    return set().union(*INTERACTIVE_COMMANDS.values())


def _should_use_tty(command: str) -> bool:
    """Determine if a command needs interactive TTY based on context.

    Args:
        command: The shell command string to analyze

    Returns:
        True if the command needs TTY access, False otherwise
    """
    try:
        # Parse command to get the base executable name
        parts = shlex.split(command)
        if not parts:
            return False

        # Extract base command name (strip path)
        base_cmd = os.path.basename(parts[0])

        # Commands that ALWAYS need TTY
        always_tty = {"ssh", "telnet", "tmux", "screen", "mosh"}
        if base_cmd in always_tty:
            return True

        # Editors need TTY unless in batch/script mode
        if base_cmd in {"vim", "vi", "nvim", "nano", "emacs"}:
            # Check for non-interactive flags
            batch_flags = {"-E", "-s", "--batch", "-e", "-c"}
            return not any(flag in parts for flag in batch_flags)

        # REPLs only need TTY if no script/command is provided
        if base_cmd in {"python", "python3", "ipython", "node", "irb", "ruby"}:
            # If only the command name, it's interactive
            # If there's a file or -c flag, it's not
            return len(parts) == 1 and "-c" not in parts

        # Database CLIs default to interactive unless command provided
        if base_cmd in {"psql", "mysql", "redis-cli", "mongo", "sqlite3"}:
            return (
                "-c" not in parts and "--command" not in parts and "--eval" not in parts
            )

        # Other potentially interactive commands
        interactive_set = _get_all_interactive_commands()
        return base_cmd in interactive_set

    except (ValueError, IndexError):
        # If parsing fails, assume non-interactive for safety
        return False


def _execute_shell_command(
    shell_command: str,
    cwd: Optional[str] = None,
    timeout: Optional[int] = 3600,
) -> int:
    """Execute a shell command with appropriate TTY handling.

    SECURITY NOTE: This function uses shell=True for full shell feature support
    (pipes, wildcards, variable expansion, etc.). This introduces command injection
    risk if called with untrusted input. Use only in contexts where the user
    has already been authenticated and is authorized to execute arbitrary commands.

    Args:
        shell_command: The command to execute
        cwd: Working directory (defaults to current)
        timeout: Maximum execution time in seconds (None = no timeout)

    Returns:
        The process exit code

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout
        KeyboardInterrupt: If user interrupts with Ctrl+C
    """
    from code_puppy.messaging import emit_error, emit_success, emit_warning

    process = None
    needs_tty = _should_use_tty(shell_command)

    try:
        if needs_tty:
            # TTY mode: Give command direct terminal access
            process = subprocess.Popen(
                shell_command,
                shell=True,
                cwd=cwd,
            )

            # Wait for completion with timeout
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                emit_warning(f"Command timed out after {timeout} seconds")
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise

            # Show exit status
            if returncode != 0:
                emit_error(f"Command exited with code {returncode}")
            else:
                emit_success("[dim]Command completed successfully[/dim]")

            return returncode

        else:
            # Regular mode: Capture and stream output
            process = subprocess.Popen(
                shell_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=cwd,
            )

            # Stream stdout in real-time
            stdout_lines = []
            if process.stdout:
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        print(line)  # Direct terminal output
                        stdout_lines.append(line)

            # Get stderr after completion
            _, stderr = process.communicate(timeout=timeout if timeout else None)

            # Display stderr
            if stderr:
                for line in stderr.strip().split("\n"):
                    if line:
                        emit_warning(f"[dim]{line}[/dim]")

            # Show exit status
            if process.returncode != 0:
                emit_error(f"Command exited with code {process.returncode}")
            else:
                emit_success("[dim]Command completed successfully[/dim]")

            return process.returncode

    except subprocess.TimeoutExpired:
        # Already handled above
        raise
    except KeyboardInterrupt:
        # User interrupted - try to clean up gracefully
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    except FileNotFoundError:
        emit_error(f"Command not found: {shell_command.split()[0]}")
        return 127  # Standard "command not found" exit code
    except Exception as e:
        emit_error(f"Error executing command: {e}")
        return 1
    finally:
        # Ensure process is cleaned up
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


# Import get_commands_help from command_handler to avoid circular imports
# This will be defined in command_handler.py
def get_commands_help():
    """Lazy import to avoid circular dependency."""
    from code_puppy.command_line.command_handler import get_commands_help as _gch

    return _gch()


@register_command(
    name="help",
    description="Show this help message",
    usage="/help, /h",
    aliases=["h"],
    category="core",
)
def handle_help_command(command: str) -> bool:
    """Show commands help."""
    import uuid

    from code_puppy.messaging import emit_info

    group_id = str(uuid.uuid4())
    help_text = get_commands_help()
    emit_info(help_text, message_group_id=group_id)
    return True


@register_command(
    name="shell",
    description="Run shell commands or enter interactive shell mode",
    usage="/shell [command], /! [command]",
    aliases=["!"],
    category="core",
)
def handle_shell_command(command: str) -> bool:
    """Execute a shell command directly or enter interactive shell mode.

    Automatically detects interactive commands (ssh, vim, etc.) and provides
    them with direct TTY access instead of piped output.

    SECURITY WARNING: Commands are executed with shell=True, which allows
    full shell features (pipes, wildcards, etc.) but also enables command
    injection if used with untrusted input. This is acceptable for a CLI
    tool where the user is already authenticated and authorized.
    """
    import asyncio
    import concurrent.futures
    from code_puppy.messaging import emit_error, emit_info, emit_warning

    tokens = command.split(maxsplit=1)

    # If no arguments provided, enter interactive shell mode
    if len(tokens) < 2:
        try:
            # Run the async shell mode using asyncio utilities
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(lambda: asyncio.run(shell_interactive_mode()))
                future.result(timeout=3600)  # 1 hour timeout
            return True
        except Exception as e:
            emit_error(f"Error entering interactive shell: {e}")
            return True

    # Single command execution
    shell_command = tokens[1]

    try:
        # Show what we're running
        emit_info(f"[bold cyan]$[/bold cyan] {shell_command}")

        # Execute using shared logic
        _execute_shell_command(shell_command, cwd=os.getcwd())

    except KeyboardInterrupt:
        emit_warning("\nCommand interrupted by user")
    except Exception as e:
        emit_error(f"Error executing command: {e}")

    return True


async def shell_interactive_mode() -> None:
    """Run an interactive shell session until user exits.

    This creates a mini shell environment where commands are executed directly.
    User can type 'exit', 'quit', or '/back' to return to code puppy mode.

    Special handling for interactive commands (ssh, vim, etc.) that need TTY access.

    SECURITY WARNING: Commands are executed with shell=True for full shell
    compatibility. This is appropriate for an interactive user session.
    """
    import os
    import subprocess
    from code_puppy.messaging import (
        emit_error,
        emit_info,
        emit_success,
        emit_system_message,
        emit_warning,
    )

    # Check if prompt_toolkit is available for better input
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory

        use_prompt_toolkit = True
    except ImportError:
        use_prompt_toolkit = False

    # Show welcome message
    emit_system_message("\n[bold green]🐚 Entering Interactive Shell Mode[/bold green]")
    emit_info(
        "[dim]Type commands directly. Use 'exit', 'quit', or '/back' to return to Code Puppy.[/dim]"
    )
    emit_info(f"[dim]Working directory: {os.getcwd()}[/dim]\n")

    # Create session if using prompt_toolkit
    if use_prompt_toolkit:
        session = PromptSession(history=InMemoryHistory())

    while True:
        try:
            # Get current working directory for prompt
            cwd = os.getcwd()
            # Abbreviate home directory
            if cwd.startswith(os.path.expanduser("~")):
                cwd = cwd.replace(os.path.expanduser("~"), "~", 1)

            # Create a colorful shell prompt
            prompt_text = f"\n[bold cyan]shell[/bold cyan] [yellow]{cwd}[/yellow] [bold green]$[/bold green] "

            # Get input
            if use_prompt_toolkit:
                # Use prompt_toolkit for better history and editing
                # Convert rich markup to plain text for prompt_toolkit
                plain_prompt = f"shell {cwd} $ "
                try:
                    import asyncio

                    shell_cmd = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: session.prompt(plain_prompt)
                    )
                except EOFError:
                    # Ctrl+D pressed
                    emit_info("\n[dim]Exiting shell mode...[/dim]")
                    break
            else:
                # Fallback to basic input
                emit_info(prompt_text, end="")
                shell_cmd = input()

            # Strip whitespace
            shell_cmd = shell_cmd.strip()

            # Check for exit commands
            if shell_cmd.lower() in ["exit", "quit", "/back", "/exit", "/quit"]:
                emit_success(
                    "\n[bold green]🐶 Returning to Code Puppy mode[/bold green]\n"
                )
                break

            # Skip empty commands
            if not shell_cmd:
                continue

            # Handle 'cd' command specially to change directory
            if shell_cmd.startswith("cd "):
                try:
                    # Parse the directory (handle ~ and relative paths)
                    target_dir = shell_cmd[3:].strip()
                    if not target_dir:
                        # 'cd' with no args goes to home
                        target_dir = os.path.expanduser("~")
                    else:
                        target_dir = os.path.expanduser(target_dir)
                        if not os.path.isabs(target_dir):
                            target_dir = os.path.join(os.getcwd(), target_dir)

                    # Change directory
                    os.chdir(target_dir)
                    emit_success(f"[dim]Changed to: {os.getcwd()}[/dim]")
                    continue
                except FileNotFoundError:
                    emit_error(f"cd: no such directory: {target_dir}")
                    continue
                except Exception as e:
                    emit_error(f"cd: {e}")
                    continue

            # Execute other commands using shared logic
            try:
                _execute_shell_command(shell_cmd, cwd=os.getcwd())
            except subprocess.TimeoutExpired:
                emit_warning("Command timed out")
            except Exception:
                # Error already handled by _execute_shell_command
                pass

        except KeyboardInterrupt:
            # Ctrl+C pressed - just show a new prompt
            emit_warning("\n^C")
            continue
        except EOFError:
            # Ctrl+D pressed - exit shell mode
            emit_info("\n[dim]Exiting shell mode...[/dim]")
            break


@register_command(
    name="cd",
    description="Change directory or show directories",
    usage="/cd <dir>",
    category="core",
)
def handle_cd_command(command: str) -> bool:
    """Change directory or list current directory."""
    # Use shlex.split to handle quoted paths properly
    import shlex

    from code_puppy.messaging import emit_error, emit_info, emit_success

    try:
        tokens = shlex.split(command)
    except ValueError:
        # Fallback to simple split if shlex fails
        tokens = command.split()
    if len(tokens) == 1:
        try:
            table = make_directory_table()
            emit_info(table)
        except Exception as e:
            emit_error(f"Error listing directory: {e}")
        return True
    elif len(tokens) == 2:
        dirname = tokens[1]
        target = os.path.expanduser(dirname)
        if not os.path.isabs(target):
            target = os.path.join(os.getcwd(), target)
        if os.path.isdir(target):
            os.chdir(target)
            emit_success(f"Changed directory to: {target}")
        else:
            emit_error(f"Not a directory: {dirname}")
        return True
    return True


@register_command(
    name="tools",
    description="Show available tools and capabilities",
    usage="/tools",
    category="core",
)
def handle_tools_command(command: str) -> bool:
    """Display available tools."""
    from rich.markdown import Markdown

    from code_puppy.messaging import emit_info

    markdown_content = Markdown(tools_content)
    emit_info(markdown_content)
    return True


@register_command(
    name="motd",
    description="Show the latest message of the day (MOTD)",
    usage="/motd",
    category="core",
)
def handle_motd_command(command: str) -> bool:
    """Show message of the day."""
    try:
        print_motd(force=True)
    except Exception:
        # Handle printing errors gracefully
        pass
    return True


@register_command(
    name="exit",
    description="Exit interactive mode",
    usage="/exit, /quit",
    aliases=["quit"],
    category="core",
)
def handle_exit_command(command: str) -> bool:
    """Exit the interactive session."""
    from code_puppy.messaging import emit_success

    try:
        emit_success("Goodbye!")
    except Exception:
        # Handle emit errors gracefully
        pass
    # Signal to the main app that we want to exit
    # The actual exit handling is done in main.py
    return True


@register_command(
    name="agent",
    description="Switch to a different agent or show available agents",
    usage="/agent <name>, /a <name>",
    aliases=["a"],
    category="core",
)
def handle_agent_command(command: str) -> bool:
    """Handle agent switching."""
    from code_puppy.agents import (
        get_agent_descriptions,
        get_available_agents,
        get_current_agent,
        set_current_agent,
    )
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()

    if len(tokens) == 1:
        # Show interactive agent picker
        try:
            # Run the async picker using asyncio utilities
            # Since we're called from an async context but this function is sync,
            # we need to carefully schedule and wait for the coroutine
            import asyncio
            import concurrent.futures
            import uuid

            # Create a new event loop in a thread and run the picker there
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(interactive_agent_picker())
                )
                selected_agent = future.result(timeout=300)  # 5 min timeout

            if selected_agent:
                current_agent = get_current_agent()
                # Check if we're already using this agent
                if current_agent.name == selected_agent:
                    group_id = str(uuid.uuid4())
                    emit_info(
                        f"Already using agent: {current_agent.display_name}",
                        message_group=group_id,
                    )
                    return True

                # Switch to the new agent
                group_id = str(uuid.uuid4())
                new_session_id = finalize_autosave_session()
                if not set_current_agent(selected_agent):
                    emit_warning(
                        "Agent switch failed after autosave rotation. Your context was preserved.",
                        message_group=group_id,
                    )
                    return True

                new_agent = get_current_agent()
                new_agent.reload_code_generation_agent()
                emit_success(
                    f"Switched to agent: {new_agent.display_name}",
                    message_group=group_id,
                )
                emit_info(f"[dim]{new_agent.description}[/dim]", message_group=group_id)
                emit_info(
                    f"[dim]Auto-save session rotated to: {new_session_id}[/dim]",
                    message_group=group_id,
                )
            else:
                emit_warning("Agent selection cancelled")
            return True
        except Exception as e:
            # Fallback to old behavior if picker fails
            import traceback
            import uuid

            emit_warning(f"Interactive picker failed: {e}")
            emit_warning(f"Traceback: {traceback.format_exc()}")

            # Show current agent and available agents
            current_agent = get_current_agent()
            available_agents = get_available_agents()
            descriptions = get_agent_descriptions()

            # Generate a group ID for all messages in this command
            group_id = str(uuid.uuid4())

            emit_info(
                f"[bold green]Current Agent:[/bold green] {current_agent.display_name}",
                message_group=group_id,
            )
            emit_info(
                f"[dim]{current_agent.description}[/dim]\n", message_group=group_id
            )

            emit_info(
                "[bold magenta]Available Agents:[/bold magenta]", message_group=group_id
            )
            for name, display_name in available_agents.items():
                description = descriptions.get(name, "No description")
                current_marker = (
                    " [green]← current[/green]" if name == current_agent.name else ""
                )
                emit_info(
                    f"  [cyan]{name:<12}[/cyan] {display_name}{current_marker}",
                    message_group=group_id,
                )
                emit_info(f"    [dim]{description}[/dim]", message_group=group_id)

            emit_info(
                "\n[yellow]Usage:[/yellow] /agent <agent-name>",
                message_group=group_id,
            )
            return True

    elif len(tokens) == 2:
        agent_name = tokens[1].lower()

        # Generate a group ID for all messages in this command
        import uuid

        group_id = str(uuid.uuid4())
        available_agents = get_available_agents()

        if agent_name not in available_agents:
            emit_error(f"Agent '{agent_name}' not found", message_group=group_id)
            emit_warning(
                f"Available agents: {', '.join(available_agents.keys())}",
                message_group=group_id,
            )
            return True

        current_agent = get_current_agent()
        if current_agent.name == agent_name:
            emit_info(
                f"Already using agent: {current_agent.display_name}",
                message_group=group_id,
            )
            return True

        new_session_id = finalize_autosave_session()
        if not set_current_agent(agent_name):
            emit_warning(
                "Agent switch failed after autosave rotation. Your context was preserved.",
                message_group=group_id,
            )
            return True

        new_agent = get_current_agent()
        new_agent.reload_code_generation_agent()
        emit_success(
            f"Switched to agent: {new_agent.display_name}",
            message_group=group_id,
        )
        emit_info(f"[dim]{new_agent.description}[/dim]", message_group=group_id)
        emit_info(
            f"[dim]Auto-save session rotated to: {new_session_id}[/dim]",
            message_group=group_id,
        )
        return True
    else:
        emit_warning("Usage: /agent [agent-name]")
        return True


async def interactive_agent_picker() -> str | None:
    """Show an interactive arrow-key selector to pick an agent (async version).

    Returns:
        The selected agent name, or None if cancelled
    """
    import sys
    import time

    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from code_puppy.agents import (
        get_agent_descriptions,
        get_available_agents,
        get_current_agent,
    )
    from code_puppy.tools.command_runner import set_awaiting_user_input
    from code_puppy.tools.common import arrow_select_async

    # Load available agents
    available_agents = get_available_agents()
    descriptions = get_agent_descriptions()
    current_agent = get_current_agent()

    # Build choices with current agent indicator and keep track of agent names
    choices = []
    agent_names = list(available_agents.keys())
    for agent_name in agent_names:
        display_name = available_agents[agent_name]
        if agent_name == current_agent.name:
            choices.append(f"✓ {agent_name} - {display_name} (current)")
        else:
            choices.append(f"  {agent_name} - {display_name}")

    # Create preview callback to show agent description
    def get_preview(index: int) -> str:
        """Get the description for the agent at the given index."""
        agent_name = agent_names[index]
        description = descriptions.get(agent_name, "No description available")
        return description

    # Create panel content
    panel_content = Text()
    panel_content.append("🐶 Select an agent to use\n", style="bold cyan")
    panel_content.append("Current agent: ", style="dim")
    panel_content.append(f"{current_agent.name}", style="bold green")
    panel_content.append(" - ", style="dim")
    panel_content.append(current_agent.display_name, style="bold green")
    panel_content.append("\n", style="dim")
    panel_content.append(current_agent.description, style="dim italic")

    # Display panel
    panel = Panel(
        panel_content,
        title="[bold white]Agent Selection[/bold white]",
        border_style="cyan",
        padding=(1, 2),
    )

    # Pause spinners BEFORE showing panel
    set_awaiting_user_input(True)
    time.sleep(0.3)  # Let spinners fully stop

    console = Console()
    console.print()
    console.print(panel)
    console.print()

    # Flush output before prompt_toolkit takes control
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(0.1)

    selected_agent = None

    try:
        # Final flush
        sys.stdout.flush()

        # Show arrow-key selector with preview (async version)
        choice = await arrow_select_async(
            "💭 Which agent would you like to use?",
            choices,
            preview_callback=get_preview,
        )

        # Extract agent name from choice (remove prefix and suffix)
        if choice:
            # Remove the "✓ " or "  " prefix and extract agent name (before " - ")
            choice_stripped = choice.strip().lstrip("✓").strip()
            # Split on " - " and take the first part (agent name)
            agent_name = choice_stripped.split(" - ")[0].strip()
            # Remove " (current)" suffix if present
            if agent_name.endswith(" (current)"):
                agent_name = agent_name[:-10].strip()
            selected_agent = agent_name

    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold red]⊗ Cancelled by user[/bold red]")
        selected_agent = None

    finally:
        set_awaiting_user_input(False)

    return selected_agent


async def interactive_model_picker() -> str | None:
    """Show an interactive arrow-key selector to pick a model (async version).

    Returns:
        The selected model name, or None if cancelled
    """
    import sys
    import time

    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from code_puppy.command_line.model_picker_completion import (
        get_active_model,
        load_model_names,
    )
    from code_puppy.tools.command_runner import set_awaiting_user_input
    from code_puppy.tools.common import arrow_select_async

    # Load available models
    model_names = load_model_names()
    current_model = get_active_model()

    # Build choices with current model indicator
    choices = []
    for model_name in model_names:
        if model_name == current_model:
            choices.append(f"✓ {model_name} (current)")
        else:
            choices.append(f"  {model_name}")

    # Create panel content
    panel_content = Text()
    panel_content.append("🤖 Select a model to use\n", style="bold cyan")
    panel_content.append("Current model: ", style="dim")
    panel_content.append(current_model, style="bold green")

    # Display panel
    panel = Panel(
        panel_content,
        title="[bold white]Model Selection[/bold white]",
        border_style="cyan",
        padding=(1, 2),
    )

    # Pause spinners BEFORE showing panel
    set_awaiting_user_input(True)
    time.sleep(0.3)  # Let spinners fully stop

    console = Console()
    console.print()
    console.print(panel)
    console.print()

    # Flush output before prompt_toolkit takes control
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(0.1)

    selected_model = None

    try:
        # Final flush
        sys.stdout.flush()

        # Show arrow-key selector (async version)
        choice = await arrow_select_async(
            "💭 Which model would you like to use?",
            choices,
        )

        # Extract model name from choice (remove prefix and suffix)
        if choice:
            # Remove the "✓ " or "  " prefix and " (current)" suffix if present
            selected_model = choice.strip().lstrip("✓").strip()
            if selected_model.endswith(" (current)"):
                selected_model = selected_model[:-10].strip()

    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold red]⊗ Cancelled by user[/bold red]")
        selected_model = None

    finally:
        set_awaiting_user_input(False)

    return selected_model


@register_command(
    name="model",
    description="Set active model",
    usage="/model, /m <model>",
    aliases=["m"],
    category="core",
)
def handle_model_command(command: str) -> bool:
    """Set the active model."""
    import asyncio

    from code_puppy.command_line.model_picker_completion import (
        get_active_model,
        load_model_names,
        set_active_model,
    )
    from code_puppy.messaging import emit_success, emit_warning

    tokens = command.split()

    # If just /model or /m with no args, show interactive picker
    if len(tokens) == 1:
        try:
            # Run the async picker using asyncio utilities
            # Since we're called from an async context but this function is sync,
            # we need to carefully schedule and wait for the coroutine
            import concurrent.futures

            # Create a new event loop in a thread and run the picker there
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(interactive_model_picker())
                )
                selected_model = future.result(timeout=300)  # 5 min timeout

            if selected_model:
                set_active_model(selected_model)
                emit_success(f"Active model set and loaded: {selected_model}")
            else:
                emit_warning("Model selection cancelled")
            return True
        except Exception as e:
            # Fallback to old behavior if picker fails
            import traceback

            emit_warning(f"Interactive picker failed: {e}")
            emit_warning(f"Traceback: {traceback.format_exc()}")
            model_names = load_model_names()
            emit_warning("Usage: /model <model-name> or /m <model-name>")
            emit_warning(f"Available models: {', '.join(model_names)}")
            return True

    # Handle both /model and /m for backward compatibility
    model_command = command
    if command.startswith("/model"):
        # Convert /model to /m for internal processing
        model_command = command.replace("/model", "/m", 1)

    # If model matched, set it
    new_input = update_model_in_input(model_command)
    if new_input is not None:
        model = get_active_model()
        emit_success(f"Active model set and loaded: {model}")
        return True

    # If no model matched, show error
    model_names = load_model_names()
    emit_warning("Usage: /model <model-name> or /m <model-name>")
    emit_warning(f"Available models: {', '.join(model_names)}")
    return True


@register_command(
    name="mcp",
    description="Manage MCP servers (list, start, stop, status, etc.)",
    usage="/mcp",
    category="core",
)
def handle_mcp_command(command: str) -> bool:
    """Handle MCP server management."""
    from code_puppy.command_line.mcp import MCPCommandHandler

    handler = MCPCommandHandler()
    return handler.handle_mcp_command(command)


@register_command(
    name="generate-pr-description",
    description="Generate comprehensive PR description",
    usage="/generate-pr-description [@dir]",
    category="core",
)
def handle_generate_pr_description_command(command: str) -> str:
    """Generate a PR description."""
    # Parse directory argument (e.g., /generate-pr-description @some/dir)
    tokens = command.split()
    directory_context = ""
    for t in tokens:
        if t.startswith("@"):
            directory_context = f" Please work in the directory: {t[1:]}"
            break

    # Hard-coded prompt from user requirements
    pr_prompt = f"""Generate a comprehensive PR description for my current branch changes. Follow these steps:

 1 Discover the changes: Use git CLI to find the base branch (usually main/master/develop) and get the list of changed files, commits, and diffs.
 2 Analyze the code: Read and analyze all modified files to understand:
    • What functionality was added/changed/removed
    • The technical approach and implementation details
    • Any architectural or design pattern changes
    • Dependencies added/removed/updated
 3 Generate a structured PR description with these sections:
    • Title: Concise, descriptive title (50 chars max)
    • Summary: Brief overview of what this PR accomplishes
    • Changes Made: Detailed bullet points of specific changes
    • Technical Details: Implementation approach, design decisions, patterns used
    • Files Modified: List of key files with brief description of changes
    • Testing: What was tested and how (if applicable)
    • Breaking Changes: Any breaking changes (if applicable)
    • Additional Notes: Any other relevant information
 4 Create a markdown file: Generate a PR_DESCRIPTION.md file with proper GitHub markdown formatting that I can directly copy-paste into GitHub's PR
   description field. Use proper markdown syntax with headers, bullet points, code blocks, and formatting.
 5 Make it review-ready: Ensure the description helps reviewers understand the context, approach, and impact of the changes.
6. If you have Github MCP, or gh cli is installed and authenticated then find the PR for the branch we analyzed and update the PR description there and then delete the PR_DESCRIPTION.md file. (If you have a better name (title) for the PR, go ahead and update the title too.{directory_context}"""

    # Return the prompt to be processed by the main chat system
    return pr_prompt
