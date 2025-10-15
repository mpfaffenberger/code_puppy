import os
from datetime import datetime
from pathlib import Path

from code_puppy.command_line.model_picker_completion import update_model_in_input
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import (
    CONTEXTS_DIR,
    finalize_autosave_session,
    get_config_keys,
)
from code_puppy.session_storage import list_sessions, load_session, save_session
from code_puppy.tools.tools_content import tools_content


def get_commands_help():
    """Generate aligned commands help using Rich Text for safe markup."""
    from rich.text import Text

    # Ensure plugins are loaded so custom help can register
    _ensure_plugins_loaded()

    # Collect core commands with their syntax parts and descriptions
    # (cmd_syntax, description)
    core_cmds = [
        ("/help, /h", "Show this help message"),
        ("/cd <dir>", "Change directory or show directories"),
        (
            "/agent <name>",
            "Switch to a different agent or show available agents",
        ),
        ("/exit, /quit", "Exit interactive mode"),
        ("/generate-pr-description [@dir]", "Generate comprehensive PR description"),
        ("/model, /m <model>", "Set active model"),
        (
            "/reasoning <low|medium|high>",
            "Set OpenAI reasoning effort for GPT-5 models",
        ),
        ("/pin_model <agent> <model>", "Pin a specific model to an agent"),
        ("/mcp", "Manage MCP servers (list, start, stop, status, etc.)"),
        ("/motd", "Show the latest message of the day (MOTD)"),
        ("/show", "Show puppy config key-values"),
        (
            "/compact",
            "Summarize and compact current chat history (uses compaction_strategy config)",
        ),
        ("/dump_context <name>", "Save current message history to file"),
        ("/load_context <name>", "Load message history from file"),
        (
            "/set",
            "Set puppy config (e.g., /set yolo_mode true, /set auto_save_session true)",
        ),
        ("/tools", "Show available tools and capabilities"),
        (
            "/truncate <N>",
            "Truncate history to N most recent messages (keeping system message)",
        ),
        ("/<unknown>", "Show unknown command warning"),
    ]

    # Determine padding width for the left column
    left_width = max(len(cmd) for cmd, _ in core_cmds) + 2  # add spacing

    lines: list[Text] = []
    lines.append(Text("Commands Help", style="bold magenta"))

    for cmd, desc in core_cmds:
        left = Text(cmd.ljust(left_width), style="cyan")
        right = Text(desc)
        line = Text()
        line.append_text(left)
        line.append_text(right)
        lines.append(line)

    # Add custom commands from plugins (if any)
    try:
        from code_puppy import callbacks

        custom_help_results = callbacks.on_custom_command_help()
        custom_entries: list[tuple[str, str]] = []
        for res in custom_help_results:
            if not res:
                continue
            if isinstance(res, tuple) and len(res) == 2:
                custom_entries.append((str(res[0]), str(res[1])))
            elif isinstance(res, list):
                for item in res:
                    if isinstance(item, tuple) and len(item) == 2:
                        custom_entries.append((str(item[0]), str(item[1])))
        if custom_entries:
            lines.append(Text("", style="dim"))
            lines.append(Text("Custom Commands", style="bold magenta"))
            # Compute padding for custom commands as well
            custom_left_width = max(len(name) for name, _ in custom_entries) + 3
            for name, desc in custom_entries:
                left = Text(f"/{name}".ljust(custom_left_width), style="cyan")
                right = Text(desc)
                line = Text()
                line.append_text(left)
                line.append_text(right)
                lines.append(line)
    except Exception:
        pass

    final_text = Text()
    for i, line in enumerate(lines):
        if i > 0:
            final_text.append("\n")
        final_text.append_text(line)

    return final_text


_PLUGINS_LOADED = False


def _ensure_plugins_loaded() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    try:
        from code_puppy import plugins

        plugins.load_plugin_callbacks()
        _PLUGINS_LOADED = True
    except Exception as e:
        # If plugins fail to load, continue gracefully but note it
        try:
            from code_puppy.messaging import emit_warning

            emit_warning(f"Plugin load error: {e}")
        except Exception:
            pass
        _PLUGINS_LOADED = True


def handle_command(command: str):
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    _ensure_plugins_loaded()

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
        # Functions have been moved to BaseAgent class
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.config import get_compaction_strategy, get_protected_token_count
        from code_puppy.messaging import (
            emit_error,
            emit_info,
            emit_success,
            emit_warning,
        )

        try:
            agent = get_current_agent()
            history = agent.get_message_history()
            if not history:
                emit_warning("No history to compact yet. Ask me something first!")
                return True

            current_agent = get_current_agent()
            before_tokens = sum(
                current_agent.estimate_tokens_for_message(m) for m in history
            )
            compaction_strategy = get_compaction_strategy()
            protected_tokens = get_protected_token_count()
            emit_info(
                f"🤔 Compacting {len(history)} messages using {compaction_strategy} strategy... (~{before_tokens} tokens)"
            )

            current_agent = get_current_agent()
            if compaction_strategy == "truncation":
                compacted = current_agent.truncation(history, protected_tokens)
                summarized_messages = []  # No summarization in truncation mode
            else:
                # Default to summarization
                compacted, summarized_messages = current_agent.summarize_messages(
                    history, with_protection=True
                )

            if not compacted:
                emit_error("Compaction failed. History unchanged.")
                return True

            agent.set_message_history(compacted)

            current_agent = get_current_agent()
            after_tokens = sum(
                current_agent.estimate_tokens_for_message(m) for m in compacted
            )
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
        from code_puppy.agents import get_current_agent
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_compaction_strategy,
            get_compaction_threshold,
            get_openai_reasoning_effort,
            get_owner_name,
            get_protected_token_count,
            get_puppy_name,
            get_yolo_mode,
        )

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        protected_tokens = get_protected_token_count()
        compaction_threshold = get_compaction_threshold()
        compaction_strategy = get_compaction_strategy()

        # Get current agent info
        current_agent = get_current_agent()

        status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]            [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]            [cyan]{owner_name}[/cyan]
[bold]current_agent:[/bold]         [magenta]{current_agent.display_name}[/magenta]
[bold]model:[/bold]                 [green]{model}[/green]
[bold]YOLO_MODE:[/bold]             {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]protected_tokens:[/bold]      [cyan]{protected_tokens:,}[/cyan] recent tokens preserved
[bold]compaction_threshold:[/bold]     [cyan]{compaction_threshold:.1%}[/cyan] context usage triggers compaction
[bold]compaction_strategy:[/bold]   [cyan]{compaction_strategy}[/cyan] (summarization or truncation)
[bold]reasoning_effort:[/bold]      [cyan]{get_openai_reasoning_effort()}[/cyan]

"""
        emit_info(status_msg)
        return True

    if command.startswith("/reasoning"):
        tokens = command.split()
        if len(tokens) != 2:
            emit_warning("Usage: /reasoning <low|medium|high>")
            return True

        effort = tokens[1]
        try:
            from code_puppy.config import set_openai_reasoning_effort

            set_openai_reasoning_effort(effort)
        except ValueError as exc:
            emit_error(str(exc))
            return True

        from code_puppy.config import get_openai_reasoning_effort

        normalized_effort = get_openai_reasoning_effort()

        from code_puppy.agents.agent_manager import get_current_agent

        agent = get_current_agent()
        agent.reload_code_generation_agent()
        emit_success(
            f"Reasoning effort set to '{normalized_effort}' and active agent reloaded"
        )
        return True

    if command.startswith("/session"):
        # /session id -> show current autosave id
        # /session new -> rotate autosave id
        tokens = command.split()
        from code_puppy.config import (
            AUTOSAVE_DIR,
            get_current_autosave_id,
            get_current_autosave_session_name,
            rotate_autosave_id,
        )

        if len(tokens) == 1 or tokens[1] == "id":
            sid = get_current_autosave_id()
            emit_info(
                f"[bold magenta]Autosave Session[/bold magenta]: {sid}\n"
                f"Files prefix: {Path(AUTOSAVE_DIR) / get_current_autosave_session_name()}"
            )
            return True
        if tokens[1] == "new":
            new_sid = rotate_autosave_id()
            emit_success(f"New autosave session id: {new_sid}")
            return True
        emit_warning("Usage: /session [id|new]")
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
            session_help = (
                "\n[yellow]Session Management[/yellow]"
                "\n  [cyan]auto_save_session[/cyan]    Auto-save chat after every response (true/false)"
            )
            emit_warning(
                f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(config_keys)}\n[dim]Note: compaction_strategy can be 'summarization' or 'truncation'[/dim]{session_help}"
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
            get_agent_descriptions,
            get_available_agents,
            get_current_agent,
            set_current_agent,
        )

        tokens = command.split()

        if len(tokens) == 1:
            # Show current agent and available agents
            current_agent = get_current_agent()
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

    if command.startswith("/model") or command.startswith("/m "):
        # Try setting model and show confirmation
        # Handle both /model and /m for backward compatibility
        model_command = command
        if command.startswith("/model"):
            # Convert /model to /m for internal processing
            model_command = command.replace("/model", "/m", 1)

        # If no model matched, show available models
        from code_puppy.command_line.model_picker_completion import load_model_names

        new_input = update_model_in_input(model_command)
        if new_input is not None:
            from code_puppy.command_line.model_picker_completion import get_active_model

            model = get_active_model()
            # Make sure this is called for the test
            emit_success(f"Active model set and loaded: {model}")
            return True
        model_names = load_model_names()
        emit_warning("Usage: /model <model-name> or /m <model-name>")
        emit_warning(f"Available models: {', '.join(model_names)}")
        return True

    if command.startswith("/mcp"):
        from code_puppy.command_line.mcp import MCPCommandHandler

        handler = MCPCommandHandler()
        return handler.handle_mcp_command(command)

    # Built-in help
    if command in ("/help", "/h"):
        import uuid

        group_id = str(uuid.uuid4())
        help_text = get_commands_help()
        emit_info(help_text, message_group_id=group_id)
        return True

    if command.startswith("/pin_model"):
        # Handle agent model pinning
        import json

        from code_puppy.agents.json_agent import discover_json_agents
        from code_puppy.command_line.model_picker_completion import load_model_names

        tokens = command.split()

        if len(tokens) != 3:
            emit_warning("Usage: /pin_model <agent-name> <model-name>")

            # Show available models and agents
            available_models = load_model_names()
            json_agents = discover_json_agents()

            # Get built-in agents
            from code_puppy.agents.agent_manager import get_agent_descriptions

            builtin_agents = get_agent_descriptions()

            emit_info("Available models:")
            for model in available_models:
                emit_info(f"  [cyan]{model}[/cyan]")

            if builtin_agents:
                emit_info("\nAvailable built-in agents:")
                for agent_name, description in builtin_agents.items():
                    emit_info(f"  [cyan]{agent_name}[/cyan] - {description}")

            if json_agents:
                emit_info("\nAvailable JSON agents:")
                for agent_name, agent_path in json_agents.items():
                    emit_info(f"  [cyan]{agent_name}[/cyan] ({agent_path})")
            return True

        agent_name = tokens[1].lower()
        model_name = tokens[2]

        # Check if model exists
        available_models = load_model_names()
        if model_name not in available_models:
            emit_error(f"Model '{model_name}' not found")
            emit_warning(f"Available models: {', '.join(available_models)}")
            return True

        # Check if this is a JSON agent or a built-in Python agent
        json_agents = discover_json_agents()

        # Get list of available built-in agents
        from code_puppy.agents.agent_manager import get_agent_descriptions

        builtin_agents = get_agent_descriptions()

        is_json_agent = agent_name in json_agents
        is_builtin_agent = agent_name in builtin_agents

        if not is_json_agent and not is_builtin_agent:
            emit_error(f"Agent '{agent_name}' not found")

            # Show available agents
            if builtin_agents:
                emit_info("Available built-in agents:")
                for name, desc in builtin_agents.items():
                    emit_info(f"  [cyan]{name}[/cyan] - {desc}")

            if json_agents:
                emit_info("\nAvailable JSON agents:")
                for name, path in json_agents.items():
                    emit_info(f"  [cyan]{name}[/cyan] ({path})")
            return True

        # Handle different agent types
        try:
            if is_json_agent:
                # Handle JSON agent - modify the JSON file
                agent_file_path = json_agents[agent_name]

                with open(agent_file_path, "r", encoding="utf-8") as f:
                    agent_config = json.load(f)

                # Set the model
                agent_config["model"] = model_name

                # Save the updated configuration
                with open(agent_file_path, "w", encoding="utf-8") as f:
                    json.dump(agent_config, f, indent=2, ensure_ascii=False)

            else:
                # Handle built-in Python agent - store in config
                from code_puppy.config import set_agent_pinned_model

                set_agent_pinned_model(agent_name, model_name)

            emit_success(f"Model '{model_name}' pinned to agent '{agent_name}'")

            # If this is the current agent, refresh it so the prompt updates immediately
            from code_puppy.agents import get_current_agent

            current_agent = get_current_agent()
            if current_agent.name == agent_name:
                try:
                    if is_json_agent and hasattr(current_agent, "refresh_config"):
                        current_agent.refresh_config()
                    current_agent.reload_code_generation_agent()
                    emit_info(f"Active agent reloaded with pinned model '{model_name}'")
                except Exception as reload_error:
                    emit_warning(
                        f"Pinned model applied but reload failed: {reload_error}"
                    )

            return True

        except Exception as e:
            emit_error(f"Failed to pin model to agent '{agent_name}': {e}")
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
        from code_puppy.agents.agent_manager import get_current_agent

        tokens = command.split()
        if len(tokens) != 2:
            emit_warning("Usage: /dump_context <session_name>")
            return True

        session_name = tokens[1]
        agent = get_current_agent()
        history = agent.get_message_history()

        if not history:
            emit_warning("No message history to dump!")
            return True

        try:
            metadata = save_session(
                history=history,
                session_name=session_name,
                base_dir=Path(CONTEXTS_DIR),
                timestamp=datetime.now().isoformat(),
                token_estimator=agent.estimate_tokens_for_message,
            )
            emit_success(
                f"✅ Context saved: {metadata.message_count} messages ({metadata.total_tokens} tokens)\n"
                f"📁 Files: {metadata.pickle_path}, {metadata.metadata_path}"
            )
            return True

        except Exception as exc:
            emit_error(f"Failed to dump context: {exc}")
            return True

    if command.startswith("/load_context"):
        from code_puppy.agents.agent_manager import get_current_agent

        tokens = command.split()
        if len(tokens) != 2:
            emit_warning("Usage: /load_context <session_name>")
            return True

        session_name = tokens[1]
        contexts_dir = Path(CONTEXTS_DIR)
        session_path = contexts_dir / f"{session_name}.pkl"

        try:
            history = load_session(session_name, contexts_dir)
        except FileNotFoundError:
            emit_error(f"Context file not found: {session_path}")
            available = list_sessions(contexts_dir)
            if available:
                emit_info(f"Available contexts: {', '.join(available)}")
            return True
        except Exception as exc:
            emit_error(f"Failed to load context: {exc}")
            return True

        agent = get_current_agent()
        agent.set_message_history(history)
        total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)

        # Rotate autosave id to avoid overwriting any existing autosave
        try:
            from code_puppy.config import rotate_autosave_id

            new_id = rotate_autosave_id()
            autosave_info = f"\n[dim]Autosave session rotated to: {new_id}[/dim]"
        except Exception:
            autosave_info = ""

        emit_success(
            f"✅ Context loaded: {len(history)} messages ({total_tokens} tokens)\n"
            f"📁 From: {session_path}{autosave_info}"
        )
        return True

    if command.startswith("/truncate"):
        from code_puppy.agents.agent_manager import get_current_agent

        tokens = command.split()
        if len(tokens) != 2:
            emit_error(
                "Usage: /truncate <N> (where N is the number of messages to keep)"
            )
            return True

        try:
            n = int(tokens[1])
            if n < 1:
                emit_error("N must be a positive integer")
                return True
        except ValueError:
            emit_error("N must be a valid integer")
            return True

        agent = get_current_agent()
        history = agent.get_message_history()
        if not history:
            emit_warning("No history to truncate yet. Ask me something first!")
            return True

        if len(history) <= n:
            emit_info(
                f"History already has {len(history)} messages, which is <= {n}. Nothing to truncate."
            )
            return True

        # Always keep the first message (system message) and then keep the N-1 most recent messages
        truncated_history = (
            [history[0]] + history[-(n - 1) :] if n > 1 else [history[0]]
        )

        agent.set_message_history(truncated_history)
        emit_success(
            f"Truncated message history from {len(history)} to {len(truncated_history)} messages (keeping system message and {n - 1} most recent)"
        )
        return True

    if command in ("/exit", "/quit"):
        emit_success("Goodbye!")
        # Signal to the main app that we want to exit
        # The actual exit handling is done in main.py
        return True

    # Try plugin-provided custom commands before unknown warning
    if command.startswith("/"):
        # Extract command name without leading slash and arguments intact
        name = command[1:].split()[0] if len(command) > 1 else ""
        try:
            from code_puppy import callbacks

            results = callbacks.on_custom_command(command=command, name=name)
            # Iterate through callback results; treat str as handled (no model run)
            for res in results:
                if res is True:
                    return True
                if isinstance(res, str):
                    # Display returned text to the user and treat as handled
                    try:
                        emit_info(res)
                    except Exception:
                        pass
                    return True
        except Exception as e:
            # Log via emit_error but do not block default handling
            emit_warning(f"Custom command hook error: {e}")

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
