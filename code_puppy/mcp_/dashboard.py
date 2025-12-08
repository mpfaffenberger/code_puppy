"""
MCP Dashboard Implementation

Provides visual status dashboard for MCP servers using Rich tables.
"""

from datetime import datetime
from typing import Dict, List, Optional

from rich import box
from rich.console import Console
from rich.table import Table

from .manager import get_mcp_manager
from .status_tracker import ServerState


class MCPDashboard:
    """Visual dashboard for MCP server status monitoring.

    Note: This class uses Rich Console directly for rendering Rich tables.
    This is intentional - Rich tables require Console for proper formatting.
    """

    def __init__(self):
        """Initialize the MCP Dashboard."""
        # Note: Console is used here specifically for Rich table rendering
        self._console = Console()

    def render_dashboard(self) -> Table:
        """
        Render the main MCP server status dashboard

        Returns:
            Table: Rich table with server status information
        """
        # Create the main table
        table = Table(
            title="MCP Server Status Dashboard",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold blue",
            title_style="bold cyan",
        )

        # Define columns
        table.add_column("Name", style="white", no_wrap=True, min_width=10)
        table.add_column("Type", style="white", no_wrap=True, width=8)
        table.add_column("State", style="white", no_wrap=True, width=8)
        table.add_column("Health", style="white", no_wrap=True, width=8)
        table.add_column("Uptime", style="white", no_wrap=True, width=10)
        table.add_column("Latency", style="white", no_wrap=True, width=10)

        # Get manager and server info
        try:
            manager = get_mcp_manager()
            servers = manager.list_servers()

            if not servers:
                # Empty state
                table.add_row(
                    "[dim]No servers configured[/dim]", "-", "-", "-", "-", "-"
                )
            else:
                # Add row for each server
                for server in servers:
                    row_data = self.render_server_row(server)
                    table.add_row(*row_data)

        except Exception as e:
            # Error state
            table.add_row(
                "[red]Error loading servers[/red]",
                "-",
                "-",
                "-",
                "-",
                f"[red]{str(e)}[/red]",
            )

        return table

    def render_server_row(self, server) -> List[str]:
        """
        Render a single server row for the dashboard

        Args:
            server: ServerInfo object with server details

        Returns:
            List[str]: Formatted row data for the table
        """
        # Server name
        name = server.name or server.id[:8]

        # Server type
        server_type = server.type.upper() if server.type else "UNK"

        # State indicator
        state_indicator = self.render_state_indicator(server.state)

        # Health indicator
        health_indicator = self.render_health_indicator(server.health)

        # Uptime
        uptime_str = self.format_uptime(server.start_time) if server.start_time else "-"

        # Latency
        latency_str = (
            self.format_latency(server.latency_ms)
            if server.latency_ms is not None
            else "-"
        )

        return [
            name,
            server_type,
            state_indicator,
            health_indicator,
            uptime_str,
            latency_str,
        ]

    def render_health_indicator(self, health: Optional[Dict]) -> str:
        """
        Render health status indicator

        Args:
            health: Health status dictionary or None

        Returns:
            str: Formatted health indicator with color
        """
        if not health:
            return "[dim]?[/dim]"

        is_healthy = health.get("is_healthy", False)
        error = health.get("error")

        if is_healthy:
            return "[green]✓[/green]"
        elif error:
            return "[red]✗[/red]"
        else:
            return "[yellow]?[/yellow]"

    def render_state_indicator(self, state: ServerState) -> str:
        """
        Render server state indicator

        Args:
            state: Current server state

        Returns:
            str: Formatted state indicator with color and symbol
        """
        indicators = {
            ServerState.RUNNING: "[green]✓ Run[/green]",
            ServerState.STOPPED: "[red]✗ Stop[/red]",
            ServerState.ERROR: "[red]⚠ Err[/red]",
            ServerState.STARTING: "[yellow]⏳ Start[/yellow]",
            ServerState.STOPPING: "[yellow]⏳ Stop[/yellow]",
            ServerState.QUARANTINED: "[yellow]⏸ Quar[/yellow]",
        }

        return indicators.get(state, "[dim]? Unk[/dim]")

    def render_metrics_summary(self, metrics: Dict) -> str:
        """
        Render a summary of server metrics

        Args:
            metrics: Dictionary of server metrics

        Returns:
            str: Formatted metrics summary
        """
        if not metrics:
            return "No metrics"

        parts = []

        # Request count
        if "request_count" in metrics:
            parts.append(f"Req: {metrics['request_count']}")

        # Error rate
        if "error_rate" in metrics:
            error_rate = metrics["error_rate"]
            if error_rate > 0.1:  # 10%
                parts.append(f"[red]Err: {error_rate:.1%}[/red]")
            elif error_rate > 0.05:  # 5%
                parts.append(f"[yellow]Err: {error_rate:.1%}[/yellow]")
            else:
                parts.append(f"[green]Err: {error_rate:.1%}[/green]")

        # Response time
        if "avg_response_time" in metrics:
            avg_time = metrics["avg_response_time"]
            parts.append(f"Avg: {avg_time:.0f}ms")

        return " | ".join(parts) if parts else "No data"

    def format_uptime(self, start_time: datetime) -> str:
        """
        Format uptime duration in human readable format

        Args:
            start_time: Server start timestamp

        Returns:
            str: Formatted uptime string (e.g., "2h 15m")
        """
        if not start_time:
            return "-"

        try:
            uptime = datetime.now() - start_time

            # Handle negative uptime (clock skew, etc.)
            if uptime.total_seconds() < 0:
                return "0s"

            # Format based on duration
            total_seconds = int(uptime.total_seconds())

            if total_seconds < 60:  # Less than 1 minute
                return f"{total_seconds}s"
            elif total_seconds < 3600:  # Less than 1 hour
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                if seconds > 0:
                    return f"{minutes}m {seconds}s"
                else:
                    return f"{minutes}m"
            elif total_seconds < 86400:  # Less than 1 day
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                if minutes > 0:
                    return f"{hours}h {minutes}m"
                else:
                    return f"{hours}h"
            else:  # 1 day or more
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                if hours > 0:
                    return f"{days}d {hours}h"
                else:
                    return f"{days}d"

        except Exception:
            return "?"

    def format_latency(self, latency_ms: float) -> str:
        """
        Format latency in human readable format

        Args:
            latency_ms: Latency in milliseconds

        Returns:
            str: Formatted latency string with color coding
        """
        if latency_ms is None:
            return "-"

        try:
            if latency_ms < 0:
                return "invalid"
            elif latency_ms < 50:  # Fast
                return f"[green]{latency_ms:.0f}ms[/green]"
            elif latency_ms < 200:  # Acceptable
                return f"[yellow]{latency_ms:.0f}ms[/yellow]"
            elif latency_ms < 1000:  # Slow
                return f"[red]{latency_ms:.0f}ms[/red]"
            elif latency_ms >= 30000:  # Timeout (30s+)
                return "[red]timeout[/red]"
            else:  # Very slow
                seconds = latency_ms / 1000
                return f"[red]{seconds:.1f}s[/red]"

        except (ValueError, TypeError):
            return "error"

    def print_dashboard(self) -> None:
        """Print the dashboard to console.

        Note: Uses Rich Console directly for table rendering - Rich tables
        require Console for proper formatting with colors and borders.
        """
        table = self.render_dashboard()
        self._console.print(table)
        self._console.print()  # Add spacing

    def get_dashboard_string(self) -> str:
        """
        Get dashboard as a string for programmatic use

        Returns:
            str: Dashboard rendered as plain text
        """
        # Create a console that captures output
        console = Console(file=None, width=80)

        with console.capture() as capture:
            console.print(self.render_dashboard())

        return capture.get()
