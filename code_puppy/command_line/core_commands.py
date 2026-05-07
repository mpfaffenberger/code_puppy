"""Command handlers for Code Puppy - CORE commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import os

from code_puppy.command_line.agent_menu import interactive_agent_picker
from code_puppy.command_line.command_registry import register_command
from code_puppy.command_line.model_picker_completion import (
    interactive_model_picker,
    update_model_in_input,
)
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
    import shlex

    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    try:
        if os.name == "nt":
            # Windows paths commonly use backslashes; POSIX shlex treats them as
            # escape characters and corrupts valid paths (e.g., C:\foo\bar).
            lexer = shlex.shlex(command, posix=False)
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        else:
            tokens = shlex.split(command)
    except ValueError:
        # Keep remaining text as one argument for better resilience.
        tokens = command.split(maxsplit=1)

    if len(tokens) == 1:
        try:
            table = make_directory_table()
            emit_info(table)
        except Exception as e:
            emit_error(f"Error listing directory: {e}")
        return True

    if len(tokens) >= 2:
        # /cd takes one path argument; if tokenizer split extra whitespace,
        # rejoin it so unquoted paths with spaces still have a chance.
        dirname = " ".join(tokens[1:]).strip().strip("\"'")
        target = os.path.expanduser(dirname)
        if not os.path.isabs(target):
            target = os.path.join(os.getcwd(), target)
        if os.path.isdir(target):
            os.chdir(target)
            emit_success(f"Changed directory to: {target}")
            # Reload the agent so the system prompt and project-local
            # AGENT.md rules reflect the new working directory.  Without
            # this, the LLM keeps receiving stale path information for the
            # remainder of the session (the PydanticAgent instructions are
            # baked in at construction time and never refreshed otherwise).
            try:
                from code_puppy.agents.agent_manager import get_current_agent

                get_current_agent().reload_code_generation_agent()
            except Exception as e:
                emit_warning(
                    f"Directory changed, but agent reload failed: {e}. "
                    "You may need to run /agent or /model to force a refresh."
                )
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
    name="paste",
    description="Paste image from clipboard (same as F3, or Ctrl+V with image)",
    usage="/paste, /clipboard, /cb",
    aliases=["clipboard", "cb"],
    category="core",
)
def handle_paste_command(command: str) -> bool:
    """Paste an image from the clipboard into the pending attachments."""
    from code_puppy.command_line.clipboard import (
        capture_clipboard_image_to_pending,
        get_clipboard_manager,
        has_image_in_clipboard,
    )
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    if not has_image_in_clipboard():
        emit_warning("No image found in clipboard")
        emit_info("Copy an image (screenshot, from browser, etc.) and try again")
        return True

    placeholder = capture_clipboard_image_to_pending()
    if placeholder:
        manager = get_clipboard_manager()
        count = manager.get_pending_count()
        emit_success(f"📋 {placeholder}")
        emit_info(f"Total pending clipboard images: {count}")
        emit_info("Type your prompt and press Enter to send with the image(s)")
    else:
        emit_warning("Failed to capture clipboard image")

    return True


@register_command(
    name="tutorial",
    description="Run the interactive tutorial wizard",
    usage="/tutorial",
    category="core",
)
def handle_tutorial_command(command: str) -> bool:
    """Run the interactive tutorial wizard.

    Usage:
        /tutorial  - Run the tutorial (can be run anytime)
    """
    import asyncio
    import concurrent.futures

    from code_puppy.command_line.onboarding_wizard import (
        reset_onboarding,
        run_onboarding_wizard,
    )
    from code_puppy.model_switching import set_model_and_reload_agent

    # Always reset so user can re-run the tutorial anytime
    reset_onboarding()

    # Run the async wizard in a thread pool (same pattern as agent picker)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(run_onboarding_wizard()))
        result = future.result(timeout=300)  # 5 min timeout

    if result == "chatgpt":
        emit_info("🔐 Starting ChatGPT OAuth flow...")
        from code_puppy.plugins.chatgpt_oauth.oauth_flow import run_oauth_flow

        run_oauth_flow()
        set_model_and_reload_agent("chatgpt-gpt-5.4")
    elif result == "claude":
        emit_info("🔐 Starting Claude Code OAuth flow...")
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        set_model_and_reload_agent("claude-code-claude-opus-4-7")
    elif result == "completed":
        emit_info("🎉 Tutorial complete! Happy coding!")
    elif result == "skipped":
        emit_info("⏭️ Tutorial skipped. Run /tutorial anytime!")

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


@register_command(
    name="wiggum",
    description="Loop mode: re-run the same prompt when agent finishes (like Wiggum chasing donuts 🍩)",
    usage="/wiggum <prompt>",
    category="core",
)
def handle_wiggum_command(command: str) -> str | bool:
    """Start wiggum loop mode.

    When active, the agent will automatically re-run the same prompt
    after completing, resetting context each time. Use Ctrl+C to stop.

    Example:
        /wiggum say hello world
    """
    from code_puppy.command_line.wiggum_state import start_wiggum
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    # Extract the prompt after /wiggum
    parts = command.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        emit_warning("Usage: /wiggum <prompt>")
        emit_info("Example: /wiggum say hello world")
        emit_info("This will repeatedly run 'say hello world' after each completion.")
        emit_info("Press Ctrl+C to stop the loop.")
        return True

    prompt = parts[1].strip()

    # Start wiggum mode
    start_wiggum(prompt)
    emit_success("🍩 WIGGUM MODE ACTIVATED!")
    emit_info(f"Prompt: {prompt}")
    emit_info("The agent will re-loop this prompt after each completion.")
    emit_info("Press Ctrl+C to stop the wiggum loop.")

    # Return the prompt to execute immediately
    return prompt


@register_command(
    name="wiggum_stop",
    description="Stop wiggum loop mode",
    usage="/wiggum_stop",
    aliases=["stopwiggum", "ws"],
    category="core",
)
def handle_wiggum_stop_command(command: str) -> bool:
    """Stop wiggum loop mode."""
    from code_puppy.command_line.wiggum_state import is_wiggum_active, stop_wiggum
    from code_puppy.messaging import emit_info, emit_success

    if is_wiggum_active():
        stop_wiggum()
        emit_success("🍩 Wiggum mode stopped!")
    else:
        emit_info("Wiggum mode is not active.")

    return True
