import os

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import get_config_keys
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

META_COMMANDS_HELP = """
[bold magenta]Meta Commands Help[/bold magenta]
~help, ~h             Show this help message
~cd <dir>             Change directory or show directories
~codemap <dir>        Show code structure for <dir>
~m <model>            Set active model
~motd                 Show the latest message of the day (MOTD)
~show                 Show puppy config key-values
~set                  Set puppy config key-values
~tools                Show available tools and capabilities
~<unknown>            Show unknown meta command warning
"""


def handle_meta_command(command: str) -> bool:
    """
    Handle meta/config commands prefixed with '~'.

    Args:
        command: The command string to handle

    Returns:
        True if the command was handled, False if not
    """
    command = command.strip()

    if command.strip().startswith("~motd"):
        print_motd(force=True)
        return True

    # ~codemap (code structure visualization)
    if command.startswith("~codemap"):
        from code_puppy.tools.ts_code_map import make_code_map

        tokens = command.split()
        if len(tokens) > 1:
            target_dir = os.path.expanduser(tokens[1])
        else:
            target_dir = os.getcwd()
        try:
            make_code_map(target_dir, ignore_tests=True)
        except Exception as e:
            emit_error(f"Error generating code map: {e}")
        return True

    if command.startswith("~cd"):
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

    if command.strip().startswith("~show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_message_history_limit,
            get_owner_name,
            get_puppy_name,
            get_yolo_mode,
        )

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        msg_limit = get_message_history_limit()
        status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]     [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]     [cyan]{owner_name}[/cyan]
[bold]model:[/bold]          [green]{model}[/green]
[bold]YOLO_MODE:[/bold]      {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]message_history_limit:[/bold]   Keeping last [cyan]{msg_limit}[/cyan] messages in context
"""
        emit_info(status_msg)
        return True

    if command.startswith("~set"):
        # Syntax: ~set KEY=VALUE or ~set KEY VALUE
        from code_puppy.config import set_config_value

        tokens = command.split(None, 2)
        argstr = command[len("~set") :].strip()
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
            emit_warning(
                f"Usage: ~set KEY=VALUE or ~set KEY VALUE\nConfig keys: {', '.join(get_config_keys())}"
            )
            return True
        if key:
            set_config_value(key, value)
            emit_success(f'🌶 Set {key} = "{value}" in puppy.cfg!')
        else:
            emit_error("You must supply a key.")
        return True

    if command.startswith("~tools"):
        # Display the TOOLS.md file content with markdown formatting
        try:
            from pathlib import Path

            from rich.markdown import Markdown

            # Get the path to TOOLS.md relative to this file
            current_dir = Path(__file__).parent.parent
            tools_md_path = current_dir / "tools" / "TOOLS.md"

            if tools_md_path.exists():
                with open(tools_md_path, "r", encoding="utf-8") as f:
                    tools_content = f.read()
                # Use Rich Markdown for proper formatting
                markdown_content = Markdown(tools_content)
                emit_info(markdown_content)
            else:
                emit_error(f"TOOLS.md not found at: {tools_md_path}")
        except Exception as e:
            emit_error(f"Error reading TOOLS.md: {e}")
        return True

    if command.startswith("~m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.agent import get_code_generation_agent
            from code_puppy.command_line.model_picker_completion import get_active_model

            model = get_active_model()
            # Make sure this is called for the test
            get_code_generation_agent(force_reload=True)
            emit_success(f"Active model set and loaded: {model}")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        emit_warning("Usage: ~m <model-name>")
        emit_warning(f"Available models: {', '.join(model_names)}")
        return True
    if command in ("~help", "~h"):
        emit_info(META_COMMANDS_HELP)
        return True
    if command.startswith("~"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            emit_warning(
                f"Unknown meta command: {command}\n[dim]Type ~help for options.[/dim]"
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
