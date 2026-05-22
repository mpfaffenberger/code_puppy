"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def pytest_configure(config):
    """Configure pytest with compatibility workarounds.

    Pre-patch sys.modules to provide a mock ``mcp.types`` during collection,
    but only when the real ``mcp`` package is not importable. Previously we
    checked ``"mcp" not in sys.modules`` which is true on a clean start —
    that installed MagicMocks for ``mcp.client`` etc. and then, when other
    tests (e.g. ``tests/agents/test_compaction.py``) transitively imported
    ``pydantic_ai.mcp``, its ``from mcp.client.sse import sse_client`` blew
    up with "'mcp.client' is not a package" because the MagicMock had no
    ``__path__``.

    Real ``mcp`` is installed in this project's dev environment, so the
    mock path is only needed in bare CI images. Probe with a real import
    first; only fall back to mocks if that fails.
    """
    try:
        import mcp  # noqa: F401
        import mcp.types  # noqa: F401
    except ImportError:
        mcp_mock = MagicMock()
        mcp_mock.types = MagicMock()
        sys.modules["mcp"] = mcp_mock
        sys.modules["mcp.types"] = mcp_mock.types
        sys.modules["mcp.client"] = MagicMock()
        sys.modules["mcp.client.session"] = MagicMock()
