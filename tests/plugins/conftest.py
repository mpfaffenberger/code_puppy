"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.models import ModelRequestParameters


# Workaround for pydantic/MCP compatibility issue during pytest collection:
# Skip antigravity tests if pydantic/MCP conflict is detected
def pytest_configure(config):
    """Configure pytest with compatibility workarounds."""
    # Pre-patch sys.modules to provide a lightweight MCP package during
    # collection. Some plugin tests only need the names to import cleanly, but
    # later suites may import pydantic_ai.mcp, which expects package-shaped
    # modules such as mcp.client.sse to exist.
    if "mcp" not in sys.modules:
        mcp_pkg = ModuleType("mcp")
        types_mod = ModuleType("mcp.types")
        client_pkg = ModuleType("mcp.client")
        session_mod = ModuleType("mcp.client.session")
        sse_mod = ModuleType("mcp.client.sse")
        stdio_mod = ModuleType("mcp.client.stdio")
        streamable_http_mod = ModuleType("mcp.client.streamable_http")
        shared_pkg = ModuleType("mcp.shared")
        exceptions_mod = ModuleType("mcp.shared.exceptions")
        context_mod = ModuleType("mcp.shared.context")
        message_mod = ModuleType("mcp.shared.message")
        session_shared_mod = ModuleType("mcp.shared.session")

        session_mod.ClientSession = MagicMock()
        session_mod.ElicitationFnT = MagicMock()
        session_mod.LoggingFnT = MagicMock()
        sse_mod.sse_client = MagicMock()
        stdio_mod.StdioServerParameters = MagicMock()
        stdio_mod.stdio_client = MagicMock()
        streamable_http_mod.streamable_http_client = MagicMock()
        context_mod.RequestContext = MagicMock()
        message_mod.SessionMessage = MagicMock()
        session_shared_mod.RequestResponder = MagicMock()

        mcp_pkg.types = types_mod
        mcp_pkg.client = client_pkg
        mcp_pkg.shared = shared_pkg
        client_pkg.session = session_mod
        client_pkg.sse = sse_mod
        client_pkg.stdio = stdio_mod
        client_pkg.streamable_http = streamable_http_mod
        shared_pkg.exceptions = exceptions_mod
        shared_pkg.context = context_mod
        shared_pkg.message = message_mod
        shared_pkg.session = session_shared_mod

        sys.modules["mcp"] = mcp_pkg
        sys.modules["mcp.types"] = types_mod
        sys.modules["mcp.client"] = client_pkg
        sys.modules["mcp.client.session"] = session_mod
        sys.modules["mcp.client.sse"] = sse_mod
        sys.modules["mcp.client.stdio"] = stdio_mod
        sys.modules["mcp.client.streamable_http"] = streamable_http_mod
        sys.modules["mcp.shared"] = shared_pkg
        sys.modules["mcp.shared.exceptions"] = exceptions_mod
        sys.modules["mcp.shared.context"] = context_mod
        sys.modules["mcp.shared.message"] = message_mod
        sys.modules["mcp.shared.session"] = session_shared_mod


class ClientShim:
    """A shim that makes client._api_client._async_httpx_client point to model._http_client."""

    def __init__(self, model):
        self._model = model
        self._api_client = ApiClientShim(model)


class ApiClientShim:
    """Inner shim for _api_client."""

    def __init__(self, model):
        self._model = model

    @property
    def _async_httpx_client(self):
        return self._model._http_client

    @_async_httpx_client.setter
    def _async_httpx_client(self, value):
        self._model._http_client = value


@pytest.fixture
def mock_google_model():
    """Create a mock AntigravityModel instance for testing."""
    # Lazy import to avoid pydantic/MCP conflicts during conftest load
    from code_puppy.plugins.antigravity_oauth.antigravity_model import AntigravityModel

    # Create the model with required api_key
    model = AntigravityModel(
        model_name="gemini-1.5-pro",
        api_key="test-api-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )

    # Set up an initial mock HTTP client
    model._http_client = AsyncMock()

    # Create a shim that keeps client._api_client._async_httpx_client in sync with _http_client
    model.client = ClientShim(model)

    return model


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """Create a mock httpx client."""
    return AsyncMock()


@pytest.fixture
def model_request_params() -> ModelRequestParameters:
    """Create model request parameters fixture."""
    return ModelRequestParameters(
        function_tools=[],
    )
