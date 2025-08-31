import os

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import get_config_keys
from code_puppy.tools.tools_content import tools_content

def get_commands_help():
    """Generate commands help using Rich Text objects to avoid markup conflicts."""
    from rich.text import Text
    
    # Build help text programmatically
    help_lines = []
    
    # Title
    help_lines.append(Text("Commands Help", style="bold magenta"))
    
    # Commands - build each line programmatically  
    help_lines.append(Text("/help, /h", style="cyan") + Text("             Show this help message"))
    help_lines.append(Text("/cd", style="cyan") + Text(" <dir>             Change directory or show directories"))
    help_lines.append(Text("/agent", style="cyan") + Text(" <name>         Switch to a different agent or show available agents"))
    help_lines.append(Text("/exit, /quit", style="cyan") + Text("          Exit interactive mode"))
    help_lines.append(Text("/generate-pr-description", style="cyan") + Text(" [@dir]  Generate comprehensive PR description"))
    help_lines.append(Text("/model", style="cyan") + Text(" <model>        Set active model"))
    help_lines.append(Text("/mcp", style="cyan") + Text("                  Manage MCP servers (list, start, stop, status, etc.)"))
    help_lines.append(Text("/motd", style="cyan") + Text("                 Show the latest message of the day (MOTD)"))
    help_lines.append(Text("/show", style="cyan") + Text("                 Show puppy config key-values"))
    help_lines.append(Text("/compact", style="cyan") + Text("              Summarize and compact current chat history"))
    help_lines.append(Text("/dump_context", style="cyan") + Text(" <name>  Save current message history to file"))
    help_lines.append(Text("/load_context", style="cyan") + Text(" <name>  Load message history from file"))
    help_lines.append(Text("/set", style="cyan") + Text("                  Set puppy config key-values (e.g., /set yolo_mode true, /set compaction_strategy truncation)"))
    help_lines.append(Text("/tools", style="cyan") + Text("                Show available tools and capabilities"))
    help_lines.append(Text("/<unknown>", style="cyan") + Text("            Show unknown command warning"))
    
    
    # Combine all lines
    final_text = Text()
    for i, line in enumerate(help_lines):
        if i > 0:
            final_text.append("\n")
        final_text.append_text(line)
    
    return final_text


def handle_command(command: str):
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    """
    Handle commands prefixed with '/'.

    Args:
        command: The command string to handle

    Returns:
        True if the command was handled, False if not, or a string to be processed as user input
    """
    command = command.strip()

    if command.strip().startswith("/motd"):
        print_motd(force=True)
        return True

    if command.strip().startswith("/compact"):
        from code_puppy.config import get_compaction_strategy
        from code_puppy.message_history_processor import (
            estimate_tokens_for_message,
            summarize_messages,
            truncation,
            get_protected_token_count,
        )
        from code_puppy.messaging import (
            emit_error,
            emit_info,
            emit_success,
            emit_warning,
        )
        from code_puppy.state_management import get_message_history, set_message_history

        try:
            history = get_message_history()
            if not history:
                emit_warning("No history to compact yet. Ask me something first!")
                return True

            before_tokens = sum(estimate_tokens_for_message(m) for m in history)
            compaction_strategy = get_compaction_strategy()
            emit_info(
                f"🤔 Compacting {len(history)} messages using {compaction_strategy} strategy... (~{before_tokens} tokens)"
            )

            if compaction_strategy == "truncation":
                protected_tokens = get_protected_token_count()
                compacted = truncation(history, protected_tokens)
                summarized_messages = []  # No summarization in truncation mode
            else:
                # Default to summarization
                compacted, summarized_messages = summarize_messages(
                    history, with_protection=False
                )

            if not compacted:
                emit_error("Compaction failed. History unchanged.")
                return True

            set_message_history(compacted)

            after_tokens = sum(estimate_tokens_for_message(m) for m in compacted)
            reduction_pct = (
                ((before_tokens - after_tokens) / before_tokens * 100)
                if before_tokens > 0
                else 0
            )

            strategy_info = (
                f"using {compaction_strategy} strategy"
                if compaction_strategy == "truncation"
                else "via summarization"
            )
            emit_success(
                f"✨ Done! History: {len(history)} → {len(compacted)} messages {strategy_info}\n"
                f"🏦 Tokens: {before_tokens:,} → {after_tokens:,} ({reduction_pct:.1f}% reduction)"
            )
            return True
        except Exception as e:
            emit_error(f"/compact error: {e}")
            return True

    if command.startswith("/cd"):
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

    if command.strip().startswith("/show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_owner_name,
            get_protected_token_count,
            get_puppy_name,
            get_compaction_threshold,
            get_yolo_mode,
        )
        from code_puppy.agents import get_current_agent_config

        from code_puppy.config import get_compaction_strategy

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        protected_tokens = get_protected_token_count()
        compaction_threshold = get_compaction_threshold()
        compaction_strategy = get_compaction_strategy()

        # Get current agent info
        current_agent = get_current_agent_config()

        status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]            [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]            [cyan]{owner_name}[/cyan]
[bold]current_agent:[/bold]         [magenta]{current_agent.display_name}[/magenta]
[bold]model:[/bold]                 [green]{model}[/green]
[bold]YOLO_MODE:[/bold]             {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]protected_tokens:[/bold]      [cyan]{protected_tokens:,}[/cyan] recent tokens preserved
[bold]compaction_threshold:[/bold]     [cyan]{compaction_threshold:.1%}[/cyan] context usage triggers compaction
[bold]compaction_strategy:[/bold]   [cyan]{compaction_strategy}[/cyan] (summarization or truncation)

"""
        emit_info(status_msg)
        return True

    if command.startswith("/set"):
        # Syntax: /set KEY=VALUE or /set KEY VALUE
        from code_puppy.config import set_config_value

        tokens = command.split(None, 2)
        argstr = command[len("/set") :].strip()
        key = None
        value = None
        if "=" in argstr:
            key, value = argstr.split("=", 1)
            key = key.strip()
            value = value.strip()
        elif len(tokens) >= 3:
            key = tokens[1]
            value = tokens[2]
        elif len(tokens) == 2:
            key = tokens[1]
            value = ""
        else:
            config_keys = get_config_keys()
            if "compaction_strategy" not in config_keys:
                config_keys.append("compaction_strategy")
            emit_warning(
                f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(config_keys)}\n[dim]Note: compaction_strategy can be 'summarization' or 'truncation'[/dim]"
            )
            return True
        if key:
            set_config_value(key, value)
            emit_success(f'🌶 Set {key} = "{value}" in puppy.cfg!')
        else:
            emit_error("You must supply a key.")
        return True

    if command.startswith("/tools"):
        # Display the tools_content.py file content with markdown formatting
        from rich.markdown import Markdown

        markdown_content = Markdown(tools_content)
        emit_info(markdown_content)
        return True

    if command.startswith("/agent"):
        # Handle agent switching
        from code_puppy.agents import (
            get_available_agents,
            get_current_agent_config,
            set_current_agent,
            get_agent_descriptions,
        )
        from code_puppy.agents.runtime_manager import get_runtime_agent_manager

        tokens = command.split()

        if len(tokens) == 1:
            # Show current agent and available agents
            current_agent = get_current_agent_config()
            available_agents = get_available_agents()
            descriptions = get_agent_descriptions()

            # Generate a group ID for all messages in this command
            import uuid

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
                "\n[yellow]Usage:[/yellow] /agent <agent-name>", message_group=group_id
            )
            return True

        elif len(tokens) == 2:
            agent_name = tokens[1].lower()

            # Generate a group ID for all messages in this command
            import uuid

            group_id = str(uuid.uuid4())

            if set_current_agent(agent_name):
                # Reload the agent with new configuration
                manager = get_runtime_agent_manager()
                manager.reload_agent()
                new_agent = get_current_agent_config()
                emit_success(
                    f"Switched to agent: {new_agent.display_name}",
                    message_group=group_id,
                )
                emit_info(f"[dim]{new_agent.description}[/dim]", message_group=group_id)
                return True
            else:
                # Generate a group ID for all messages in this command
                import uuid

                group_id = str(uuid.uuid4())

                available_agents = get_available_agents()
                emit_error(f"Agent '{agent_name}' not found", message_group=group_id)
                emit_warning(
                    f"Available agents: {', '.join(available_agents.keys())}",
                    message_group=group_id,
                )
                return True
        else:
            emit_warning("Usage: /agent [agent-name]")
            return True

    if command.startswith("/model"):
        # Try setting model and show confirmation
        # Handle both /model and /m for backward compatibility
        model_command = command.replace("/model", "/m") if command.startswith("/model") else command
        new_input = update_model_in_input(model_command)
        if new_input is not None:
            from code_puppy.agents.runtime_manager import get_runtime_agent_manager
            from code_puppy.command_line.model_picker_completion import get_active_model

            model = get_active_model()
            # Make sure this is called for the test
            manager = get_runtime_agent_manager()
            manager.reload_agent()
            emit_success(f"Active model set and loaded: {model}")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        emit_warning("Usage: /model <model-name>")
        emit_warning(f"Available models: {', '.join(model_names)}")
        return True
    
    if command.startswith("/mcp"):
        from code_puppy.command_line.mcp_commands import MCPCommandHandler
        handler = MCPCommandHandler()
        return handler.handle_mcp_command(command)
    if command in ("/help", "/h"):
        import uuid
        group_id = str(uuid.uuid4())
        help_text = get_commands_help()
        emit_info(help_text, message_group_id=group_id)
        return True

    if command.startswith("/generate-pr-description"):
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

    if command.startswith("/dump_context"):
        import json
        import pickle
        from datetime import datetime
        from pathlib import Path

        from code_puppy.config import CONFIG_DIR
        from code_puppy.message_history_processor import estimate_tokens_for_message
        from code_puppy.state_management import get_message_history

        tokens = command.split()
        if len(tokens) != 2:
            emit_warning("Usage: /dump_context <session_name>")
            return True

        session_name = tokens[1]
        history = get_message_history()

        if not history:
            emit_warning("No message history to dump!")
            return True

        # Create contexts directory inside CONFIG_DIR if it doesn't exist
        contexts_dir = Path(CONFIG_DIR) / "contexts"
        contexts_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Save as pickle for exact preservation
            pickle_file = contexts_dir / f"{session_name}.pkl"
            with open(pickle_file, "wb") as f:
                pickle.dump(history, f)

            # Also save metadata as JSON for readability
            meta_file = contexts_dir / f"{session_name}_meta.json"
            metadata = {
                "session_name": session_name,
                "timestamp": datetime.now().isoformat(),
                "message_count": len(history),
                "total_tokens": sum(estimate_tokens_for_message(m) for m in history),
                "file_path": str(pickle_file),
            }

            with open(meta_file, "w") as f:
                json.dump(metadata, f, indent=2)

            emit_success(
                f"✅ Context saved: {len(history)} messages ({metadata['total_tokens']} tokens)\n"
                f"📁 Files: {pickle_file}, {meta_file}"
            )
            return True

        except Exception as e:
            emit_error(f"Failed to dump context: {e}")
            return True

    if command.startswith("/load_context"):
        import pickle
        from pathlib import Path

        from code_puppy.config import CONFIG_DIR
        from code_puppy.message_history_processor import estimate_tokens_for_message
        from code_puppy.state_management import set_message_history

        tokens = command.split()
        if len(tokens) != 2:
            emit_warning("Usage: /load_context <session_name>")
            return True

        session_name = tokens[1]
        contexts_dir = Path(CONFIG_DIR) / "contexts"
        pickle_file = contexts_dir / f"{session_name}.pkl"

        if not pickle_file.exists():
            emit_error(f"Context file not found: {pickle_file}")
            # List available contexts
            available = list(contexts_dir.glob("*.pkl"))
            if available:
                names = [f.stem for f in available]
                emit_info(f"Available contexts: {', '.join(names)}")
            return True

        try:
            with open(pickle_file, "rb") as f:
                history = pickle.load(f)

            set_message_history(history)
            total_tokens = sum(estimate_tokens_for_message(m) for m in history)

            emit_success(
                f"✅ Context loaded: {len(history)} messages ({total_tokens} tokens)\n"
                f"📁 From: {pickle_file}"
            )
            return True

        except Exception as e:
            emit_error(f"Failed to load context: {e}")
            return True

    if command in ("/exit", "/quit"):
        emit_success("Goodbye!")
        # Signal to the main app that we want to exit
        # The actual exit handling is done in main.py
        return True
    if command.startswith("/"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            emit_warning(
                f"Unknown command: {command}\n[dim]Type /help for options.[/dim]"
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            emit_info(
                f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
            )
        return True

    return False
