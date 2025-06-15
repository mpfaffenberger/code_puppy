import os

from rich.console import Console

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.config import get_config_keys
from code_puppy.command_line.utils import make_directory_table

META_COMMANDS_HELP = """
[bold magenta]Meta Commands Help[/bold magenta]
~help, ~h             Show this help message
~cd <dir>             Change directory or show directories
~codemap <dir>        Show code structure for <dir>
~m <model>            Set active model
~motd                 Show the latest message of the day (MOTD)
~show                 Show puppy config key-values
~set                  Set puppy config key-values
~<unknown>            Show unknown meta command warning
"""


from code_puppy.command_line.motd import print_motd

def handle_meta_command(command: str, console: Console) -> bool:
    """
    Handle meta/config commands prefixed with '~'.
    Returns True if the command was handled (even if just an error/help), False if not.
    """
    command = command.strip()

    if command.strip().startswith("~motd"):
        print_motd(console, force=True)
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
            console.print(f"[red]Error generating code map:[/red] {e}")
        return True

    if command.startswith("~cd"):
        tokens = command.split()
        if len(tokens) == 1:
            try:
                table = make_directory_table()
                console.print(table)
            except Exception as e:
                console.print(f"[red]Error listing directory:[/red] {e}")
            return True
        elif len(tokens) == 2:
            dirname = tokens[1]
            target = os.path.expanduser(dirname)
            if not os.path.isabs(target):
                target = os.path.join(os.getcwd(), target)
            if os.path.isdir(target):
                os.chdir(target)
                console.print(
                    f"[bold green]Changed directory to:[/bold green] [cyan]{target}[/cyan]"
                )
            else:
                console.print(f"[red]Not a directory:[/red] [bold]{dirname}[/bold]")
            return True

    if command.strip().startswith("~show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import get_owner_name, get_puppy_name, get_yolo_mode, get_message_history_limit
        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        msg_limit = get_message_history_limit()
        console.print(f'''[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]     [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]     [cyan]{owner_name}[/cyan]
[bold]model:[/bold]          [green]{model}[/green]
[bold]YOLO_MODE:[/bold]      {'[red]ON[/red]' if yolo_mode else '[yellow]off[/yellow]'}
[bold]message_history_limit:[/bold]   Keeping last [cyan]{msg_limit}[/cyan] messages in context
''')
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
            console.print(
                f"[yellow]Usage:[/yellow] ~set KEY=VALUE or ~set KEY VALUE\nConfig keys: {', '.join(get_config_keys())}"
            )
            return True
        if key:
            set_config_value(key, value)
            console.print(
                f'[green]🌶 Set[/green] [cyan]{key}[/cyan] = "{value}" in puppy.cfg!'
            )
        else:
            console.print("[red]You must supply a key.[/red]")
        return True

    if command.startswith("~m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.command_line.model_picker_completion import get_active_model
            from code_puppy.agent import get_code_generation_agent

            model = get_active_model()
            # Make sure this is called for the test
            get_code_generation_agent(force_reload=True)
            console.print(
                f"[bold green]Active model set and loaded:[/bold green] [cyan]{model}[/cyan]"
            )
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        console.print("[yellow]Usage:[/yellow] ~m <model-name>")
        console.print(f"[yellow]Available models:[/yellow] {', '.join(model_names)}")
        return True
    if command in ("~help", "~h"):
        console.print(META_COMMANDS_HELP)
        return True
    if command.startswith("~"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            console.print(
                f"[yellow]Unknown meta command:[/yellow] {command}\n[dim]Type ~help for options.[/dim]"
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            console.print(
                f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
            )
        return True
    return False
