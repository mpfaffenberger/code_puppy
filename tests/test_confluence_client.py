"""Unit tests for ConfluenceClient."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from code_puppy.plugins.walmart_specific.confluence_client import (
    ConfluenceClient,
    ConfluenceSearchResult,
)
from code_puppy.plugins.walmart_specific.confluence_auth import ConfluenceAuth


@pytest.fixture
def mock_auth():
    """Create a mock ConfluenceAuth instance."""
    auth = Mock(spec=ConfluenceAuth)
    auth.get_token = AsyncMock(return_value="mock-token-12345")
    auth.base_url = "https://confluence.walmart.com"
    return auth


@pytest.fixture
def confluence_client(mock_auth):
    """Create a ConfluenceClient instance with mocked auth."""
    return ConfluenceClient(auth=mock_auth)


class TestConfluenceClient:
    """Test suite for ConfluenceClient."""

    @pytest.mark.asyncio
    async def test_init(self, mock_auth):
        """Test ConfluenceClient initialization."""
        client = ConfluenceClient(auth=mock_auth)
        assert client.auth == mock_auth
        assert client.base_url == "https://confluence.walmart.com"

    @pytest.mark.asyncio
    async def test_search_success(self, confluence_client, mock_auth):
        """Test successful search."""
        mock_response = {
            "results": [
                {
                    "content": {
                        "id": "123",
                        "type": "page",
                        "title": "Test Page",
                        "space": {"key": "TEST", "name": "Test Space"},
                    },
                    "excerpt": "This is a test excerpt",
                    "url": "/pages/viewpage.action?pageId=123",
                }
            ],
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            results = await confluence_client.search(query="test")

            assert len(results) == 1
            assert results[0].id == "123"
            assert results[0].title == "Test Page"


class TestConfluenceSearchResult:
    """Test suite for ConfluenceSearchResult model."""

    def test_search_result_creation(self):
        """Test creating a search result."""
        result = ConfluenceSearchResult(
            id="123",
            title="Test Page",
            space_key="TEST",
            space_name="Test Space",
            excerpt="This is a test",
            url="https://confluence.walmart.com/pages/viewpage.action?pageId=123",
        )

        assert result.id == "123"
        assert result.title == "Test Page"
