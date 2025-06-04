from code_puppy.command_line.model_picker_completion import update_model_in_input, load_model_names, get_active_model
from rich.console import Console

def handle_meta_command(command: str, console: Console) -> bool:
    """
    Handle meta/config commands prefixed with '~'.
    Returns True if the command was handled (even if just an error/help), False if not.
    """
    command = command.strip()
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
        console.print("[bold magenta]Meta commands available:[/bold magenta]\n  ~m <model>: Pick a model from your list!\n  ~help: Show this help\n  (More soon. Woof!)")
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
