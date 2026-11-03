# Import to trigger command registration
import code_puppy.command_line.config_commands  # noqa: F401
import code_puppy.command_line.core_commands  # noqa: F401
import code_puppy.command_line.session_commands  # noqa: F401
import code_puppy.command_line.uc_menu  # noqa: F401

# Global flag to track if plugins have been loaded
_PLUGINS_LOADED = False


def get_commands_help():
    """Generate aligned commands help using Rich Text for safe markup.

    Now dynamically generates help from the command registry!
    Only shows two sections: Built-in Commands and Custom Commands.
    """
    from rich.text import Text

    from code_puppy.command_line.command_catalog import (
        list_plugin_commands,
        list_registry_commands,
    )

    # Ensure plugins are loaded so custom help can register
    _ensure_plugins_loaded()

    lines: list[Text] = []
    # No global header needed - user already knows they're viewing help

    # Built-in commands (registered + legacy) and plugin-advertised commands
    builtin_cmds = [(e.usage, e.description) for e in list_registry_commands()]
    custom_entries = [(e.usage, e.description) for e in list_plugin_commands()]

    # Calculate global column width (longest command across ALL sections + padding)
    all_commands = builtin_cmds + custom_entries
    if all_commands:
        max_cmd_width = max(len(cmd) for cmd, _ in all_commands)
        column_width = max_cmd_width + 4  # Add 4 spaces padding
    else:
        column_width = 30

    # Maximum description width before truncation (to prevent line wrapping)
    max_desc_width = 80

    def truncate_desc(desc: str, max_width: int) -> str:
        """Truncate description if too long, add ellipsis."""
        if len(desc) <= max_width:
            return desc
        return desc[: max_width - 3] + "..."

    # Display Built-in Commands section (starts immediately, no blank line)
    lines.append(Text("Built-in Commands", style="bold magenta"))
    for cmd, desc in sorted(builtin_cmds, key=lambda x: x[0]):
        truncated_desc = truncate_desc(desc, max_desc_width)
        left = Text(cmd.ljust(column_width), style="cyan")
        right = Text(truncated_desc)
        line = Text()
        line.append_text(left)
        line.append_text(right)
        lines.append(line)

    # Display Custom Commands section (if any)
    if custom_entries:
        lines.append(Text(""))
        lines.append(Text("Custom Commands", style="bold magenta"))
        for cmd, desc in sorted(custom_entries, key=lambda x: x[0]):
            truncated_desc = truncate_desc(desc, max_desc_width)
            left = Text(cmd.ljust(column_width), style="cyan")
            right = Text(truncated_desc)
            line = Text()
            line.append_text(left)
            line.append_text(right)
            lines.append(line)

    # Display Shell Pass-through section
    lines.append(Text(""))
    lines.append(Text("Shell Pass-through", style="bold magenta"))
    shell_left = Text("!<command>".ljust(column_width), style="cyan")
    shell_right = Text("Run a shell command directly (e.g., !git status)")
    shell_line = Text()
    shell_line.append_text(shell_left)
    shell_line.append_text(shell_right)
    lines.append(shell_line)

    final_text = Text()
    for i, line in enumerate(lines):
        if i > 0:
            final_text.append("\n")
        final_text.append_text(line)

    # Add trailing newline for spacing before next prompt
    final_text.append("\n")

    return final_text


# ============================================================================
# IMPORT BUILT-IN COMMAND HANDLERS
# ============================================================================
# Each category's handlers register themselves via @register_command on import.

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


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


# All command handlers moved to builtin_commands.py
# The import above triggers their registration


def _dispatch_custom_command(command: str, name: str):
    """Dispatch through the plugin callback boundary.

    Returns ``(handled, result)`` so namespaced commands can be distinguished
    from file paths without knowing which plugin provides them.
    """
    from code_puppy import callbacks
    from code_puppy.messaging import emit_info

    for result in callbacks.on_custom_command(command=command, name=name):
        if result is True:
            return True, True
        if isinstance(result, callbacks.CustomCommandResult):
            return True, result.content
        if isinstance(result, str):
            emit_info(result)
            return True, True
    return False, None


# ============================================================================
# MAIN COMMAND DISPATCHER
# ============================================================================

# The /colors and /diff TUIs were removed: theming owns those settings now.


def handle_command(command: str):
    """
    Handle commands prefixed with '/'.

    Args:
        command: The command string to handle

    Returns:
        True if the command was handled, False if not, or a string to be processed as user input
    """
    from rich.text import Text

    from code_puppy.command_line.command_registry import get_command
    from code_puppy.messaging import emit_info, emit_warning

    _ensure_plugins_loaded()

    command = command.strip()

    # Commands have a single slash, file paths multiple. EXCEPTION: namespaced
    # custom commands (/flux/status) — only bail to normal input if the token
    # isn't a known custom command.
    if command.startswith("/"):
        first_token = command.split()[0] if command.split() else command
        slash_count = first_token.count("/")
        if slash_count > 1:
            name = first_token.lstrip("/")
            try:
                handled, result = _dispatch_custom_command(command, name)
            except Exception as e:
                emit_warning(f"Custom command hook error: {e}")
                handled, result = False, None
            if handled:
                return result
            # This looks like a file path, not a command - let it be processed as normal input
            return False

    # Check if this is a registered command
    if command.startswith("/"):
        # Extract command name (first word after /)
        cmd_name = command[1:].split()[0] if len(command) > 1 else ""

        # Try to find in registry
        cmd_info = get_command(cmd_name)
        if cmd_info:
            # Execute the registered handler
            return cmd_info.handler(command)

    # ========================================================================
    # LEGACY COMMAND FALLBACK
    # ========================================================================
    # Kept for commands added in other branches not yet migrated to the
    # registry (current commands all use @register_command). Old-style
    # if/elif still works after a rebase — add your block below.
    #
    # EXAMPLE:
    #
    #   if command.startswith("/mycommand"):
    #       from code_puppy.messaging import emit_info
    #       emit_info("My command executed!")
    #       return True
    #
    # NOTE: use @register_command for new commands.
    # ========================================================================

    # Legacy commands from other branches/rebases go here:
    # (All current commands are in the registry above)

    # Example placeholder (remove this and add your command if needed):
    # if command.startswith("/my_new_command"):
    #     from code_puppy.messaging import emit_info
    #     emit_info("Command executed!")
    #     return True

    # End of legacy fallback section
    # ========================================================================

    # All legacy command implementations have been moved to @register_command handlers above.
    # If you're adding a new command via rebase, add your if block here.

    # Try plugin-provided custom commands before unknown warning
    if command.startswith("/"):
        # Extract command name without leading slash and arguments intact
        name = command[1:].split()[0] if len(command) > 1 else ""
        try:
            handled, result = _dispatch_custom_command(command, name)
            if handled:
                return result
        except Exception as e:
            # Log via emit_error but do not block default handling
            emit_warning(f"Custom command hook error: {e}")

        if name:
            emit_warning(
                Text.from_markup(
                    f"Unknown command: {command}\n[dim]Type /help for options.[/dim]"
                )
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            emit_info(
                Text.from_markup(
                    f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
                )
            )
        return True

    return False
