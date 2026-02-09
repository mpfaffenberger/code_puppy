"""Handler for the /search-agents command.

Provides searching functionality for the Agent Marketplace with Rich table output.
Supports filtering by category, tag, and sorting by downloads/rating/recent.
"""

import argparse
import shlex
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from code_puppy.messaging import emit_error, emit_info

from . import api_client
from .api_client import get_marketplace_token_status

console = Console()

# Store the last search results for use by download command
_last_search_results: list[dict] = []


def get_last_search_results() -> list[dict]:
    """Get the results from the most recent search.

    Returns:
        List of agent summaries from the last search.
    """
    return _last_search_results


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for search-agents command.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="/search-agents",
        description="Search for agents in the marketplace",
        add_help=False,
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Search query terms",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        help="Filter by category (e.g., data, devops, frontend)",
    )
    parser.add_argument(
        "--tag",
        "-t",
        type=str,
        help="Filter by tag",
    )
    parser.add_argument(
        "--sort",
        "-s",
        type=str,
        choices=["downloads", "rating", "recent"],
        default="downloads",
        help="Sort results by: downloads, rating, or recent",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)",
    )
    parser.add_argument(
        "--help",
        "-h",
        action="store_true",
        help="Show this help message",
    )
    return parser


def _parse_args(command: str) -> argparse.Namespace:
    """Parse the search-agents command arguments.

    Args:
        command: The full command string.

    Returns:
        Parsed arguments namespace.
    """
    parser = _create_parser()

    # Remove the command name prefix and parse remaining args
    parts = command.strip().split(None, 1)
    args_str = parts[1] if len(parts) > 1 else ""

    try:
        # Use shlex to handle quoted strings properly
        tokens = shlex.split(args_str)
        return parser.parse_args(tokens)
    except (ValueError, SystemExit):
        # Return empty/default args on parse error
        return parser.parse_args([])


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
        return "N/A"
    return f"{rating:.1f}"


def _format_access(access_type: Optional[str]) -> str:
    """Format the access type with emoji.

    Args:
        access_type: Access type string (e.g., 'public', 'ad_group', 'private').

    Returns:
        Formatted access string with emoji.
    """
    if access_type is None:
        access_type = "public"

    access_type = access_type.lower()

    if access_type in ("public", "open"):
        return "🌍 Public"
    elif access_type in ("ad_group", "ad-group", "adgroup", "group"):
        return "🔒 AD Grp"
    elif access_type in ("private", "restricted"):
        return "🔐 Private"
    else:
        return f"❓ {access_type.title()}"


def _truncate(text: str, max_length: int = 40) -> str:
    """Truncate text to a maximum length.

    Args:
        text: The text to truncate.
        max_length: Maximum character count.

    Returns:
        Truncated text with ellipsis if needed.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _build_results_table(results: list[dict]) -> Table:
    """Build a Rich table from search results.

    Args:
        results: List of agent dictionaries from the API.

    Returns:
        Configured Rich Table with results.
    """
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        row_styles=["", "dim"],
    )

    # Column definitions matching the spec
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Name", style="green", min_width=15, max_width=20)
    table.add_column("Description", min_width=20, max_width=27)
    table.add_column("Access", min_width=9, max_width=10)
    table.add_column("⬇ DLs", justify="right", min_width=7)
    table.add_column("⭐ Rating", justify="right", min_width=8)
    table.add_column("Author", style="blue", min_width=10, max_width=12)

    for idx, agent in enumerate(results, start=1):
        table.add_row(
            str(idx),
            _truncate(agent.get("name", "Unknown"), 20),
            _truncate(agent.get("description", "No description"), 27),
            _format_access(agent.get("access_level")),
            _format_number(agent.get("download_count", 0)),
            _format_rating(agent.get("average_rating")),
            _truncate(agent.get("owner_name", "Anonymous"), 12),
        )

    return table


def _display_results(results: list[dict], query: Optional[str] = None) -> None:
    """Display search results in a Rich table.

    Args:
        results: List of agent dictionaries from the API.
        query: The original search query for display.
    """
    global _last_search_results
    _last_search_results = results

    if not results:
        emit_info("No agents found matching your search criteria.")
        console.print("\n[dim]Try a different query or browse by category with:[/dim]")
        console.print("  [cyan]/search-agents --category data[/cyan]")
        return

    # Header with result count
    query_text = f' matching "[bold]{query}[/bold]"' if query else ""
    console.print(
        f"\n[cyan]🔍[/cyan] Found [bold]{len(results)}[/bold] agents{query_text}\n"
    )

    # Build and display the results table
    table = _build_results_table(results)
    console.print(table)

    # Help footer
    console.print(
        "\n[dim]Use[/dim] [cyan]/download-agent <name>[/cyan] "
        "[dim]to install an agent[/dim]"
    )


def _show_help() -> None:
    """Display help information for the search-agents command."""
    help_text = """
[bold cyan]Usage:[/bold cyan]
  /search-agents [query] [options]

[bold cyan]Examples:[/bold cyan]
  /search-agents data analysis
  /search-agents --category devops
  /search-agents sql --sort rating
  /search-agents --tag python --limit 10
  /search-agents --category data --sort recent

[bold cyan]Options:[/bold cyan]
  [green]query[/green]             Search terms (optional)
  [green]--category, -c[/green]    Filter by category (data, devops, frontend, etc.)
  [green]--tag, -t[/green]         Filter by tag
  [green]--sort, -s[/green]        Sort by: downloads, rating, or recent
  [green]--limit, -l[/green]       Maximum results (default: 20)
  [green]--help, -h[/green]        Show this help message

[bold cyan]Available Categories:[/bold cyan]
  data, devops, frontend, backend, security, testing, documentation

[bold cyan]Access Types:[/bold cyan]
  🌍 Public   - Available to everyone
  🔒 AD Grp   - Restricted to specific AD groups
  🔐 Private  - Author only (not shown in search)
    """
    console.print(
        Panel(help_text.strip(), title="🔍 Search Agents", border_style="cyan")
    )


def _filter_latest_versions(agents: list[dict]) -> list[dict]:
    """Filter agents to only show the most recent version of each agent.

    Args:
        agents: List of agent dictionaries from marketplace API

    Returns:
        List of agents with only the latest version of each agent name
    """
    if not agents:
        return agents

    # Group agents by name and track the latest version
    latest_by_name = {}

    for agent in agents:
        name = agent.get("name")
        if not name:
            continue

        version = agent.get("version", 1)

        # If we haven't seen this agent, or this is a newer version, keep it
        if name not in latest_by_name or version > latest_by_name[name].get(
            "version", 1
        ):
            latest_by_name[name] = agent

    # Return the filtered list, preserving the original order where possible
    # by keeping the first occurrence of each agent name
    seen_names = set()
    result = []

    for agent in agents:
        name = agent.get("name")
        if name and name not in seen_names:
            seen_names.add(name)
            result.append(latest_by_name[name])

    return result


async def _search_agents_async(
    query: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "downloads",
    limit: int = 20,
) -> list[dict]:
    """Perform the async search operation.

    Args:
        query: Search query string.
        category: Category filter.
        tag: Tag filter.
        sort: Sort order.
        limit: Maximum results.

    Returns:
        List of agent summaries.

    Raises:
        Exception: If the API call fails.
    """
    response = await api_client.search_agents(
        query=query,
        category=category,
        tags=[tag] if tag else None,
        sort=sort,
        limit=limit,
    )

    # api_client.search_agents returns a normalized response dict:
    # {"success": bool, "data": list, "error": str | None, "status_code": int}
    if not response.get("success"):
        error_msg = response.get("error", "Unknown error")
        raise Exception(error_msg)

    # Extract the actual list of agents from the data field
    data = response.get("data", [])

    # Handle multiple response formats:
    # 1. _normalize_response wraps API response: {"data": {"success": true, "data": [...]}}
    # 2. Direct list: {"data": [...]}
    # 3. Nested data with "agents" key: {"data": {"agents": [...]}}

    agents = []
    if isinstance(data, dict):
        # Check for double-wrapped response from _normalize_response
        if "data" in data:
            inner_data = data["data"]
            if isinstance(inner_data, list):
                agents = inner_data
            elif isinstance(inner_data, dict) and "agents" in inner_data:
                agents = inner_data["agents"]
        # Check for agents key directly
        elif "agents" in data:
            agents = data["agents"]
    elif isinstance(data, list):
        agents = data

    # Filter to only show the latest version of each agent
    return _filter_latest_versions(agents)


def handle_search_agents(command: str) -> bool:
    """Handle the /search-agents command.

    Supports:
      /search-agents [query]
      /search-agents --category data
      /search-agents --tag sql
      /search-agents --sort downloads|rating|recent
      /search-agents --help

    Args:
        command: The full command string including any arguments.

    Returns:
        bool: True to indicate the command was handled.
    """
    args = _parse_args(command)

    # Show help if requested
    if args.help:
        _show_help()
        return True

    # Combine query parts into a single string
    query = " ".join(args.query) if args.query else None

    # Check if marketplace token is valid before making API calls
    token_exists, is_valid = get_marketplace_token_status()

    if not token_exists or not is_valid:
        # Token missing or expired - auto-trigger authentication
        if not token_exists:
            console.print(
                "[yellow]🔐 No marketplace token found. Authenticating...[/yellow]"
            )
        else:
            console.print(
                "[yellow]🔐 Marketplace token expired. Authenticating...[/yellow]"
            )

        try:
            from code_puppy.plugins.walmart_specific.pingfed_auth import (
                handle_puppy_auth_command,
            )

            result = handle_puppy_auth_command("/puppy_auth", "puppy_auth")
            if not result:
                emit_error("Authentication failed. Please try again.")
                return True
        except ImportError:
            emit_error("Authentication module not available.")
            return True

    console.print("[cyan]🐶[/cyan] Searching the Agent Marketplace...")

    try:
        # Run the async search using the helper that handles event loop conflicts
        from code_puppy.plugins.agent_marketplace.api_client import run_async

        results = run_async(
            _search_agents_async(
                query=query,
                category=args.category,
                tag=args.tag,
                sort=args.sort,
                limit=args.limit,
            )
        )
        _display_results(results, query)

    except Exception as e:
        error_msg = str(e)

        # Handle common errors with friendly messages
        if "401" in error_msg or "403" in error_msg:
            emit_error("Authentication required. Please ensure you're logged in.")
        elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            emit_error("Request timed out. The server may be busy.")
        elif "connection" in error_msg.lower():
            emit_error("Connection error. Check your network connection.")
        else:
            emit_error(f"Search failed: {e}")

        console.print("\n[dim]Check your network connection or try again later.[/dim]")

    return True
