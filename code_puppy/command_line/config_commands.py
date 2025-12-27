"""Command handlers for Code Puppy - CONFIG commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import json

from code_puppy.command_line.command_registry import register_command
from code_puppy.config import get_config_keys


# Import get_commands_help from command_handler to avoid circular imports
# This will be defined in command_handler.py
def get_commands_help():
    """Lazy import to avoid circular dependency."""
    from code_puppy.command_line.command_handler import get_commands_help as _gch

    return _gch()


@register_command(
    name="show",
    description="Show puppy config key-values",
    usage="/show",
    category="config",
)
def handle_show_command(command: str) -> bool:
    """Show current puppy configuration."""
    from rich.text import Text

    from code_puppy.agents import get_current_agent
    from code_puppy.command_line.model_picker_completion import get_active_model
    from code_puppy.config import (
        get_auto_save_session,
        get_compaction_strategy,
        get_compaction_threshold,
        get_default_agent,
        get_effective_temperature,
        get_openai_reasoning_effort,
        get_openai_verbosity,
        get_owner_name,
        get_protected_token_count,
        get_puppy_name,
        get_temperature,
        get_use_dbos,
        get_yolo_mode,
    )
    from code_puppy.keymap import get_cancel_agent_key, get_cancel_agent_display_name
    from code_puppy.messaging import emit_info

    puppy_name = get_puppy_name()
    owner_name = get_owner_name()
    model = get_active_model()
    yolo_mode = get_yolo_mode()
    auto_save = get_auto_save_session()
    protected_tokens = get_protected_token_count()
    compaction_threshold = get_compaction_threshold()
    compaction_strategy = get_compaction_strategy()
    global_temperature = get_temperature()
    effective_temperature = get_effective_temperature(model)

    # Get current agent info
    current_agent = get_current_agent()
    default_agent = get_default_agent()

    status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]            [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]            [cyan]{owner_name}[/cyan]
[bold]current_agent:[/bold]         [magenta]{current_agent.display_name}[/magenta]
[bold]default_agent:[/bold]        [cyan]{default_agent}[/cyan]
[bold]model:[/bold]                 [green]{model}[/green]
[bold]YOLO_MODE:[/bold]             {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]DBOS:[/bold]                  {"[green]enabled[/green]" if get_use_dbos() else "[yellow]disabled[/yellow]"} (toggle: /set enable_dbos true|false)
[bold]auto_save_session:[/bold]     {"[green]enabled[/green]" if auto_save else "[yellow]disabled[/yellow]"}
[bold]protected_tokens:[/bold]      [cyan]{protected_tokens:,}[/cyan] recent tokens preserved
[bold]compaction_threshold:[/bold]     [cyan]{compaction_threshold:.1%}[/cyan] context usage triggers compaction
[bold]compaction_strategy:[/bold]   [cyan]{compaction_strategy}[/cyan] (summarization or truncation)
[bold]reasoning_effort:[/bold]      [cyan]{get_openai_reasoning_effort()}[/cyan]
[bold]verbosity:[/bold]             [cyan]{get_openai_verbosity()}[/cyan]
[bold]temperature:[/bold]           [cyan]{effective_temperature if effective_temperature is not None else "(model default)"}[/cyan]{" (per-model)" if effective_temperature != global_temperature and effective_temperature is not None else ""}
[bold]cancel_agent_key:[/bold]      [cyan]{get_cancel_agent_display_name()}[/cyan] (options: ctrl+c, ctrl+k, ctrl+q)

"""
    emit_info(Text.from_markup(status_msg))
    return True


@register_command(
    name="reasoning",
    description="Set OpenAI reasoning effort for GPT-5 models (e.g., /reasoning high)",
    usage="/reasoning <minimal|low|medium|high|xhigh>",
    category="config",
)
def handle_reasoning_command(command: str) -> bool:
    """Set OpenAI reasoning effort level."""
    from code_puppy.messaging import emit_error, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning("Usage: /reasoning <minimal|low|medium|high|xhigh>")
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


@register_command(
    name="verbosity",
    description="Set OpenAI verbosity for GPT-5 models (e.g., /verbosity high)",
    usage="/verbosity <low|medium|high>",
    category="config",
)
def handle_verbosity_command(command: str) -> bool:
    """Set OpenAI verbosity level.

    Controls how concise vs. verbose the model's responses are:
    - low: more concise responses
    - medium: balanced (default)
    - high: more verbose responses
    """
    from code_puppy.messaging import emit_error, emit_success, emit_warning

    tokens = command.split()
    if len(tokens) != 2:
        emit_warning("Usage: /verbosity <low|medium|high>")
        return True

    verbosity = tokens[1]
    try:
        from code_puppy.config import set_openai_verbosity

        set_openai_verbosity(verbosity)
    except ValueError as exc:
        emit_error(str(exc))
        return True

    from code_puppy.config import get_openai_verbosity

    normalized_verbosity = get_openai_verbosity()

    from code_puppy.agents.agent_manager import get_current_agent

    agent = get_current_agent()
    agent.reload_code_generation_agent()
    emit_success(f"Verbosity set to '{normalized_verbosity}' and active agent reloaded")
    return True


@register_command(
    name="set",
    description="Set puppy config (e.g., /set yolo_mode true)",
    usage="/set <key> <value>",
    category="config",
)
def handle_set_command(command: str) -> bool:
    """Set configuration values."""
    from rich.text import Text

    from code_puppy.config import set_config_value
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

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
        keymap_help = (
            "\n[yellow]Keyboard Shortcuts[/yellow]"
            "\n  [cyan]cancel_agent_key[/cyan]     Key to cancel agent tasks (ctrl+c, ctrl+k, or ctrl+q)"
        )
        emit_warning(
            Text.from_markup(
                f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(config_keys)}\n[dim]Note: compaction_strategy can be 'summarization' or 'truncation'[/dim]{session_help}{keymap_help}"
            )
        )
        return True
    if key:
        # Check if we're toggling DBOS enablement
        if key == "enable_dbos":
            emit_info(
                Text.from_markup(
                    "[yellow]⚠️ DBOS configuration changed. Please restart Code Puppy for this change to take effect.[/yellow]"
                )
            )

        # Validate cancel_agent_key before setting
        if key == "cancel_agent_key":
            from code_puppy.keymap import VALID_CANCEL_KEYS

            normalized_value = value.strip().lower()
            if normalized_value not in VALID_CANCEL_KEYS:
                emit_error(
                    f"Invalid cancel_agent_key '{value}'. Valid options: {', '.join(sorted(VALID_CANCEL_KEYS))}"
                )
                return True
            value = normalized_value  # Use normalized value
            emit_info(
                Text.from_markup(
                    "[yellow]⚠️ cancel_agent_key changed. Please restart Code Puppy for this change to take effect.[/yellow]"
                )
            )

        set_config_value(key, value)
        emit_success(f'Set {key} = "{value}" in puppy.cfg!')

        # Reload the current agent to pick up the new config
        from code_puppy.agents import get_current_agent

        try:
            current_agent = get_current_agent()
            current_agent.reload_code_generation_agent()
            emit_info("Agent reloaded with updated config")
        except Exception as reload_error:
            emit_warning(f"Config saved but agent reload failed: {reload_error}")
    else:
        emit_error("You must supply a key.")
    return True


def _get_json_agents_pinned_to_model(model_name: str) -> list:
    """Get JSON agents that have this model pinned in their JSON file."""
    from code_puppy.agents.json_agent import discover_json_agents

    pinned = []
    json_agents = discover_json_agents()
    for agent_name, agent_path in json_agents.items():
        try:
            with open(agent_path, "r") as f:
                agent_data = json.load(f)
                if agent_data.get("model") == model_name:
                    pinned.append(agent_name)
        except Exception:
            continue
    return pinned


@register_command(
    name="pin_model",
    description="Pin a specific model to an agent",
    usage="/pin_model <agent> <model>",
    category="config",
)
def handle_pin_model_command(command: str) -> bool:
    """Pin a specific model to an agent."""
    from code_puppy.agents.json_agent import discover_json_agents
    from code_puppy.command_line.model_picker_completion import load_model_names
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

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
            emit_info(f"  {model}")

        if builtin_agents:
            emit_info("\nAvailable built-in agents:")
            for agent_name, description in builtin_agents.items():
                emit_info(f"  {agent_name} - {description}")

        if json_agents:
            emit_info("\nAvailable JSON agents:")
            for agent_name, agent_path in json_agents.items():
                emit_info(f"  {agent_name} ({agent_path})")
        return True

    agent_name = tokens[1].lower()
    model_name = tokens[2]

    # Handle special case: (unpin) option (case-insensitive)
    if model_name.lower() == "(unpin)":
        # Delegate to unpin command
        return handle_unpin_command(f"/unpin {agent_name}")

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
                emit_info(f"  {name} - {desc}")

        if json_agents:
            emit_info("\nAvailable JSON agents:")
            for name, path in json_agents.items():
                emit_info(f"  {name} ({path})")
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
                emit_warning(f"Pinned model applied but reload failed: {reload_error}")

        return True

    except Exception as e:
        emit_error(f"Failed to pin model to agent '{agent_name}': {e}")
        return True


@register_command(
    name="unpin",
    description="Unpin a model from an agent (resets to default)",
    usage="/unpin <agent>",
    category="config",
)
def handle_unpin_command(command: str) -> bool:
    """Unpin a model from an agent (resets to default)."""
    from code_puppy.agents.json_agent import discover_json_agents
    from code_puppy.config import get_agent_pinned_model
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()

    if len(tokens) != 2:
        emit_warning("Usage: /unpin <agent-name>")

        # Show available agents
        json_agents = discover_json_agents()

        # Get built-in agents
        from code_puppy.agents.agent_manager import get_agent_descriptions

        builtin_agents = get_agent_descriptions()

        if builtin_agents:
            emit_info("Available built-in agents:")
            for agent_name, description in builtin_agents.items():
                pinned_model = get_agent_pinned_model(agent_name)
                if pinned_model:
                    emit_info(f"  {agent_name} - {description} [→ {pinned_model}]")
                else:
                    emit_info(f"  {agent_name} - {description}")

        if json_agents:
            emit_info("\nAvailable JSON agents:")
            for agent_name, agent_path in json_agents.items():
                # Read the JSON file to check for pinned model
                try:
                    with open(agent_path, "r") as f:
                        agent_config = json.load(f)
                    pinned_model = agent_config.get("model")
                    if pinned_model:
                        emit_info(f"  {agent_name} ({agent_path}) [→ {pinned_model}]")
                    else:
                        emit_info(f"  {agent_name} ({agent_path})")
                except Exception:
                    emit_info(f"  {agent_name} ({agent_path})")
        return True

    agent_name_input = tokens[1].lower()

    # Check if this is a JSON agent or a built-in Python agent
    json_agents = discover_json_agents()

    # Get list of available built-in agents
    from code_puppy.agents.agent_manager import get_agent_descriptions

    builtin_agents = get_agent_descriptions()

    # Find matching agent (case-insensitive)
    agent_name = None
    is_json_agent = False
    is_builtin_agent = False

    # Check JSON agents (case-insensitive)
    for json_agent_name in json_agents:
        if json_agent_name.lower() == agent_name_input:
            agent_name = json_agent_name
            is_json_agent = True
            break

    # Check built-in agents (case-insensitive)
    if not is_json_agent:
        for builtin_agent_name in builtin_agents:
            if builtin_agent_name.lower() == agent_name_input:
                agent_name = builtin_agent_name
                is_builtin_agent = True
                break

    if not is_json_agent and not is_builtin_agent:
        emit_error(f"Agent '{agent_name_input}' not found")

        # Show available agents
        if builtin_agents:
            emit_info("Available built-in agents:")
            for name, desc in builtin_agents.items():
                emit_info(f"  {name} - {desc}")

        if json_agents:
            emit_info("\nAvailable JSON agents:")
            for name, path in json_agents.items():
                emit_info(f"  {name} ({path})")
        return True

    try:
        if is_json_agent:
            # Handle JSON agent - remove the model from JSON file
            agent_file_path = json_agents[agent_name]

            with open(agent_file_path, "r", encoding="utf-8") as f:
                agent_config = json.load(f)

            # Remove the model key if it exists
            if "model" in agent_config:
                del agent_config["model"]

            # Save the updated configuration
            with open(agent_file_path, "w", encoding="utf-8") as f:
                json.dump(agent_config, f, indent=2, ensure_ascii=False)

        else:
            # Handle built-in Python agent - clear from config
            from code_puppy.config import clear_agent_pinned_model

            clear_agent_pinned_model(agent_name)

        emit_success(f"Model unpinned from agent '{agent_name}' (reset to default)")

        # If this is the current agent, refresh it so the prompt updates immediately
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        if current_agent.name == agent_name:
            try:
                if is_json_agent and hasattr(current_agent, "refresh_config"):
                    current_agent.refresh_config()
                current_agent.reload_code_generation_agent()
                emit_info("Active agent reloaded with default model")
            except Exception as reload_error:
                emit_warning(f"Model unpinned but reload failed: {reload_error}")

        return True

    except Exception as e:
        emit_error(f"Failed to unpin model from agent '{agent_name}': {e}")
        return True


@register_command(
    name="diff",
    description="Configure diff highlighting colors (additions, deletions)",
    usage="/diff",
    category="config",
)
def handle_diff_command(command: str) -> bool:
    """Configure diff highlighting colors."""
    import asyncio
    import concurrent.futures

    from code_puppy.command_line.diff_menu import interactive_diff_picker
    from code_puppy.config import (
        set_diff_addition_color,
        set_diff_deletion_color,
    )
    from code_puppy.messaging import emit_error

    # Show interactive picker for diff configuration
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_diff_picker()))
        result = future.result(timeout=300)  # 5 min timeout

    if result:
        # Apply the changes silently (no console output)
        try:
            set_diff_addition_color(result["add_color"])
            set_diff_deletion_color(result["del_color"])
        except Exception as e:
            emit_error(f"Failed to apply diff settings: {e}")
    return True


@register_command(
    name="colors",
    description="Configure banner colors for tool outputs (THINKING, SHELL COMMAND, etc.)",
    usage="/colors",
    category="config",
)
def handle_colors_command(command: str) -> bool:
    """Configure banner colors via interactive TUI."""
    import asyncio
    import concurrent.futures

    from code_puppy.command_line.colors_menu import interactive_colors_picker
    from code_puppy.config import set_banner_color
    from code_puppy.messaging import emit_error, emit_success

    # Show interactive picker for banner color configuration
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_colors_picker()))
        result = future.result(timeout=300)  # 5 min timeout

    if result:
        # Apply the changes
        try:
            for banner_name, color in result.items():
                set_banner_color(banner_name, color)
            emit_success("Banner colors saved! 🎨")
        except Exception as e:
            emit_error(f"Failed to apply banner color settings: {e}")
    return True


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _show_color_options(color_type: str):
    # ============================================================================
    # UTILITY FUNCTIONS
    # ============================================================================

    """Show available Rich color options organized by category."""
    from rich.text import Text

    from code_puppy.messaging import emit_info

    # Standard Rich colors organized by category
    color_categories = {
        "Basic Colors": [
            ("black", "⚫"),
            ("red", "🔴"),
            ("green", "🟢"),
            ("yellow", "🟡"),
            ("blue", "🔵"),
            ("magenta", "🟣"),
            ("cyan", "🔷"),
            ("white", "⚪"),
        ],
        "Bright Colors": [
            ("bright_black", "⚫"),
            ("bright_red", "🔴"),
            ("bright_green", "🟢"),
            ("bright_yellow", "🟡"),
            ("bright_blue", "🔵"),
            ("bright_magenta", "🟣"),
            ("bright_cyan", "🔷"),
            ("bright_white", "⚪"),
        ],
        "Special Colors": [
            ("orange1", "🟠"),
            ("orange3", "🟠"),
            ("orange4", "🟠"),
            ("deep_sky_blue1", "🔷"),
            ("deep_sky_blue2", "🔷"),
            ("deep_sky_blue3", "🔷"),
            ("deep_sky_blue4", "🔷"),
            ("turquoise2", "🔷"),
            ("turquoise4", "🔷"),
            ("steel_blue1", "🔷"),
            ("steel_blue3", "🔷"),
            ("chartreuse1", "🟢"),
            ("chartreuse2", "🟢"),
            ("chartreuse3", "🟢"),
            ("chartreuse4", "🟢"),
            ("gold1", "🟡"),
            ("gold3", "🟡"),
            ("rosy_brown", "🔴"),
            ("indian_red", "🔴"),
        ],
    }

    # Suggested colors for each type
    if color_type == "additions":
        suggestions = [
            ("green", "🟢"),
            ("bright_green", "🟢"),
            ("chartreuse1", "🟢"),
            ("green3", "🟢"),
            ("sea_green1", "🟢"),
        ]
        emit_info(
            Text.from_markup(
                "[bold white on green]🎨 Recommended Colors for Additions:[/bold white on green]"
            )
        )
        for color, emoji in suggestions:
            emit_info(
                Text.from_markup(
                    f"  [cyan]{color:<16}[/cyan] [white on {color}]■■■■■■■■■■[/white on {color}] {emoji}"
                )
            )
    elif color_type == "deletions":
        suggestions = [
            ("orange1", "🟠"),
            ("red", "🔴"),
            ("bright_red", "🔴"),
            ("indian_red", "🔴"),
            ("dark_red", "🔴"),
        ]
        emit_info(
            Text.from_markup(
                "[bold white on orange1]🎨 Recommended Colors for Deletions:[/bold white on orange1]"
            )
        )
        for color, emoji in suggestions:
            emit_info(
                Text.from_markup(
                    f"  [cyan]{color:<16}[/cyan] [white on {color}]■■■■■■■■■■[/white on {color}] {emoji}"
                )
            )

    emit_info("\n🎨 All Available Rich Colors:")
    for category, colors in color_categories.items():
        emit_info(f"\n{category}:")
        # Display in columns for better readability
        for i in range(0, len(colors), 4):
            row = colors[i : i + 4]
            row_text = "  ".join([f"[{color}]■[/{color}] {color}" for color, _ in row])
            emit_info(Text.from_markup(f"  {row_text}"))

    emit_info("\nUsage: /diff {color_type} <color_name>")
    emit_info("All diffs use white text on your chosen background colors")
    emit_info("You can also use hex colors like #ff0000 or rgb(255,0,0)")
