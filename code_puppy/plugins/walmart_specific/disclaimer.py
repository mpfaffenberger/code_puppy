from rich.console import Console


def display_disclaimer():
    """Display a disclaimer message about data sensitivity and usage guidelines."""
    from code_puppy.messaging import emit_system_message

    message = "\n[bold yellow]DISCLAIMER : Be a responsible Puppy Owner[/bold yellow]"
    emit_system_message(message)

    message = "[yellow]Prompt responsibly: Only use internal data available to all HO associates. No permission based data should be included in prompts.[/yellow]"
    emit_system_message(message)

    message = (
        "[yellow]All information entered will be monitored in accordance with "
        "applicable Walmart policies and used for enhancement of this tool and "
        "AI adoption at Walmart. Refer to "
        "[link=https://one.walmart.com/content/uswire/en_us/work1/policies/"
        "people-policies/company-issued-equipment-useage.html]usage[/link] "
        "for best practices on secure usage.[/yellow]\n"
    )
    emit_system_message(message)


def print_textual_installation_help(direct_console: Console):
    """Print helpful instructions for installing the textual CLI."""

    direct_console.print("[bold red]Error:[/bold red] 'textual' command not found.")
    direct_console.print(
        "\n[bold yellow]The textual CLI is required to run code-puppy in web mode.[/bold yellow]"
    )
    direct_console.print("\n[bold blue]Installation:[/bold blue]")
    direct_console.print("[green]pip install textual-dev[/green]")
    direct_console.print("\n[dim]After installation, you can run:[/dim]")
    direct_console.print("[green]code-puppy --web[/green]")
    direct_console.print(
        "\n[dim]For more info, visit: https://textual.textualize.io/[/dim]"
    )
