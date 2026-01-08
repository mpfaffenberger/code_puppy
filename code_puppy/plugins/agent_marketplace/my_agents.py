"""Handler for the /my-agents command.

Provides functionality to list and manage your published agents.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from code_puppy.messaging import emit_error

from . import api_client

console = Console()


def _format_number(num: int) -> str:
    """Format a number with comma separators.

    Args:
        num: The number to format.

    Returns:
        Formatted string with commas.
    """
    return f"{num:,}"


def _format_rating(rating: Optional[float]) -> str:
    """Format a rating value.

    Args:
        rating: The rating value (0-5).

    Returns:
        Formatted rating string.
    """
    if rating is None or rating == 0:
        return "--"
    return f"{rating:.1f}"


def _format_relative_time(iso_date: str) -> str:
    """Format an ISO date string as a relative time.

    Args:
        iso_date: ISO format date string.

    Returns:
        Human-readable relative time string.
    """
    try:
        # Parse the date - handle both with and without timezone
        if iso_date.endswith("Z"):
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        elif "+" in iso_date or iso_date.count("-") > 2:
            dt = datetime.fromisoformat(iso_date)
        else:
            dt = datetime.fromisoformat(iso_date).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 7:
            return f"{days}d ago"
        weeks = days // 7
        if weeks < 4:
            return f"{weeks}w ago"
        months = days // 30
        return f"{months}mo ago"
    except (ValueError, TypeError):
        return iso_date[:10] if len(iso_date) >= 10 else iso_date


def _display_agents(agents: list[dict]) -> None:
    """Display user's agents in a Rich table.

    Args:
        agents: List of agent dictionaries from the API.
    """
    if not agents:
        # Empty state
        empty_text = """
[yellow]You haven't published any agents yet.[/yellow]

Use [cyan]/upload-agent[/cyan] to get started!

[dim]Your agents will appear here after publishing.[/dim]
        """
        console.print(
            Panel(
                empty_text.strip(),
                title="\U0001f4cb My Agents",
                border_style="yellow",
            )
        )
        return

    # Header
    console.print(
        f"\n[cyan]\U0001f4cb[/cyan] Your Published Agents ([bold]{len(agents)}[/bold] total)\n"
    )

    # Create the results table
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        row_styles=["", "dim"],
    )

    table.add_column("Name", style="green", min_width=15, max_width=20)
    table.add_column("Status", min_width=10)
    table.add_column("Version", justify="center", min_width=8)
    table.add_column("\u2b07 DLs", justify="right", min_width=8)
    table.add_column("\u2b50 Rating", justify="right", min_width=8)
    table.add_column("Updated", min_width=10)

    for agent in agents:
        # Determine status display
        is_public = agent.get("is_public", False)
        status = "\U0001f30d Public" if is_public else "\U0001f512 Private"
        status_style = "green" if is_public else "dim"

        # Format version
        version = f"v{agent.get('version', 1)}"

        # Add the row
        table.add_row(
            agent.get("name", "Unknown"),
            f"[{status_style}]{status}[/{status_style}]",
            version,
            _format_number(agent.get("download_count", 0)),
            _format_rating(agent.get("average_rating")),
            _format_relative_time(agent.get("updated_at", "")),
        )

    console.print(table)

    # Summary stats
    total_downloads = sum(a.get("download_count", 0) for a in agents)
    public_count = sum(1 for a in agents if a.get("is_public", False))
    console.print(
        f"\n[dim]{public_count} public \u2022 {total_downloads:,} total downloads[/dim]"
    )

    # Help footer
    console.print(
        "\n[dim]Tip:[/dim] Use [cyan]/upload-agent[/cyan] to publish a new agent "
        "or update an existing one."
    )


async def _get_my_agents_async() -> list[dict]:
    """Perform the async fetch operation.

    Returns:
        List of user's published agents.
    """
    return await api_client.get_my_agents()


def handle_my_agents(command: str) -> bool:
    """Handle the my-agents command.

    Args:
        command: The full command string including any arguments.

    Returns:
        bool: True to indicate the command was handled.
    """
    console.print("[cyan]\U0001f436[/cyan] Fetching your agents...")

    try:
        # Run the async fetch
        from code_puppy.plugins.agent_marketplace.api_client import run_async
        agents = run_async(_get_my_agents_async())
        _display_agents(agents)

    except Exception as e:
        error_msg = str(e)

        # Handle common errors with friendly messages
        if (
            "401" in error_msg
            or "403" in error_msg
            or "unauthorized" in error_msg.lower()
        ):
            emit_error("Authentication required. Please log in first.")
            console.print(
                "\n[dim]Run[/dim] [cyan]/login[/cyan] [dim]to authenticate.[/dim]"
            )
        elif "404" in error_msg:
            emit_error("My agents endpoint not available.")
        else:
            emit_error(f"Failed to fetch agents: {e}")
            console.print(
                "\n[dim]Check your network connection or try again later.[/dim]"
            )

    return True
