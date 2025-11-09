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
    from code_puppy.agents import get_current_agent
    from code_puppy.command_line.model_picker_completion import get_active_model
    from code_puppy.config import (
        get_auto_save_session,
        get_compaction_strategy,
        get_compaction_threshold,
        get_default_agent,
        get_openai_reasoning_effort,
        get_owner_name,
        get_protected_token_count,
        get_puppy_name,
        get_use_dbos,
        get_yolo_mode,
    )
    from code_puppy.messaging import emit_info

    puppy_name = get_puppy_name()
    owner_name = get_owner_name()
    model = get_active_model()
    yolo_mode = get_yolo_mode()
    auto_save = get_auto_save_session()
    protected_tokens = get_protected_token_count()
    compaction_threshold = get_compaction_threshold()
    compaction_strategy = get_compaction_strategy()

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

"""
    emit_info(status_msg)
    return True


@register_command(
    name="reasoning",
    description="Set OpenAI reasoning effort for GPT-5 models (e.g., /reasoning high)",
    usage="/reasoning <low|medium|high>",
    category="config",
)
def handle_reasoning_command(command: str) -> bool:
    """Set OpenAI reasoning effort level."""
    from code_puppy.messaging import emit_error, emit_success, emit_warning

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


@register_command(
    name="set",
    description="Set puppy config (e.g., /set yolo_mode true)",
    usage="/set <key> <value>",
    category="config",
)
def handle_set_command(command: str) -> bool:
    """Set configuration values."""
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
        emit_warning(
            f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(config_keys)}\n[dim]Note: compaction_strategy can be 'summarization' or 'truncation'[/dim]{session_help}"
        )
        return True
    if key:
        # Check if we're toggling DBOS enablement
        if key == "enable_dbos":
            emit_info(
                "[yellow]⚠️ DBOS configuration changed. Please restart Code Puppy for this change to take effect.[/yellow]"
            )

        set_config_value(key, value)
        emit_success(f'Set {key} = "{value}" in puppy.cfg!')
    else:
        emit_error("You must supply a key.")
    return True


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
                emit_warning(f"Pinned model applied but reload failed: {reload_error}")

        return True

    except Exception as e:
        emit_error(f"Failed to pin model to agent '{agent_name}': {e}")
        return True


@register_command(
    name="diff",
    description="Configure diff highlighting colors (additions, deletions)",
    usage="/diff",
    category="config",
)
def handle_diff_command(command: str) -> bool:
    """Configure diff highlighting colors."""
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
        get_diff_highlight_style,
        set_diff_addition_color,
        set_diff_deletion_color,
        set_diff_highlight_style,
    )
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split()

    if len(tokens) == 1:
        # Show current diff configuration
        add_color = get_diff_addition_color()
        del_color = get_diff_deletion_color()

        emit_info("[bold magenta]🎨 Diff Configuration[/bold magenta]")
        # Show the actual color pairs being used
        from code_puppy.tools.file_modifications import _get_optimal_color_pair

        add_fg, add_bg = _get_optimal_color_pair(add_color, "green")
        del_fg, del_bg = _get_optimal_color_pair(del_color, "orange1")
        current_style = get_diff_highlight_style()
        if current_style == "highlighted":
            emit_info(
                f"[bold]Additions:[/bold]       [{add_fg} on {add_bg}]■■■■■■■■■■[/{add_fg} on {add_bg}] {add_color}"
            )
            emit_info(
                f"[bold]Deletions:[/bold]       [{del_fg} on {del_bg}]■■■■■■■■■■[/{del_fg} on {del_bg}] {del_color}"
            )
        if current_style == "text":
            emit_info(
                f"[bold]Additions:[/bold]       [{add_color}]■■■■■■■■■■[/{add_color}] {add_color}"
            )
            emit_info(
                f"[bold]Deletions:[/bold]       [{del_color}]■■■■■■■■■■[/{del_color}] {del_color}"
            )
        emit_info("\n[yellow]Subcommands:[/yellow]")
        emit_info(
            "  [cyan]/diff style <style>[/cyan]                 Set diff style (text/highlighted)"
        )
        emit_info(
            "  [cyan]/diff additions <color>[/cyan]             Set addition color (shows options if no color)"
        )
        emit_info(
            "  [cyan]/diff deletions <color>[/cyan]             Set deletion color (shows options if no color)"
        )
        emit_info(
            "  [cyan]/diff show[/cyan]                         Show current configuration with example"
        )

        if current_style == "text":
            emit_info("\n[dim]Current mode: Plain text diffs (no highlighting)[/dim]")
        else:
            emit_info(
                "\n[dim]Current mode: Intelligent color pairs for maximum contrast[/dim]"
            )
        return True

    subcmd = tokens[1].lower()

    if subcmd == "style":
        if len(tokens) == 2:
            # Show current style
            current_style = get_diff_highlight_style()
            emit_info("[bold magenta]🎨 Current Diff Style[/bold magenta]")
            emit_info(f"Style: {current_style}")
            emit_info("\n[yellow]Available styles:[/yellow]")
            emit_info(
                "  [cyan]text[/cyan]         - Plain text diffs with no highlighting"
            )
            emit_info(
                "  [cyan]highlighted[/cyan]   - Intelligent color pairs for maximum contrast"
            )
            emit_info("\n[dim]Use '/diff style <style>' to change[/dim]")
            return True
        elif len(tokens) != 3:
            emit_warning("Usage: /diff style <style>")
            emit_info("[dim]Use '/diff style' to see available styles[/dim]")
            return True

        new_style = tokens[2].lower()
        try:
            set_diff_highlight_style(new_style)
            emit_success(f"Diff style set to '{new_style}'")
        except Exception as e:
            emit_error(f"Failed to set diff style: {e}")
        return True

    if subcmd == "additions":
        if len(tokens) == 2:
            # Show available color options
            _show_color_options("additions")
            return True
        elif len(tokens) != 3:
            emit_warning("Usage: /diff additions <color>")
            emit_info("[dim]Use '/diff additions' to see available colors[/dim]")
            return True

        color = tokens[2]
        try:
            set_diff_addition_color(color)
            emit_success(f"Addition color set to '{color}'")
        except Exception as e:
            emit_error(f"Failed to set addition color: {e}")
        return True

    elif subcmd == "deletions":
        if len(tokens) == 2:
            # Show available color options
            _show_color_options("deletions")
            return True
        elif len(tokens) != 3:
            emit_warning("Usage: /diff deletions <color>")
            emit_info("[dim]Use '/diff deletions' to see available colors[/dim]")
            return True

        color = tokens[2]
        try:
            set_diff_deletion_color(color)
            emit_success(f"Deletion color set to '{color}'")
        except Exception as e:
            emit_error(f"Failed to set deletion color: {e}")
        return True

    elif subcmd == "show":
        # Show current configuration with example
        from code_puppy.tools.file_modifications import _colorize_diff

        add_color = get_diff_addition_color()
        del_color = get_diff_deletion_color()

        # Create a simple diff example
        example_diff = """--- a/example.txt
+++ b/example.txt
@@ -1,3 +1,4 @@
 line 1
-old line 2
+new line 2
 line 3
+added line 4"""

        current_style = get_diff_highlight_style()

        emit_info("[bold magenta]🎨 Current Diff Configuration[/bold magenta]")
        emit_info(f"Style: {current_style}")

        if current_style == "highlighted":
            # Show the actual color pairs being used
            from code_puppy.tools.file_modifications import _get_optimal_color_pair

            add_fg, add_bg = _get_optimal_color_pair(add_color, "green")
            del_fg, del_bg = _get_optimal_color_pair(del_color, "orange1")
            emit_info(
                f"Additions: [{add_fg} on {add_bg}]■■■■■■■■■■[/{add_fg} on {add_bg}] {add_color}"
            )
            emit_info(
                f"Deletions: [{del_fg} on {del_bg}]■■■■■■■■■■[/{del_fg} on {del_bg}] {del_color}"
            )
        else:
            emit_info(f"Additions: {add_color} (plain text mode)")
            emit_info(f"Deletions: {del_color} (plain text mode)")
        emit_info(
            "\n[bold cyan]── DIFF EXAMPLE ───────────────────────────────────[/bold cyan]"
        )

        # Show the colored example
        colored_example = _colorize_diff(example_diff)
        emit_info(colored_example, highlight=False)

        emit_info(
            "[bold cyan]───────────────────────────────────────────────[/bold cyan]\n"
        )
        return True

    else:
        emit_warning(f"Unknown diff subcommand: {subcmd}")
        emit_info("Use '/diff' to see available subcommands")
        return True


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _show_color_options(color_type: str):
    # ============================================================================
    # UTILITY FUNCTIONS
    # ============================================================================

    """Show available Rich color options organized by category."""
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
            "[bold white on green]🎨 Recommended Colors for Additions:[/bold white on green]"
        )
        for color, emoji in suggestions:
            emit_info(
                f"  [cyan]{color:<16}[/cyan] [white on {color}]■■■■■■■■■■[/white on {color}] {emoji}"
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
            "[bold white on orange1]🎨 Recommended Colors for Deletions:[/bold white on orange1]"
        )
        for color, emoji in suggestions:
            emit_info(
                f"  [cyan]{color:<16}[/cyan] [white on {color}]■■■■■■■■■■[/white on {color}] {emoji}"
            )

    emit_info("\n[bold]🎨 All Available Rich Colors:[/bold]")
    for category, colors in color_categories.items():
        emit_info(f"\n[cyan]{category}:[/cyan]")
        # Display in columns for better readability
        for i in range(0, len(colors), 4):
            row = colors[i : i + 4]
            row_text = "  ".join([f"[{color}]■[/{color}] {color}" for color, _ in row])
            emit_info(f"  {row_text}")

    emit_info("\n[yellow]Usage:[/yellow] [cyan]/diff {color_type} <color_name>[/cyan]")
    emit_info("[dim]All diffs use white text on your chosen background colors[/dim]")
    emit_info("[dim]You can also use hex colors like #ff0000 or rgb(255,0,0)[/dim]")
