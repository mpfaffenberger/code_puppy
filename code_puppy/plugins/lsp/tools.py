"""Agent-facing LSP tool registrations."""

from pydantic_ai import RunContext

from .manager import get_manager


def _register_definition(agent):
    @agent.tool
    async def lsp_definition(
        context: RunContext, file_path: str, line: int, column: int
    ):
        """Find the definition at a 1-based source position."""
        return await get_manager().definition(file_path, line, column)


def _register_references(agent):
    @agent.tool
    async def lsp_references(
        context: RunContext, file_path: str, line: int, column: int
    ):
        """Find references to the symbol at a 1-based source position."""
        return await get_manager().references(file_path, line, column)


def _register_hover(agent):
    @agent.tool
    async def lsp_hover(context: RunContext, file_path: str, line: int, column: int):
        """Return type/documentation hover information for a source position."""
        return await get_manager().hover(file_path, line, column)


def _register_diagnostics(agent):
    @agent.tool
    async def lsp_diagnostics(context: RunContext, file_path: str):
        """Return diagnostics published by the configured language server."""
        return await get_manager().diagnostics_for(file_path)


def _register_workspace_symbols(agent):
    @agent.tool
    async def lsp_workspace_symbols(context: RunContext, query: str):
        """Search symbols across the current workspace."""
        return await get_manager().workspace_symbols(query)


TOOL_DEFINITIONS = [
    {"name": "lsp_definition", "register_func": _register_definition},
    {"name": "lsp_references", "register_func": _register_references},
    {"name": "lsp_hover", "register_func": _register_hover},
    {"name": "lsp_diagnostics", "register_func": _register_diagnostics},
    {"name": "lsp_workspace_symbols", "register_func": _register_workspace_symbols},
]


def register_tools_callback():
    return TOOL_DEFINITIONS
