"""
Tests for ManagedMCPServer.
"""

import os
from unittest.mock import patch

import pytest

from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig


@pytest.mark.asyncio
async def test_managed_server_header_env_expansion_mocked():
    """Test that headers with env vars are expanded correctly (using mocks)."""

    config_dict = {
        "url": "http://test.com",
        "headers": {
            "Authorization": "Bearer ${TEST_API_KEY}",
            "X-Custom": "FixedValue",
        },
    }

    server_config = ServerConfig(
        id="test-id", name="test-server", type="http", config=config_dict
    )

    captured_headers = {}

    def mock_create_async_client(headers=None, **kwargs):
        # Capture the headers passed to create_async_client
        if headers:
            captured_headers.update(headers)
        return None  # Return value doesn't matter for this test

    with (
        patch.dict(os.environ, {"TEST_API_KEY": "secret-123"}),
        patch("code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"),
        patch(
            "code_puppy.mcp_.managed_server.create_async_client",
            side_effect=mock_create_async_client,
        ),
    ):
        ManagedMCPServer(server_config)

        # Verify headers were expanded correctly
        assert captured_headers["Authorization"] == "Bearer secret-123"
        assert captured_headers["X-Custom"] == "FixedValue"
