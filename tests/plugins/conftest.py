"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def pytest_configure(config):
    """Configure pytest with compatibility workarounds.

    Pre-patch sys.modules to provide a mock ``mcp.types`` during collection.
    This prevents a ValueError in pydantic's RootModel metaclass when MCP
    is not installed in the test environment.
    """
    if "mcp" not in sys.modules:
        mcp_mock = MagicMock()
        mcp_mock.types = MagicMock()
        sys.modules["mcp"] = mcp_mock
        sys.modules["mcp.types"] = mcp_mock.types
        sys.modules["mcp.client"] = MagicMock()
        sys.modules["mcp.client.session"] = MagicMock()
