"""Universal Constructor (UC) slash command handler.

Provides the /uc command for managing custom UC tools.
"""

from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import emit_error, emit_info, emit_warning


def _list_tools() -> bool:
    """List all UC tools including disabled ones.

    Returns:
        True always (command completed).
    """
    from rich.table import Table

    from code_puppy.plugins.universal_constructor.registry import get_registry

    registry = get_registry()

    # Force a fresh scan to pick up any new tools
    registry.scan()

    # Get ALL tools including disabled ones
    tools = registry.list_tools(include_disabled=True)

    if not tools:
        emit_info("No UC tools found.")
        emit_info("Tools are stored in: ~/.code_puppy/plugins/universal_constructor/")
        emit_info("Ask the LLM to create one with: 'Create a UC tool that...'")
        return True

    # Build a Rich table
    table = Table(
        title="🔧 Universal Constructor Tools",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Namespace", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Description", style="white")

    for tool in tools:
        # Status indicator
        status = (
            "[green]✓ enabled[/green]" if tool.meta.enabled else "[red]✗ disabled[/red]"
        )

        # Namespace display
        namespace = tool.meta.namespace if tool.meta.namespace else "[dim](root)[/dim]"

        # Truncate long descriptions
        desc = tool.meta.description
        if len(desc) > 50:
            desc = desc[:47] + "..."

        table.add_row(
            tool.meta.name,
            namespace,
            status,
            desc,
        )

    emit_info(table)

    # Summary
    enabled_count = sum(1 for t in tools if t.meta.enabled)
    emit_info(
        f"\n[dim]Total: {len(tools)} tools ({enabled_count} enabled, {len(tools) - enabled_count} disabled)[/dim]"
    )
    emit_info("[dim]Use '/uc info <name>' to see tool details[/dim]")

    return True


def _show_tool_info(tool_name: str) -> bool:
    """Show detailed information about a specific tool.

    Args:
        tool_name: Name of the tool to show info for.

    Returns:
        True always (command completed).
    """
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    from code_puppy.plugins.universal_constructor.registry import get_registry

    registry = get_registry()
    registry.scan()  # Ensure fresh data

    tool = registry.get_tool(tool_name)

    if tool is None:
        # Try to find a partial match
        all_tools = registry.list_tools(include_disabled=True)
        matches = [t for t in all_tools if tool_name.lower() in t.full_name.lower()]

        if matches:
            emit_error(f"Tool '{tool_name}' not found.")
            emit_info("Did you mean one of these?")
            for t in matches:
                emit_info(f"  • {t.full_name}")
        else:
            emit_error(f"Tool '{tool_name}' not found.")
            emit_info("Use '/uc list' to see all available tools.")
        return True

    # Build detailed info display
    info_lines = Text()
    info_lines.append("Name: ", style="bold")
    info_lines.append(f"{tool.meta.name}\n")

    if tool.meta.namespace:
        info_lines.append("Namespace: ", style="bold")
        info_lines.append(f"{tool.meta.namespace}\n")

    info_lines.append("Full Name: ", style="bold")
    info_lines.append(f"{tool.full_name}\n")

    info_lines.append("Status: ", style="bold")
    if tool.meta.enabled:
        info_lines.append("✓ enabled\n", style="green")
    else:
        info_lines.append("✗ disabled\n", style="red")

    info_lines.append("Version: ", style="bold")
    info_lines.append(f"{tool.meta.version}\n")

    if tool.meta.author:
        info_lines.append("Author: ", style="bold")
        info_lines.append(f"{tool.meta.author}\n")

    info_lines.append("\nDescription: ", style="bold")
    info_lines.append(f"{tool.meta.description}\n")

    info_lines.append("\nSignature: ", style="bold")
    info_lines.append(f"{tool.signature}\n", style="cyan")

    if tool.docstring:
        info_lines.append("\nDocstring: ", style="bold")
        info_lines.append(f"{tool.docstring}\n", style="dim")

    info_lines.append("\nSource Path: ", style="bold")
    info_lines.append(f"{tool.source_path}\n", style="dim")

    # Create panel for metadata
    panel = Panel(
        info_lines,
        title=f"[bold cyan]🔧 Tool: {tool.full_name}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )
    emit_info(panel)

    # Show source code with syntax highlighting
    try:
        source_code = tool.source_path.read_text()
        syntax = Syntax(
            source_code,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        source_panel = Panel(
            syntax,
            title="[bold yellow]📄 Source Code[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
        emit_info(source_panel)
    except Exception as e:
        emit_warning(f"Could not read source code: {e}")

    return True


@register_command(
    name="uc",
    description="Universal Constructor - manage custom tools",
    usage="/uc [list|info <name>]",
    category="tools",
)
def handle_uc_command(command: str) -> bool:
    """Handle the /uc command for Universal Constructor.

    Subcommands:
        /uc or /uc list - List all tools (including disabled)
        /uc info <name> - Show detailed info for a specific tool

    Args:
        command: The full command string (e.g., '/uc info my_tool').

    Returns:
        True always (command completed).
    """
    import shlex

    # Parse the command
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    # /uc with no args → list
    if len(tokens) == 1:
        return _list_tools()

    subcommand = tokens[1].lower()

    if subcommand == "list":
        return _list_tools()

    elif subcommand == "info":
        if len(tokens) < 3:
            emit_error("Usage: /uc info <tool_name>")
            emit_info("Example: /uc info weather_api")
            return True
        tool_name = tokens[2]
        return _show_tool_info(tool_name)

    else:
        emit_warning(f"Unknown subcommand: {subcommand}")
        emit_info("Usage:")
        emit_info("  /uc           - List all UC tools")
        emit_info("  /uc list      - List all UC tools")
        emit_info("  /uc info <n>  - Show details for tool <n>")
        return True
