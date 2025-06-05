from code_puppy.command_line.model_picker_completion import update_model_in_input, load_model_names, get_active_model
from rich.console import Console
import os
from code_puppy.command_line.utils import make_directory_table

def handle_meta_command(command: str, console: Console) -> bool:
    # ~codemap (code structure visualization)
    if command.startswith("~codemap"):
        from code_puppy.tools.code_map import make_code_map
        tokens = command.split()
        if len(tokens) > 1:
            target_dir = os.path.expanduser(tokens[1])
        else:
            target_dir = os.getcwd()
        try:
            tree = make_code_map(target_dir, show_doc=True)
            console.print(tree)
        except Exception as e:
            console.print(f'[red]Error generating code map:[/red] {e}')
        return True
    """
    Handle meta/config commands prefixed with '~'.
    Returns True if the command was handled (even if just an error/help), False if not.
    """
    command = command.strip()
    if command.startswith("~cd"):
        tokens = command.split()
        if len(tokens) == 1:
            try:
                table = make_directory_table()
                console.print(table)
            except Exception as e:
                console.print(f'[red]Error listing directory:[/red] {e}')
            return True
        elif len(tokens) == 2:
            dirname = tokens[1]
            target = os.path.expanduser(dirname)
            if not os.path.isabs(target):
                target = os.path.join(os.getcwd(), target)
            if os.path.isdir(target):
                os.chdir(target)
                console.print(f'[bold green]Changed directory to:[/bold green] [cyan]{target}[/cyan]')
            else:
                console.print(f'[red]Not a directory:[/red] [bold]{dirname}[/bold]')
            return True

    if command.startswith("~m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.agent import get_code_generation_agent
            model = get_active_model()
            get_code_generation_agent(force_reload=True)
            console.print(f"[bold green]Active model set and loaded:[/bold green] [cyan]{model}[/cyan]")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        console.print(f"[yellow]Available models:[/yellow] {', '.join(model_names)}")
        console.print(f"[yellow]Usage:[/yellow] ~m <model_name>")
        return True
    if command in ("~help", "~h"):
        console.print("[bold magenta]Meta commands available:[/bold magenta]\n  ~m <model>: Pick a model from your list!\n  ~cd [dir]: Change directories\n  ~codemap [dir]: Visualize project code structure\n  ~help: Show this help\n  (More soon. Woof!)")
        return True
    if command.startswith("~"):
        name = command[1:].split()[0] if len(command)>1 else ""
        if name:
            console.print(f"[yellow]Unknown meta command:[/yellow] {command}\n[dim]Type ~help for options.[/dim]")
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model
            current_model = get_active_model()
            console.print(f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]")
        return True
    return False
