"""Shared pytest fixtures for plugin tests."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.models import ModelRequestParameters


# Workaround for pydantic/MCP compatibility issue during pytest collection:
# Skip antigravity tests if pydantic/MCP conflict is detected
def pytest_configure(config):
    """Configure pytest with compatibility workarounds."""
    # Pre-patch sys.modules to provide a mock mcp.types during collection
    # This prevents the ValueError in pydantic's RootModel metaclass
    if "mcp" not in sys.modules:
        mcp_mock = MagicMock()
        mcp_mock.types = MagicMock()
        sys.modules["mcp"] = mcp_mock
        sys.modules["mcp.types"] = mcp_mock.types
        sys.modules["mcp.client"] = MagicMock()
        sys.modules["mcp.client.session"] = MagicMock()


@pytest.fixture
def mock_google_model():
    """Create a mock AntigravityModel instance for testing."""
    # Lazy import to avoid pydantic/MCP conflicts during conftest load
    from code_puppy.plugins.antigravity_oauth.antigravity_model import AntigravityModel

    with patch(
        "code_puppy.plugins.antigravity_oauth.antigravity_model.GoogleModel.__init__",
        return_value=None,
    ):
        model = AntigravityModel("gemini-1.5-pro")
        model._model_name = "gemini-1.5-pro"
        # Mock the _provider attribute which is accessed by the system property
        provider_mock = MagicMock()
        provider_mock.name = "google"
        model._provider = provider_mock
        model.client = MagicMock()
        model._get_instructions = MagicMock(return_value=None)
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
