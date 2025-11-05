"""Integration tests for Confluence functionality."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from code_puppy.plugins.walmart_specific.confluence_client import (
    ConfluenceClient,
)
from code_puppy.tools.confluence_tools import search_confluence
from code_puppy.agents.agent_confluence_search import ConfluenceSearchAgent


@pytest.fixture
def mock_confluence_client():
    """Create a mock ConfluenceClient."""
    client = Mock(spec=ConfluenceClient)
    client.close = AsyncMock()
    return client


class TestConfluenceToolsIntegration:
    """Integration tests for Confluence tools."""

    @pytest.mark.asyncio
    async def test_search_confluence_tool(self, mock_confluence_client):
        """Test search_confluence tool integration."""
        # Mock the search_content method to return the expected API response
        mock_api_response = {
            "results": [
                {
                    "id": "123",
                    "title": "Test Documentation",
                    "type": "page",
                    "space": {"key": "TECH", "name": "Technology"},
                    "_links": {"webui": "/pages/viewpage.action?pageId=123"},
                    "excerpt": "This is test documentation",
                }
            ],
            "size": 1,
        }

        mock_confluence_client.search_content = Mock(return_value=mock_api_response)

        with patch(
            "code_puppy.tools.confluence_tools.get_confluence_client",
            return_value=mock_confluence_client,
        ):
            result = await search_confluence(query="API documentation", limit=10)

            assert "Test Documentation" in result
            assert "TECH" in result


class TestConfluenceAgentIntegration:
    """Integration tests for ConfluenceSearchAgent."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test ConfluenceSearchAgent initialization."""
        agent = ConfluenceSearchAgent()

        assert agent.name == "confluence-search"
        assert agent.display_name == "Confluence Search 📚"
