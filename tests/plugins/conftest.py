"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


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


@pytest.fixture(autouse=True)
def _ensure_plugin_callbacks_registered():
    """Re-register plugin callbacks that may have been wiped by clear_callbacks().

    ``tests/test_callbacks_extended.py`` calls ``clear_callbacks()`` in
    ``setup_method`` before each of its own tests.  Because Python caches
    module imports, the plugin modules never re-execute their module-level
    ``register_callback()`` calls afterward.  This fixture compensates by
    re-registering the specific callbacks that tests in *this* directory
    assert must be present.  ``register_callback`` deduplicates by function
    identity, so calling it multiple times is safe.
    """
    from code_puppy.callbacks import get_callbacks, register_callback

    # claude_code_hooks (test file is immutable — fixture lives here)
    try:
        from code_puppy.plugins.claude_code_hooks.register_callbacks import (
            on_post_tool_call_hook,
            on_pre_tool_call_hook,
        )

        if on_pre_tool_call_hook not in get_callbacks("pre_tool_call"):
            register_callback("pre_tool_call", on_pre_tool_call_hook)
        if on_post_tool_call_hook not in get_callbacks("post_tool_call"):
            register_callback("post_tool_call", on_post_tool_call_hook)
    except Exception:
        pass  # never crash the test suite

    yield
