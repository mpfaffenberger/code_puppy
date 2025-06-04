from code_puppy.command_line.model_picker_completion import update_model_in_input, load_model_names, get_active_model
from rich.console import Console
import os
from rich.table import Table

def handle_meta_command(command: str, console: Console) -> bool:
    """
    Handle meta/config commands prefixed with '~'.
    Returns True if the command was handled (even if just an error/help), False if not.
    """
    command = command.strip()
    if command.startswith("~ls"):
        tokens = command.split()
        if len(tokens) == 1:
            entries = []
            try:
                entries = [e for e in os.listdir(os.getcwd())]
            except Exception as e:
                console.print(f'[red]Error listing directory:[/red] {e}')
                return True
            dirs = [e for e in entries if os.path.isdir(e)]
            files = [e for e in entries if not os.path.isdir(e)]
            table = Table(title=f"📁 [bold blue]Current directory:[/bold blue] [cyan]{os.getcwd()}[/cyan]")
            table.add_column('Type', style='dim', width=8)
            table.add_column('Name', style='bold')
            for d in sorted(dirs):
                table.add_row('[green]dir[/green]', f'[cyan]{d}[/cyan]')
            for f in sorted(files):
                table.add_row('[yellow]file[/yellow]', f'{f}')
            console.print(table)
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
            model = get_active_model()
            console.print(f"[bold green]Active model set to:[/bold green] [cyan]{model}[/cyan]")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        console.print(f"[yellow]Available models:[/yellow] {', '.join(model_names)}")
        console.print(f"[yellow]Usage:[/yellow] ~m <model_name>")
        return True
    if command in ("~help", "~h"):
        console.print("[bold magenta]Meta commands available:[/bold magenta]\n  ~m <model>: Pick a model from your list!\n  ~ls [dir]: List/change directories\n  ~help: Show this help\n  (More soon. Woof!)")
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
