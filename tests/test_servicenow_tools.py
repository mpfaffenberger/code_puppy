"""Tests for ServiceNow Knowledge Base tools."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.walmart_specific.servicenow_client import (
    ServiceNowAuthError,
    ServiceNowClient,
    ServiceNowError,
    ServiceNowNotFoundError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session_file(tmp_path):
    """Create a mock session file for testing."""
    session_data = {
        "cookies": {
            "glide_session_store": "test_session_value",
            "JSESSIONID": "test_jsessionid",
        },
        "all_cookies": {
            "glide_session_store": "test_session_value",
            "JSESSIONID": "test_jsessionid",
        },
        "url": "https://walmartglobal.service-now.com/",
        "timestamp": "2025-01-15T10:00:00",
    }
    session_file = tmp_path / "servicenow.json"
    session_file.write_text(json.dumps(session_data))
    return session_file


@pytest.fixture
def mock_kb_search_response():
    """Mock response for KB article search."""
    return {
        "result": [
            {
                "sys_id": "abc123",
                "number": "KB0012345",
                "short_description": "How to reset your password",
                "text": "<p>Follow these steps to reset your password...</p>",
                "category": "IT Support",
                "kb_knowledge_base": "IT Knowledge Base",
                "workflow_state": "published",
                "sys_updated_on": "2025-01-10 12:00:00",
            },
            {
                "sys_id": "def456",
                "number": "KB0012346",
                "short_description": "Password policy guidelines",
                "text": "<p>Password must be at least 12 characters...</p>",
                "category": "Security",
                "kb_knowledge_base": "Security Knowledge Base",
                "workflow_state": "published",
                "sys_updated_on": "2025-01-09 10:00:00",
            },
        ]
    }


@pytest.fixture
def mock_kb_article_response():
    """Mock response for single KB article."""
    return {
        "result": {
            "sys_id": "abc123",
            "number": "KB0012345",
            "short_description": "How to reset your password",
            "text": "<h2>Password Reset Guide</h2><p>Follow these steps to reset your password:</p><ol><li>Go to the login page</li><li>Click 'Forgot Password'</li><li>Enter your email</li><li>Check your inbox</li></ol>",
            "category": "IT Support",
            "kb_knowledge_base": "IT Knowledge Base",
            "workflow_state": "published",
        }
    }


# =============================================================================
# ServiceNow Client Tests
# =============================================================================


class TestServiceNowClient:
    """Tests for ServiceNowClient class."""

    def test_client_init_missing_session_file(self, tmp_path):
        """Test that client raises error when session file is missing."""
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(tmp_path / "nonexistent.json"))
        assert "Session file not found" in str(exc_info.value)

    def test_client_init_invalid_json(self, tmp_path):
        """Test that client raises error for invalid JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(bad_file))
        assert "Invalid JSON" in str(exc_info.value)

    def test_client_init_missing_cookies(self, tmp_path):
        """Test that client raises error when cookies field is missing."""
        no_cookies_file = tmp_path / "no_cookies.json"
        no_cookies_file.write_text(json.dumps({"url": "https://example.com"}))
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(no_cookies_file))
        assert "missing 'cookies' field" in str(exc_info.value)

    def test_client_init_success(self, mock_session_file):
        """Test successful client initialization."""
        with patch.object(ServiceNowClient, "_check_staleness"):
            client = ServiceNowClient(session_file_path=str(mock_session_file))
            assert client.base_url == "https://walmartglobal.service-now.com"
            assert "glide_session_store" in client.cookies
            client.close()


# =============================================================================
# ServiceNow Tools Tests
# =============================================================================


class TestServiceNowKBSearch:
    """Tests for servicenow_kb_search tool."""

    def test_search_success(self, mock_session_file, mock_kb_search_response):
        """Test successful KB article search."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_articles.return_value = mock_kb_search_response
            MockClient.return_value = mock_client

            result = servicenow_kb_search(mock_ctx, "password reset", limit=10)

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["results"]) == 2
            assert result["results"][0]["number"] == "KB0012345"
            assert result["results"][0]["title"] == "How to reset your password"

    def test_search_auth_error(self, mock_session_file):
        """Test search handling of authentication error."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_articles.side_effect = ServiceNowAuthError(
                "Authentication failed"
            )
            MockClient.return_value = mock_client

            result = servicenow_kb_search(mock_ctx, "password")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestServiceNowKBReadArticle:
    """Tests for servicenow_kb_read_article tool."""

    def test_read_article_by_number(self, mock_session_file, mock_kb_article_response):
        """Test reading article by KB number."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        # Wrap the result in a list since get_kb_article_by_number returns list
        mock_response = {"result": [mock_kb_article_response["result"]]}

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_number.return_value = mock_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "KB0012345")

            assert result["success"] is True
            assert result["number"] == "KB0012345"
            assert result["title"] == "How to reset your password"
            assert "Password Reset Guide" in result["content"]

    def test_read_article_by_sys_id(self, mock_session_file, mock_kb_article_response):
        """Test reading article by sys_id."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_id.return_value = mock_kb_article_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "abc123")

            assert result["success"] is True
            assert result["article_id"] == "abc123"

    def test_read_article_not_found(self, mock_session_file):
        """Test handling of article not found."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_number.return_value = {"result": []}
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "KB9999999")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_read_article_with_character_limit(self, mock_session_file):
        """Test reading article with character limit."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()
        long_content = "<p>" + "A" * 50000 + "</p>"
        mock_response = {
            "result": {
                "sys_id": "abc123",
                "number": "KB0012345",
                "short_description": "Long article",
                "text": long_content,
                "category": "Test",
                "workflow_state": "published",
            }
        }

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_id.return_value = mock_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(
                mock_ctx, "abc123", character_limit=1000
            )

            assert result["success"] is True
            assert result["content_truncated"] is True
            assert len(result["content"]) <= 1000
            assert result["remaining_content_length"] > 0


class TestServiceNowKBSearchByCategory:
    """Tests for servicenow_kb_search_by_category tool."""

    def test_search_by_category_success(self, mock_session_file, mock_kb_search_response):
        """Test successful category search."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search_by_category

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_by_category.return_value = mock_kb_search_response
            MockClient.return_value = mock_client

            result = servicenow_kb_search_by_category(
                mock_ctx, category="IT Support", query="password"
            )

            assert result["success"] is True
            assert result["category"] == "IT Support"
            assert result["query"] == "password"
            assert len(result["results"]) == 2


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_convert_html_to_markdown(self):
        """Test HTML to markdown conversion."""
        from code_puppy.tools.servicenow_tools import _convert_html_to_markdown

        html = "<h2>Title</h2><p>Paragraph text</p><ul><li>Item 1</li><li>Item 2</li></ul>"
        markdown = _convert_html_to_markdown(html)

        assert "## Title" in markdown
        assert "Paragraph text" in markdown
        assert "Item 1" in markdown

    def test_convert_empty_html(self):
        """Test conversion of empty HTML."""
        from code_puppy.tools.servicenow_tools import _convert_html_to_markdown

        assert _convert_html_to_markdown("") == ""
        assert _convert_html_to_markdown(None) == ""

    def test_format_search_result(self):
        """Test search result formatting."""
        from code_puppy.tools.servicenow_tools import _format_search_result

        raw_result = {
            "sys_id": "abc123",
            "number": "KB0012345",
            "short_description": "Test Article",
            "text": "Some article text content here",
            "kb_category": {"display_value": "Test Category", "link": "..."},
            "kb_knowledge_base": {"display_value": "Test KB", "link": "..."},
            "workflow_state": "published",
        }

        formatted = _format_search_result(raw_result)

        assert formatted["sys_id"] == "abc123"
        assert formatted["number"] == "KB0012345"
        assert formatted["title"] == "Test Article"
        assert "KB0012345" in formatted["url"]
        assert formatted["category"] == "Test Category"
        assert formatted["knowledge_base"] == "Test KB"
    
    def test_format_search_result_string_category(self):
        """Test search result formatting with string category (backwards compat)."""
        from code_puppy.tools.servicenow_tools import _format_search_result

        raw_result = {
            "sys_id": "abc123",
            "number": "KB0012345",
            "short_description": "Test Article",
            "text": "Some article text content here",
            "kb_category": "Simple Category",
            "kb_knowledge_base": "Simple KB",
            "workflow_state": "published",
        }

        formatted = _format_search_result(raw_result)

        assert formatted["category"] == "Simple Category"
        assert formatted["knowledge_base"] == "Simple KB"
