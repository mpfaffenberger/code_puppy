# Import to trigger command registration
import code_puppy.command_line.config_commands  # noqa: F401
import code_puppy.command_line.core_commands  # noqa: F401
import code_puppy.command_line.session_commands  # noqa: F401

# Global flag to track if plugins have been loaded
_PLUGINS_LOADED = False


def get_commands_help():
    """Generate aligned commands help using Rich Text for safe markup.

    Now dynamically generates help from the command registry!
    Only shows two sections: Built-in Commands and Custom Commands.
    """
    from rich.text import Text

    from code_puppy.command_line.command_registry import get_unique_commands

    # Ensure plugins are loaded so custom help can register
    _ensure_plugins_loaded()

    lines: list[Text] = []
    # No global header needed - user already knows they're viewing help

    # Collect all built-in commands (registered + legacy)
    builtin_cmds: list[tuple[str, str]] = []

    # Get registered commands (all categories are built-in)
    registered_commands = get_unique_commands()
    for cmd_info in sorted(registered_commands, key=lambda c: c.name):
        builtin_cmds.append((cmd_info.usage, cmd_info.description))

    # Get custom commands from plugins
    custom_entries: list[tuple[str, str]] = []
    try:
        from code_puppy import callbacks

        custom_help_results = callbacks.on_custom_command_help()
        for res in custom_help_results:
            if not res:
                continue
            # Format 1: Tuple with (command_name, description)
            if isinstance(res, tuple) and len(res) == 2:
                cmd_name = str(res[0])
                custom_entries.append((f"/{cmd_name}", str(res[1])))
            # Format 2: List of tuples or strings
            elif isinstance(res, list):
                # Check if it's a list of tuples (preferred format)
                if res and isinstance(res[0], tuple) and len(res[0]) == 2:
                    for item in res:
                        if isinstance(item, tuple) and len(item) == 2:
                            cmd_name = str(item[0])
                            custom_entries.append((f"/{cmd_name}", str(item[1])))
                # Format 3: List of strings (legacy format)
                # Extract command from first line like "/command_name - Description"
                elif res and isinstance(res[0], str) and res[0].startswith("/"):
                    first_line = res[0]
                    if " - " in first_line:
                        parts = first_line.split(" - ", 1)
                        cmd_name = parts[0].lstrip("/").strip()
                        description = parts[1].strip()
                        custom_entries.append((f"/{cmd_name}", description))
    except Exception:
        pass

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
# All built-in command handlers have been split into category-specific files.
# These imports trigger their registration via @register_command decorators.

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

# ============================================================================
# MAIN COMMAND DISPATCHER
# ============================================================================

# _show_color_options has been moved to builtin_commands.py


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
    # This section is kept as a fallback mechanism for commands added in other
    # branches that haven't been migrated to the registry system yet.
    #
    # All current commands are registered above using @register_command, so
    # they won't fall through to this section.
    #
    # If you're rebasing and your branch adds a new command using the old
    # if/elif style, it will still work! Just add your if block below.
    #
    # EXAMPLE: How to add a legacy command:
    #
    #   if command.startswith("/mycommand"):
    #       from code_puppy.messaging import emit_info
    #       emit_info("My command executed!")
    #       return True
    #
    # NOTE: For new commands, please use @register_command instead (see above).
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
            from code_puppy import callbacks

            # Import the special result class for markdown commands
            try:
                from code_puppy.plugins.customizable_commands.register_callbacks import (
                    MarkdownCommandResult,
                )
            except ImportError:
                MarkdownCommandResult = None

            results = callbacks.on_custom_command(command=command, name=name)
            # Iterate through callback results; treat str as handled (no model run)
            for res in results:
                if res is True:
                    return True
                if MarkdownCommandResult and isinstance(res, MarkdownCommandResult):
                    # Special case: markdown command that should be processed as input
                    # Replace the command with the markdown content and let it be processed
                    # This is handled by the caller, so return the content as string
                    return res.content
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
