"""Command handlers for Code Puppy - CORE commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import os

from code_puppy.command_line.command_registry import register_command
from code_puppy.command_line.model_picker_completion import update_model_in_input
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import finalize_autosave_session
from code_puppy.messaging import emit_error, emit_info
from code_puppy.tools.tools_content import tools_content


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
    from rich.text import Text

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
                emit_info(f"{new_agent.description}", message_group=group_id)
                emit_info(
                    Text.from_markup(
                        f"[dim]Auto-save session rotated to: {new_session_id}[/dim]"
                    ),
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
                Text.from_markup(
                    f"[bold green]Current Agent:[/bold green] {current_agent.display_name}"
                ),
                message_group=group_id,
            )
            emit_info(
                Text.from_markup(f"[dim]{current_agent.description}[/dim]\n"),
                message_group=group_id,
            )

            emit_info(
                Text.from_markup("[bold magenta]Available Agents:[/bold magenta]"),
                message_group=group_id,
            )
            for name, display_name in available_agents.items():
                description = descriptions.get(name, "No description")
                current_marker = (
                    " [green]← current[/green]" if name == current_agent.name else ""
                )
                emit_info(
                    Text.from_markup(
                        f"  [cyan]{name:<12}[/cyan] {display_name}{current_marker}"
                    ),
                    message_group=group_id,
                )
                emit_info(f"    {description}", message_group=group_id)

            emit_info(
                Text.from_markup("\n[yellow]Usage:[/yellow] /agent <agent-name>"),
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
        emit_info(f"{new_agent.description}", message_group=group_id)
        emit_info(
            Text.from_markup(
                f"[dim]Auto-save session rotated to: {new_session_id}[/dim]"
            ),
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

    local_console = Console()
    emit_info("")
    local_console.print(panel)
    emit_info("")

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
        emit_error("Cancelled by user")
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

    local_console = Console()
    emit_info("")
    local_console.print(panel)
    emit_info("")

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
        emit_error("Cancelled by user")
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
    name="add_model",
    description="Browse and add models from models.dev catalog",
    usage="/add_model",
    category="core",
)
def handle_add_model_command(command: str) -> bool:
    """Launch interactive model browser TUI."""
    from code_puppy.command_line.add_model_menu import interactive_model_picker
    from code_puppy.tools.command_runner import set_awaiting_user_input

    set_awaiting_user_input(True)
    try:
        # interactive_model_picker is now synchronous - no async complications!
        result = interactive_model_picker()

        if result:
            emit_info("Successfully added model configuration")
        return True
    except KeyboardInterrupt:
        # User cancelled - this is expected behavior
        return True
    except Exception as e:
        emit_error(f"Failed to launch model browser: {e}")
        return False
    finally:
        set_awaiting_user_input(False)


@register_command(
    name="model_settings",
    description="Configure per-model settings (temperature, seed, etc.)",
    usage="/model_settings [--show [model_name]]",
    aliases=["ms"],
    category="config",
)
def handle_model_settings_command(command: str) -> bool:
    """Launch interactive model settings TUI.

    Opens a TUI showing all available models. Select a model to configure
    its settings (temperature, seed, etc.). ESC closes the TUI.

    Use --show [model_name] to display current settings without the TUI.
    """
    from code_puppy.command_line.model_settings_menu import (
        interactive_model_settings,
        show_model_settings_summary,
    )
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.tools.command_runner import set_awaiting_user_input

    tokens = command.split()

    # Check for --show flag to just display current settings
    if "--show" in tokens:
        model_name = None
        for t in tokens[1:]:
            if not t.startswith("--"):
                model_name = t
                break
        show_model_settings_summary(model_name)
        return True

    set_awaiting_user_input(True)
    try:
        result = interactive_model_settings()

        if result:
            emit_success("Model settings updated successfully")

        # Always reload the active agent so settings take effect
        from code_puppy.agents import get_current_agent

        try:
            current_agent = get_current_agent()
            current_agent.reload_code_generation_agent()
            emit_info("Active agent reloaded")
        except Exception as reload_error:
            emit_warning(f"Agent reload failed: {reload_error}")

        return True
    except KeyboardInterrupt:
        return True
    except Exception as e:
        emit_error(f"Failed to launch model settings: {e}")
        return False
    finally:
        set_awaiting_user_input(False)


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
