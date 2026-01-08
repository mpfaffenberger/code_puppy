"""Handler for the /download-agent command.

Provides downloading functionality for agents from the marketplace with
hash-based update detection and caching.
"""

import argparse
import asyncio
import hashlib
import json
import shlex
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from code_puppy.messaging import emit_error, emit_info, emit_warning

from . import api_client
from .search import get_last_search_results

console = Console()

# Default directories
AGENTS_DIR = Path.home() / ".code_puppy" / "agents"
HASHES_FILE = Path.home() / ".code_puppy" / "agent_hashes.json"


# ============================================================================
# Hash Management
# ============================================================================


def _load_hashes() -> dict:
    """Load the local agent hashes from disk.

    Returns:
        Dictionary mapping agent names to their hash info:
        {
            "agent-name": {
                "hash": "abc123...",
                "version": "v1",
                "downloaded_at": "2024-01-15T10:30:00Z"
            }
        }
    """
    if not HASHES_FILE.exists():
        return {}

    try:
        with open(HASHES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_hashes(hashes: dict) -> None:
    """Save the agent hashes to disk.

    Args:
        hashes: Dictionary of agent hashes to save.
    """
    HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2, ensure_ascii=False)


def _compute_hash(agent_data: dict) -> str:
    """Compute a hash for agent data.

    Args:
        agent_data: The agent definition dictionary.

    Returns:
        SHA256 hash string (first 12 characters).
    """
    # Normalize the data for consistent hashing
    normalized = json.dumps(agent_data, sort_keys=True, ensure_ascii=False)
    full_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return full_hash[:12]


def _get_local_hash(name: str) -> Optional[dict]:
    """Get local hash info for an agent.

    Args:
        name: Agent name.

    Returns:
        Hash info dict if exists, None otherwise.
    """
    hashes = _load_hashes()
    return hashes.get(name)


def _update_local_hash(
    name: str, agent_hash: str, version: str, downloaded_at: str
) -> None:
    """Update local hash cache for an agent.

    Args:
        name: Agent name.
        agent_hash: The computed hash.
        version: Version string.
        downloaded_at: ISO timestamp.
    """
    hashes = _load_hashes()
    hashes[name] = {
        "hash": agent_hash,
        "version": version,
        "downloaded_at": downloaded_at,
    }
    _save_hashes(hashes)


# ============================================================================
# File Management
# ============================================================================


def _ensure_agents_dir() -> Path:
    """Ensure the agents directory exists.

    Returns:
        Path to the agents directory.
    """
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    return AGENTS_DIR


def _get_agent_path(name: str) -> Path:
    """Get the path for an agent file.

    Args:
        name: The agent name.

    Returns:
        Full path to the agent JSON file.
    """
    # Sanitize the name for filesystem use
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return _ensure_agents_dir() / f"{safe_name}.json"


def _agent_exists(name: str) -> bool:
    """Check if an agent with this name already exists locally.

    Args:
        name: The agent name.

    Returns:
        True if the agent file already exists.
    """
    return _get_agent_path(name).exists()


def _save_agent(agent_data: dict, name: str) -> Path:
    """Save agent data to a JSON file.

    Args:
        agent_data: The agent definition dictionary.
        name: The name to save the agent as.

    Returns:
        Path to the saved file.
    """
    path = _get_agent_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(agent_data, f, indent=2, ensure_ascii=False)
    return path


def _format_path(path: Path) -> str:
    """Format path for display (with ~ for home).

    Args:
        path: Path to format.

    Returns:
        Human-readable path string.
    """
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


# ============================================================================
# Command Parsing
# ============================================================================


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for download-agent command.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="/download-agent",
        description="Download an agent from the marketplace",
        add_help=False,
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Name of the agent to download",
    )
    parser.add_argument(
        "--check",
        "-C",
        metavar="NAME",
        type=str,
        help="Check if an update is available for the specified agent",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force download without update prompts",
    )
    parser.add_argument(
        "--help",
        "-h",
        action="store_true",
        help="Show this help message",
    )
    return parser


def _parse_args(command: str) -> argparse.Namespace:
    """Parse the download-agent command arguments.

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
        tokens = shlex.split(args_str)
        return parser.parse_args(tokens)
    except (ValueError, SystemExit):
        return parser.parse_args([])


# ============================================================================
# Interactive Selection
# ============================================================================


def _show_recent_results() -> Optional[str]:
    """Show recent search results and prompt for selection.

    Returns:
        Selected agent name, or None if cancelled.
    """
    results = get_last_search_results()

    if not results:
        emit_info("No recent search results available.")
        console.print(
            "\n[dim]Run[/dim] [cyan]/search-agents <query>[/cyan] "
            "[dim]first to find agents.[/dim]"
        )
        return None

    # Display compact table of recent results
    console.print("\n[cyan]📝[/cyan] Recent search results:\n")

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Name", style="green")
    table.add_column("Description", max_width=40)

    # Limit to 10 for readability
    display_results = results[:10]
    for idx, agent in enumerate(display_results, start=1):
        desc = agent.get("description", "No description")
        if len(desc) > 40:
            desc = desc[:39] + "…"
        table.add_row(
            str(idx),
            agent.get("name", "Unknown"),
            desc,
        )

    console.print(table)

    # Prompt for selection
    console.print()
    selection = Prompt.ask(
        "[cyan]Enter number to download (or agent name, 'q' to cancel)[/cyan]",
        default="q",
    )

    if selection.lower() == "q":
        emit_info("Download cancelled.")
        return None

    # Handle numeric selection
    try:
        idx = int(selection)
        if 1 <= idx <= len(display_results):
            return display_results[idx - 1].get("name")
        else:
            emit_error(
                f"Invalid selection: {idx}. Please choose 1-{len(display_results)}."
            )
            return None
    except ValueError:
        # Treat as agent name
        return selection.strip()


def _prompt_for_agent_name() -> Optional[str]:
    """Prompt the user for an agent name interactively.

    Returns:
        Agent name, or None if cancelled.
    """
    results = get_last_search_results()

    if results:
        return _show_recent_results()

    # No recent results, prompt for name or suggest search
    console.print(
        "\n[cyan]🐶[/cyan] No agent name provided. You can:\n"
        "  [green]1.[/green] Enter an agent name directly\n"
        "  [green]2.[/green] Search for agents first with [cyan]/search-agents[/cyan]"
    )

    name = Prompt.ask(
        "\n[cyan]Enter agent name (or 'q' to cancel)[/cyan]",
        default="q",
    )

    if name.lower() == "q":
        emit_info("Download cancelled.")
        return None

    return name.strip()


# ============================================================================
# Update Checking
# ============================================================================


async def _check_update_async(name: str, local_hash: str) -> dict:
    """Check for updates asynchronously.

    Args:
        name: Agent name/ID.
        local_hash: Local hash to compare.

    Returns:
        Update info from API.
    """
    return await api_client.check_update(name, local_hash)


def _handle_check_command(name: str) -> bool:
    """Handle the --check flag to check for updates.

    Args:
        name: Agent name to check.

    Returns:
        True always (command handled).
    """
    console.print(f"\n[cyan]🔍[/cyan] Checking for updates to [bold]{name}[/bold]...")

    # Check if we have this agent locally
    local_info = _get_local_hash(name)

    if not local_info:
        emit_warning(f"Agent '{name}' is not installed locally.")
        console.print(
            f"\n[dim]Use[/dim] [cyan]/download-agent {name}[/cyan] "
            "[dim]to install it.[/dim]"
        )
        return True

    local_hash = local_info.get("hash", "")
    local_version = local_info.get("version", "unknown")

    try:
        from code_puppy.plugins.agent_marketplace.api_client import run_async
        update_info = run_async(_check_update_async(name, local_hash))

        if update_info.get("update_available", False):
            latest_version = update_info.get("latest_version", "unknown")
            latest_hash = update_info.get("latest_hash", "unknown")

            console.print(f"\n[yellow]⚠️  Update available for {name}![/yellow]\n")
            console.print(f"  [dim]Local:[/dim]  {local_version} (hash: {local_hash})")
            console.print(
                f"  [dim]Latest:[/dim] {latest_version} (hash: {latest_hash})"
            )

            # Show changelog if available
            changelog = update_info.get("changelog")
            if changelog:
                console.print(f"\n  [dim]Changes:[/dim] {changelog}")

            console.print(
                f"\n[dim]Use[/dim] [cyan]/download-agent {name}[/cyan] "
                "[dim]to update[/dim]"
            )
        else:
            console.print(
                f"\n[green]✓[/green] [bold]{name}[/bold] is up to date "
                f"({local_version}, hash: {local_hash})"
            )

    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
            emit_error(f"Agent '{name}' not found in the marketplace.")
        else:
            emit_error(f"Failed to check for updates: {e}")

    return True


def _prompt_for_update(name: str, local_version: str, latest_version: str) -> bool:
    """Prompt user to confirm update download.

    Args:
        name: Agent name.
        local_version: Current local version.
        latest_version: Available version.

    Returns:
        True if user wants to update.
    """
    console.print(f"\n[yellow]⚠️  Update available![/yellow]")
    console.print(f"  [dim]Local version:[/dim]  {local_version}")
    console.print(f"  [dim]Latest version:[/dim] {latest_version}\n")

    return Confirm.ask("Download update?", default=True)


# ============================================================================
# Download Flow
# ============================================================================


async def _download_agent_async(name: str) -> dict:
    """Perform the async download operation.

    Args:
        name: The agent name/ID to download.

    Returns:
        Agent definition dictionary.

    Raises:
        Exception: If download fails.
    """
    response = await api_client.download_agent(name)
    
    # Check for success
    if not response.get("success"):
        error_msg = response.get("error", "Download failed")
        raise Exception(error_msg)
    
    # Extract the agent data from the response
    # API returns: {success: true, data: {agent: {...}, version: ..., content_hash: ...}}
    data = response.get("data", {})
    
    # Handle nested structure from API
    if isinstance(data, dict):
        # If data has an "agent" key, return just the agent
        if "agent" in data:
            agent = data["agent"]
            # Preserve version info at top level for hash tracking
            agent["_version"] = data.get("version")
            agent["_content_hash"] = data.get("content_hash")
            return agent
        # If data has "data" key (double-wrapped), unwrap it
        if "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "agent" in inner:
                agent = inner["agent"]
                agent["_version"] = inner.get("version")
                agent["_content_hash"] = inner.get("content_hash")
                return agent
            return inner
    
    return data


def _display_success(name: str, path: Path, version: str, agent_hash: str) -> None:
    """Display success message with version/hash info.

    Args:
        name: The downloaded agent name.
        path: Path where the agent was saved.
        version: Version string.
        agent_hash: The agent hash.
    """
    display_path = _format_path(path)

    success_text = f"""
[green]✓ Downloaded successfully![/green]

  [dim]Version:[/dim] {version}
  [dim]Hash:[/dim]    {agent_hash}
  [dim]Saved to:[/dim] [cyan]{display_path}[/cyan]

[bold]To use this agent:[/bold]

  [green]/agent {name}[/green]
    """
    console.print(Panel(success_text.strip(), title=f"🐶 {name}", border_style="green"))


def _show_help() -> None:
    """Display help information for the download-agent command."""
    help_text = """
[bold cyan]Usage:[/bold cyan]
  /download-agent <name>         Download a specific agent
  /download-agent                Interactive mode (from recent search)
  /download-agent --check <name> Check if an update is available

[bold cyan]Examples:[/bold cyan]
  /download-agent data-analyzer
  /download-agent --check sql-helper
  /download-agent -C bigquery-explorer
  /download-agent --force data-analyzer

[bold cyan]Options:[/bold cyan]
  [green]name[/green]           Name of the agent to download
  [green]--check, -C[/green]    Check for updates without downloading
  [green]--force, -f[/green]    Force download without confirmation prompts
  [green]--help, -h[/green]     Show this help message

[bold cyan]Update Detection:[/bold cyan]
  Downloaded agents are tracked with content hashes.
  When re-downloading, you'll be prompted if an update exists.
  Local hashes are stored in ~/.code_puppy/agent_hashes.json
    """
    console.print(
        Panel(help_text.strip(), title="⬇️  Download Agent", border_style="cyan")
    )


def _get_timestamp() -> str:
    """Get current ISO timestamp.

    Returns:
        ISO format timestamp string.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def handle_download_agent(command: str) -> bool:
    """Handle the /download-agent command.

    Supports:
      /download-agent <name>         - Download specific agent
      /download-agent                - Interactive mode
      /download-agent --check <name> - Check if update available
      /download-agent --force <name> - Force download without prompts

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

    # Handle --check flag
    if args.check:
        return _handle_check_command(args.check)

    # Get agent name (from args or interactively)
    agent_name = args.name
    if not agent_name:
        agent_name = _prompt_for_agent_name()
        if not agent_name:
            return True  # User cancelled

    # Check for existing agent and updates
    local_info = _get_local_hash(agent_name)
    force_download = args.force
    
    # Also verify the actual agent file exists (not just the hash cache)
    agent_file_path = _get_agent_path(agent_name)
    agent_file_exists = agent_file_path.exists()
    
    if local_info and agent_file_exists and not force_download:
        # Agent exists locally - check for updates
        local_hash = local_info.get("hash", "")
        local_version = local_info.get("version", "v?")

        console.print(f'[cyan]🐶[/cyan] Checking for updates to "{agent_name}"...')

        try:
            from code_puppy.plugins.agent_marketplace.api_client import run_async
            update_info = run_async(_check_update_async(agent_name, local_hash))

            if update_info.get("update_available", False):
                latest_version = update_info.get("latest_version", "v?")

                # Prompt user
                if not _prompt_for_update(agent_name, local_version, latest_version):
                    emit_info("Download cancelled.")
                    return True
            else:
                # Already up to date
                console.print(
                    f"\n[green]✓[/green] [bold]{agent_name}[/bold] is already "
                    f"up to date ({local_version})\n"
                )
                return True

        except Exception as e:
            # If check fails, proceed with download anyway
            emit_warning(f"Could not check for updates: {e}")
            if not Confirm.ask("Continue with download?", default=True):
                return True

    # Download the agent
    console.print(f'\n[cyan]🐶[/cyan] Fetching agent "{agent_name}"...')

    try:
        from code_puppy.plugins.agent_marketplace.api_client import run_async
        agent_data = run_async(_download_agent_async(agent_name))

        # Extract version info from response
        version = agent_data.get("version", "v1")
        # Compute hash from agent data
        agent_hash = _compute_hash(agent_data)

        # Save the agent
        path = _save_agent(agent_data, agent_name)

        # Update hash cache
        _update_local_hash(
            name=agent_name,
            agent_hash=agent_hash,
            version=version,
            downloaded_at=_get_timestamp(),
        )

        _display_success(agent_name, path, version, agent_hash)

    except Exception as e:
        error_msg = str(e)

        # Handle common errors with friendly messages
        if "404" in error_msg or "not found" in error_msg.lower():
            emit_error(f'Agent "{agent_name}" not found in the marketplace.')
            console.print(
                "\n[dim]Use[/dim] [cyan]/search-agents[/cyan] "
                "[dim]to find available agents.[/dim]"
            )
        elif "401" in error_msg:
            emit_error("Authentication required. Please log in first.")
        elif "403" in error_msg:
            emit_error(
                f"Access denied. You may not have permission to download "
                f'"{agent_name}".'
            )
            console.print(
                "\n[dim]This agent may be restricted to specific AD groups.[/dim]"
            )
        elif "timeout" in error_msg.lower():
            emit_error("Request timed out. The server may be busy.")
        else:
            emit_error(f"Download failed: {e}")
            console.print(
                "\n[dim]Check your network connection or try again later.[/dim]"
            )

    return True
