from typing import Optional

from rich.console import Console


def display_disclaimer():
    """Display a disclaimer message about data sensitivity and usage guidelines."""
    from code_puppy.messaging import emit_system_message

    message = "\n[bold yellow]DISCLAIMER: Be a responsible Puppy Owner[/bold yellow]"
    emit_system_message(message)

    message = (
        "[yellow]All information entered will be monitored in accordance with "
        "applicable Walmart policies and used for enhancement of this tool and "
        "AI adoption at Walmart. Refer to the following policies for best practices on secure usage:[/yellow]\n"
        "[yellow]• Global Associate Technology Management and Usage Policy: "
        "https://one.walmart.com/content/uswire/en_us/work1/policies/non-people-policies/tdc/policies/tdc-01.html[/yellow]\n"
        "[yellow]• US Associate Device Usage Policy: "
        "https://one.walmart.com/content/uswire/en_us/work1/policies/people-policies/us-associate-device-usage-policy0.html[/yellow]"
    )
    emit_system_message(message)

    message = (
        "\n[bold yellow]Your Responsibility:[/bold yellow]\n"
        "[yellow]Tools, scripts, and applications you create with Code-Puppy are your responsibility "
        "to secure and ensure compliance with Walmart policies. If your work will be used beyond your computer "
        "(for example, deployed into production cloud resources), it must have its own approved "
        "Solution Security Plan (SSP).[/yellow]"
    )
    emit_system_message(message)

    message = (
        "\n[bold red]⚠️  CRITICAL - Data Restrictions:[/bold red]\n"
        "[red]NEVER put HIPAA or PCI data into Code-Puppy prompts or files.[/red]\n"
    )
    emit_system_message(message)


def get_disclaimer_help() -> list:
    """Return help information for the disclaimer command."""
    return [
        ("disclaimer", "Display Walmart data usage disclaimer and policy information")
    ]


def handle_disclaimer_command(command: str, name: str) -> Optional[bool]:
    """Handle the /disclaimer command.

    Args:
        command: The full command string entered by the user
        name: The command name (without slash)

    Returns:
        bool: True if handled, None if not this command
    """
    if name != "disclaimer":
        return None

    display_disclaimer()
    return True


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
