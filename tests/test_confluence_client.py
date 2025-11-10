"""Unit tests for ConfluenceClient."""

import pytest
from unittest.mock import patch
from code_puppy.plugins.walmart_specific.confluence_client import (
    ConfluenceClient,
    ConfluenceSearchResult,
)


@pytest.fixture
def mock_cookies():
    """Create mock Confluence session cookies."""
    return {"JSESSIONID": "mock-session-id", "cloud.session.token": "mock-token-12345"}


@pytest.fixture
def mock_session_file(tmp_path):
    """Create a temporary mock session file."""
    session_file = tmp_path / "confluence.json"
    session_data = {
        "cookies": {
            "JSESSIONID": "mock-session-id",
            "cloud.session.token": "mock-token-12345",
        },
        "base_url": "https://confluence.walmart.com",
        "timestamp": "2025-01-10T12:00:00",
    }
    session_file.write_text(__import__("json").dumps(session_data))
    return str(session_file)


@pytest.fixture
def confluence_client(mock_session_file):
    """Create a ConfluenceClient instance with mocked session."""
    return ConfluenceClient(session_file_path=mock_session_file)


class TestConfluenceClient:
    """Test suite for ConfluenceClient."""

    def test_init(self, mock_session_file):
        """Test ConfluenceClient initialization."""
        client = ConfluenceClient(session_file_path=mock_session_file)
        assert client.base_url == "https://confluence.walmart.com"
        assert client.session_file_path == mock_session_file

    def test_search_success(self, confluence_client):
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

        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            results = confluence_client.search_content(cql="type=page")

            assert len(results) == 1
            assert results[0]["id"] == "123"
            assert results[0]["title"] == "Test Page"


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
