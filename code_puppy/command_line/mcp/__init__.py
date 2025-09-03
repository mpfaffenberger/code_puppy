"""
MCP Command Line Interface - Namespace package for MCP server management commands.

This package provides a modular command interface for managing MCP servers.
Each command is implemented in its own module for better maintainability.
"""

from .handler import MCPCommandHandler

__all__ = ["MCPCommandHandler"]
