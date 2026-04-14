"""Delete agent command for the Agent Marketplace.

Provides the /delete-agent command to remove your agents from the marketplace.
"""

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from code_puppy.messaging import emit_error, emit_info

from . import api_client

console = Console()


# ============================================================================
# Async Operations
# ============================================================================


async def _delete_agent_async(name: str) -> dict:
    """Perform the async delete operation.

    Args:
        name: The agent name to delete.

    Returns:
        Response dict from API.
    """
    return await api_client.delete_agent(name)


# ============================================================================
# Command Parsing
# ============================================================================


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for delete-agent command."""
    parser = argparse.ArgumentParser(
        prog="/delete-agent",
        description="Delete your agent from the marketplace",
        add_help=False,
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Name of the agent to delete",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="Show this help message",
    )
    return parser


def _show_help() -> None:
    """Display help information for the delete-agent command."""
    help_text = """
[bold cyan]Usage:[/bold cyan]
  /delete-agent <name> [options]

[bold cyan]Arguments:[/bold cyan]
  name          Name of your agent to delete from the marketplace

[bold cyan]Options:[/bold cyan]
  -f, --force   Skip confirmation prompt
  -h, --help    Show this help message

[bold cyan]Examples:[/bold cyan]
  /delete-agent my-agent
  /delete-agent my-agent --force

[bold cyan]Notes:[/bold cyan]
  • You can only delete agents you own
  • Requires authentication (/marketplace_auth)
  • This is a soft delete - agent is marked as inactive
    """
    console.print(Panel(help_text.strip(), title="🗑️ Delete Agent", border_style="cyan"))


# ============================================================================
# Main Command Handler
# ============================================================================


def handle_delete_agent(command: str) -> bool:
    """Handle the /delete-agent command.

    Args:
        command: Full command string including /delete-agent.

    Returns:
        True to indicate the command was handled.
    """
    # Parse command
    parts = command.split()[1:]  # Remove "/delete-agent"
    parser = _create_parser()

    try:
        args = parser.parse_args(parts)
    except SystemExit:
        _show_help()
        return True

    # Handle help
    if args.help or not args.name:
        _show_help()
        return True

    agent_name = args.name

    # Confirm deletion unless --force
    if not args.force:
        console.print(
            f"\n[yellow]⚠️  You are about to delete '{agent_name}' from the marketplace.[/yellow]"
        )
        console.print(
            "[dim]This will remove it from search results and prevent downloads.[/dim]\n"
        )

        if not Confirm.ask(
            f"Are you sure you want to delete [bold]{agent_name}[/bold]?", default=False
        ):
            emit_info("Delete cancelled.")
            return True

    console.print(f'\n[cyan]🐶[/cyan] Deleting agent "{agent_name}"...')

    try:
        from code_puppy.plugins.agent_marketplace.api_client import run_async

        response = run_async(_delete_agent_async(agent_name))

        # Check for success
        if not response.get("success"):
            error_msg = response.get("error", "Delete failed")
            raise Exception(error_msg)

        # Success!
        response.get("data", {})
        message = response.get("message", f"Agent '{agent_name}' deleted successfully!")

        console.print(
            Panel(
                f"[green]✓[/green] {message}",
                title="🗑️ Agent Deleted",
                border_style="green",
            )
        )

    except Exception as e:
        error_msg = str(e)

        # Handle common errors with friendly messages
        if "404" in error_msg or "not found" in error_msg.lower():
            emit_error(f'Agent "{agent_name}" not found in the marketplace.')
        elif "401" in error_msg or "auth" in error_msg.lower():
            emit_error("Authentication required. Run /marketplace_auth first.")
        elif (
            "403" in error_msg
            or "permission" in error_msg.lower()
            or "own" in error_msg.lower()
        ):
            emit_error(f"You don't have permission to delete '{agent_name}'.")
            console.print("[dim]You can only delete agents you own.[/dim]")
        else:
            emit_error(f"Delete failed: {e}")

        console.print("\n[dim]Use /my-agents to see agents you can delete.[/dim]")

    return True
