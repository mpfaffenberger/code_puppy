"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolate_plugin_skills(request, monkeypatch):
    """Prevent built-in plugin skills (e.g. mist-agent) from leaking
    into skill-discovery tests that assert exact filesystem-only counts.

    Tests that *want* the real plugin-skill collector to run mark themselves
    with ``@pytest.mark.plugin_skills`` to opt out of the isolation.
    """
    if request.node.get_closest_marker("plugin_skills"):
        return

    from code_puppy.plugins.agent_skills import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_collect_plugin_skills", lambda: [])


def pytest_configure(config):
    """Configure pytest with compatibility workarounds.

    Prefer the real ``mcp`` package when it is importable. Only fall back to
    stubs in slim environments where it is genuinely unavailable, and stub all
    submodules that ``pydantic_ai.mcp`` imports during collection.
    """
    config.addinivalue_line(
        "markers",
        "plugin_skills: opt out of _isolate_plugin_skills so the real "
        "plugin-skill collector runs",
    )

    try:
        import mcp  # noqa: F401
        import mcp.client.session  # noqa: F401
        import mcp.client.sse  # noqa: F401
        import mcp.client.streamable_http  # noqa: F401
        import mcp.types  # noqa: F401

        return
    except Exception:
        pass

    mcp_mock = MagicMock()
    client_mock = MagicMock()
    mcp_mock.types = MagicMock()
    mcp_mock.client = client_mock
    client_mock.session = MagicMock()
    client_mock.sse = MagicMock()
    client_mock.streamable_http = MagicMock()

    sys.modules["mcp"] = mcp_mock
    sys.modules["mcp.types"] = mcp_mock.types
    sys.modules["mcp.client"] = client_mock
    sys.modules["mcp.client.session"] = client_mock.session
    sys.modules["mcp.client.sse"] = client_mock.sse
    sys.modules["mcp.client.streamable_http"] = client_mock.streamable_http
