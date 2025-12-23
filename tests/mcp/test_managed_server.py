"""
Tests for ManagedMCPServer.
"""

import os
import pytest
from unittest.mock import patch
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

    with (
        patch.dict(os.environ, {"TEST_API_KEY": "secret-123"}),
        patch("code_puppy.mcp_.managed_server.MCPServerStreamableHTTP") as MockHTTP,
    ):
        ManagedMCPServer(server_config)

        # Verify call args
        call_args = MockHTTP.call_args
        assert call_args is not None
        _, kwargs = call_args

        headers = kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer secret-123"
        assert headers["X-Custom"] == "FixedValue"
