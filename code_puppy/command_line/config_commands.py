"""Command handlers for Code Puppy - CONFIG commands.

This module contains @register_command decorated handlers that are automatically
discovered by the command registry system.
"""

import json
from typing import Optional

from code_puppy.command_line.command_registry import register_command
from code_puppy.command_line.config_apply import apply_setting
from code_puppy.i18n import t


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
        get_resume_message_count,
        get_temperature,
        get_yolo_mode,
    )
    from code_puppy.keymap import (
        get_cancel_agent_display_name,
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
[bold]auto_save_session:[/bold]     {"[green]enabled[/green]" if auto_save else "[yellow]disabled[/yellow]"}
[bold]protected_tokens:[/bold]      [cyan]{protected_tokens:,}[/cyan] recent tokens preserved
[bold]compaction_threshold:[/bold]     [cyan]{compaction_threshold:.1%}[/cyan] context usage triggers compaction
[bold]compaction_strategy:[/bold]   [cyan]{compaction_strategy}[/cyan] (summarization or truncation)
[bold]resume_message_count:[/bold] [cyan]{get_resume_message_count()}[/cyan] messages shown on /resume
[bold]reasoning_effort:[/bold]      [cyan]{get_openai_reasoning_effort()}[/cyan]
[bold]verbosity:[/bold]             [cyan]{get_openai_verbosity()}[/cyan]
[bold]temperature:[/bold]           [cyan]{effective_temperature if effective_temperature is not None else "(model default)"}[/cyan]{" (per-model)" if effective_temperature != global_temperature and effective_temperature is not None else ""}
[bold]cancel_agent_key:[/bold]      [cyan]{get_cancel_agent_display_name()}[/cyan] (options: ctrl+c, ctrl+k, ctrl+q)

"""
    emit_info(Text.from_markup(status_msg))
    return True


@register_command(
    name="set",
    description="Set puppy config (e.g., /set yolo_mode true) or launch interactive menu",
    usage="/set [key [value]]",
    category="config",
)
def handle_set_command(command: str) -> bool:
    """Set configuration values, or launch the interactive picker."""
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    tokens = command.split(None, 2)
    argstr = command[len("/set") :].strip()
    key: Optional[str] = None
    value: Optional[str] = None
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
        # No arguments -- launch the interactive config menu
        _launch_interactive_set_menu()
        return True

    if not key:
        emit_error(t("cfg.set.key_required"))
        return True

    result = apply_setting(key, value or "", reload_agent=True)
    if not result.ok:
        emit_error(result.error or "Failed to apply setting.")
        return True

    from code_puppy.command_line.set_menu_values import is_sensitive_key, mask_value

    display = (
        mask_value(result.value_after or "")
        if is_sensitive_key(key)
        else result.value_after
    )
    if key == "yolo_mode" and (value or "").strip().lower() == "config":
        emit_success(t("cfg.set.yolo_config_unchanged"))
    else:
        emit_success(t("cfg.set.success", key=key, value=display))
    # Restart notices (warning) and the reload-success/failure signal
    # are independent: a restart-required key like ``enable_dbos``
    # should still report whether the live agent reload happened. The
    # original ``/set`` always emitted "Agent reloaded with updated
    # config" alongside the restart notice; preserve that contract.
    if result.warning:
        emit_warning(result.warning)
    if result.reload_error:
        emit_warning(result.reload_error)
    else:
        emit_info(t("cfg.set.agent_reloaded"))
    return True


def _launch_interactive_set_menu() -> None:
    """Run the picker in a worker thread and drain any queued messages.

    The picker owns the terminal while prompt_toolkit is active, so it
    can't safely emit messages itself; instead it returns them in
    ``PickerResult.pending_messages`` and we emit them here on the
    main thread once the picker has fully exited.
    """
    import asyncio
    import concurrent.futures

    from code_puppy.command_line.set_menu import interactive_set_picker
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    _LEVEL_EMITTERS = {
        "info": emit_info,
        "success": emit_success,
        "warning": emit_warning,
        "error": emit_error,
    }

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_set_picker()))
        result = future.result(timeout=300)  # 5 min timeout

    if result is None:
        return
    for level, message in result.pending_messages:
        emitter = _LEVEL_EMITTERS.get(level, emit_info)
        emitter(message)

    # Coalesce all agent reloads into a single one at the end, but only
    # when the user actually changed something. Failures here mirror the
    # behaviour of the per-key path: warn, don't crash.
    if result.changed_settings:
        from code_puppy.agents import get_current_agent

        try:
            get_current_agent().reload_code_generation_agent()
            emit_info(t("cfg.set.agent_reloaded"))
        except Exception as reload_error:
            emit_warning(t("cfg.set.reload_failed", error=reload_error))


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
        emit_warning(t("cfg.pin_model.usage"))

        # Show available models and agents
        available_models = load_model_names()
        json_agents = discover_json_agents()

        # Get built-in agents
        from code_puppy.agents.agent_manager import get_agent_descriptions

        builtin_agents = get_agent_descriptions()

        emit_info(t("cfg.listing.available_models"))
        for model in available_models:
            emit_info(f"  {model}")

        if builtin_agents:
            emit_info("\n" + t("cfg.listing.builtin_agents"))
            for agent_name, description in builtin_agents.items():
                emit_info(f"  {agent_name} - {description}")

        if json_agents:
            emit_info("\n" + t("cfg.listing.json_agents"))
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
        emit_error(t("cfg.model.not_found", model=model_name))
        emit_warning(t("cfg.model.available_list", models=", ".join(available_models)))
        return True

    # Check if this is a JSON agent or a built-in Python agent
    json_agents = discover_json_agents()

    # Get list of available built-in agents
    from code_puppy.agents.agent_manager import get_agent_descriptions

    builtin_agents = get_agent_descriptions()

    is_json_agent = agent_name in json_agents
    is_builtin_agent = agent_name in builtin_agents

    if not is_json_agent and not is_builtin_agent:
        emit_error(t("cfg.agent.not_found", agent=agent_name))

        # Show available agents
        if builtin_agents:
            emit_info("\n" + t("cfg.listing.builtin_agents"))
            for name, desc in builtin_agents.items():
                emit_info(f"  {name} - {desc}")

        if json_agents:
            emit_info("\n" + t("cfg.listing.json_agents"))
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

        emit_success(t("cfg.pin_model.success", model=model_name, agent=agent_name))

        # If this is the current agent, refresh it so the prompt updates immediately
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        if current_agent.name == agent_name:
            try:
                if is_json_agent and hasattr(current_agent, "refresh_config"):
                    current_agent.refresh_config()
                current_agent.reload_code_generation_agent()
                emit_info(t("cfg.pin_model.agent_reloaded", model=model_name))
            except Exception as reload_error:
                emit_warning(t("cfg.pin_model.reload_failed", error=reload_error))

        return True

    except Exception as e:
        emit_error(t("cfg.pin_model.failed", agent=agent_name, error=e))
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
        emit_warning(t("cfg.unpin.usage"))

        # Show available agents
        json_agents = discover_json_agents()

        # Get built-in agents
        from code_puppy.agents.agent_manager import get_agent_descriptions

        builtin_agents = get_agent_descriptions()

        if builtin_agents:
            emit_info("\n" + t("cfg.listing.builtin_agents"))
            for agent_name, description in builtin_agents.items():
                pinned_model = get_agent_pinned_model(agent_name)
                if pinned_model:
                    emit_info(f"  {agent_name} - {description} [→ {pinned_model}]")
                else:
                    emit_info(f"  {agent_name} - {description}")

        if json_agents:
            emit_info("\n" + t("cfg.listing.json_agents"))
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
        emit_error(t("cfg.agent.not_found", agent=agent_name_input))

        # Show available agents
        if builtin_agents:
            emit_info("\n" + t("cfg.listing.builtin_agents"))
            for name, desc in builtin_agents.items():
                emit_info(f"  {name} - {desc}")

        if json_agents:
            emit_info("\n" + t("cfg.listing.json_agents"))
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

        emit_success(t("cfg.unpin.success", agent=agent_name))

        # If this is the current agent, refresh it so the prompt updates immediately
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        if current_agent.name == agent_name:
            try:
                if is_json_agent and hasattr(current_agent, "refresh_config"):
                    current_agent.refresh_config()
                current_agent.reload_code_generation_agent()
                emit_info(t("cfg.unpin.agent_reloaded"))
            except Exception as reload_error:
                emit_warning(t("cfg.unpin.reload_failed", error=reload_error))

        return True

    except Exception as e:
        emit_error(t("cfg.unpin.failed", agent=agent_name, error=e))
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
            emit_error(t("cfg.diff.apply_failed", error=e))
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
            emit_success(t("cfg.colors.saved"))
        except Exception as e:
            emit_error(t("cfg.colors.apply_failed", error=e))
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

    emit_info("\n" + t("cfg.colors.all_available"))
    for category, colors in color_categories.items():
        emit_info(f"\n{category}:")
        # Display in columns for better readability
        for i in range(0, len(colors), 4):
            row = colors[i : i + 4]
            row_text = "  ".join([f"[{color}]■[/{color}] {color}" for color, _ in row])
            emit_info(Text.from_markup(f"  {row_text}"))

    emit_info("\n" + t("cfg.colors.usage"))
    emit_info(t("cfg.colors.white_text_note"))
    emit_info(t("cfg.colors.hex_note"))
