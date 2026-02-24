"""Tests for DX Documentation tools.

These tests verify the DX documentation integration including
authentication, search, and content retrieval.
"""

import json
from unittest.mock import MagicMock

import pytest


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_context():
    """Mock PydanticAI run context."""
    return MagicMock()


# =============================================================================
# DX AUTH TESTS
# =============================================================================


class TestDXAuth:
    """Tests for dx_auth module."""

    def test_import_dx_auth(self):
        """Test that dx_auth module can be imported."""
        from code_puppy.plugins.dx_docs.auth import (
            DXAuthError,
            DXTokenNotFoundError,
            DXTokenExpiredError,
        )

        assert DXAuthError is not None
        assert DXTokenNotFoundError is not None
        assert DXTokenExpiredError is not None

    def test_get_dx_tokens_no_file(self, tmp_path, monkeypatch):
        """Test get_dx_tokens when token file doesn't exist."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        # Point to non-existent file
        monkeypatch.setattr(
            dx_auth, "MCP_CLI_TOKENS_FILE", tmp_path / "nonexistent.json"
        )

        tokens = dx_auth.get_dx_tokens()
        assert tokens is None

    def test_get_dx_tokens_valid_file(self, tmp_path, monkeypatch):
        """Test get_dx_tokens with a valid token file."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        # Create a valid token file
        token_file = tmp_path / "tokens.json"
        token_data = {
            "access_token": "test_token_123",
            "refresh_token": "refresh_456",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        token_file.write_text(json.dumps(token_data))

        monkeypatch.setattr(dx_auth, "MCP_CLI_TOKENS_FILE", token_file)

        tokens = dx_auth.get_dx_tokens()
        assert tokens is not None
        assert tokens["access_token"] == "test_token_123"

    def test_get_dx_access_token(self, tmp_path, monkeypatch):
        """Test get_dx_access_token extracts the token correctly."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        token_file = tmp_path / "tokens.json"
        token_data = {"access_token": "my_access_token"}
        token_file.write_text(json.dumps(token_data))

        monkeypatch.setattr(dx_auth, "MCP_CLI_TOKENS_FILE", token_file)

        token = dx_auth.get_dx_access_token()
        assert token == "my_access_token"

    def test_is_token_valid_no_token(self, tmp_path, monkeypatch):
        """Test is_token_valid returns False when no token."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        monkeypatch.setattr(
            dx_auth, "MCP_CLI_TOKENS_FILE", tmp_path / "nonexistent.json"
        )

        assert dx_auth.is_token_valid() is False

    def test_is_token_valid_with_valid_token(self, tmp_path, monkeypatch):
        """Test is_token_valid returns True for valid token."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        token_file = tmp_path / "tokens.json"
        token_data = {
            "access_token": "valid_token",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        token_file.write_text(json.dumps(token_data))

        monkeypatch.setattr(dx_auth, "MCP_CLI_TOKENS_FILE", token_file)

        assert dx_auth.is_token_valid() is True

    def test_get_token_status_no_token(self, tmp_path, monkeypatch):
        """Test get_token_status when no token exists."""
        from code_puppy.plugins.dx_docs import auth as dx_auth

        monkeypatch.setattr(
            dx_auth, "MCP_CLI_TOKENS_FILE", tmp_path / "nonexistent.json"
        )

        is_valid, message = dx_auth.get_token_status()
        assert is_valid is False
        assert "No token found" in message

    def test_ensure_authenticated_no_token(self, tmp_path, monkeypatch):
        """Test ensure_authenticated raises when no token."""
        from code_puppy.plugins.dx_docs import auth as dx_auth
        from code_puppy.plugins.dx_docs.auth import DXTokenNotFoundError

        monkeypatch.setattr(
            dx_auth, "MCP_CLI_TOKENS_FILE", tmp_path / "nonexistent.json"
        )

        with pytest.raises(DXTokenNotFoundError):
            dx_auth.ensure_authenticated()


# =============================================================================
# DX CLIENT TESTS
# =============================================================================


class TestDXClient:
    """Tests for dx_client module."""

    def test_import_dx_client(self):
        """Test that dx_client module can be imported."""
        from code_puppy.plugins.dx_docs.client import (
            DXClient,
            DXError,
        )

        assert DXClient is not None
        assert DXError is not None

    def test_dx_client_init(self):
        """Test DXClient initialization."""
        from code_puppy.plugins.dx_docs.client import DXClient

        client = DXClient()
        assert client.endpoint == "https://api.dx.walmart.com/mcp"
        assert client.timeout == 30

    def test_dx_client_custom_endpoint(self):
        """Test DXClient with custom endpoint."""
        from code_puppy.plugins.dx_docs.client import DXClient

        client = DXClient(endpoint="https://custom.endpoint/mcp", timeout=60)
        assert client.endpoint == "https://custom.endpoint/mcp"
        assert client.timeout == 60

    def test_parse_single_result(self):
        """Test parsing a single search result string."""
        from code_puppy.plugins.dx_docs.client import DXClient

        client = DXClient()
        result_str = "pageId: abc123, title: Test Page, highlighted: Some <b>text</b>, url= https://example.com/page"

        result = client._parse_single_result(result_str)

        assert result is not None
        assert result.page_id == "abc123"
        assert result.title == "Test Page"
        assert result.url == "https://example.com/page"

    def test_parse_single_result_invalid(self):
        """Test parsing an invalid result string."""
        from code_puppy.plugins.dx_docs.client import DXClient

        client = DXClient()

        # No pageId
        result = client._parse_single_result("title: No Page ID")
        assert result is None

        # Empty string
        result = client._parse_single_result("")
        assert result is None

        # None
        result = client._parse_single_result(None)
        assert result is None

    def test_dx_search_result_model(self):
        """Test DXSearchResult pydantic model."""
        from code_puppy.plugins.dx_docs.client import DXSearchResult

        result = DXSearchResult(
            page_id="test123",
            title="Test Title",
            url="https://example.com",
            highlighted="Some highlighted text",
        )

        assert result.page_id == "test123"
        assert result.title == "Test Title"
        assert result.url == "https://example.com"
        assert result.highlighted == "Some highlighted text"

    def test_dx_page_content_model(self):
        """Test DXPageContent pydantic model."""
        from code_puppy.plugins.dx_docs.client import DXPageContent

        page = DXPageContent(
            page_id="page123",
            title="Page Title",
            content="This is the page content.",
            url="https://example.com/page",
        )

        assert page.page_id == "page123"
        assert page.title == "Page Title"
        assert page.content == "This is the page content."


# =============================================================================
# DX TOOLS TESTS
# =============================================================================


class TestDXTools:
    """Tests for dx_tools module."""

    def test_import_dx_tools(self):
        """Test that dx_tools module can be imported."""
        from code_puppy.plugins.dx_docs.tools import (
            dx_search,
            dx_semantic_search,
            dx_get_page_content,
            dx_get_tags,
            dx_authenticate,
            DX_TOOLS,
        )

        assert dx_search is not None
        assert dx_semantic_search is not None
        assert dx_get_page_content is not None
        assert dx_get_tags is not None
        assert dx_authenticate is not None
        assert len(DX_TOOLS) == 5

    def test_dx_tools_in_registry(self):
        """Test that DX tools are registered in TOOL_REGISTRY after plugin load."""
        from code_puppy.tools import TOOL_REGISTRY
        from code_puppy.plugins.dx_docs.tools import DX_TOOLS

        # Simulate plugin loading by merging DX_TOOLS into TOOL_REGISTRY
        TOOL_REGISTRY.update(DX_TOOLS)

        assert "dx_search" in TOOL_REGISTRY
        assert "dx_get_page_content" in TOOL_REGISTRY
        assert "dx_get_tags" in TOOL_REGISTRY
        assert "dx_authenticate" in TOOL_REGISTRY

    def test_handle_dx_error_token_not_found(self):
        """Test error handling for token not found."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.auth import DXTokenNotFoundError

        error = DXTokenNotFoundError()
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "not_authenticated"
        assert "action" in result

    def test_handle_dx_error_token_expired(self):
        """Test error handling for expired token."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.auth import DXTokenExpiredError

        error = DXTokenExpiredError()
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "token_expired"

    def test_handle_dx_error_not_found(self):
        """Test error handling for not found."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.client import DXNotFoundError

        error = DXNotFoundError("Page not found")
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "not_found"

    def test_handle_dx_error_api_error(self):
        """Test error handling for API errors."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.client import DXAPIError

        error = DXAPIError("API failed", status_code=500)
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert result["status_code"] == 500

    def test_format_search_result(self):
        """Test formatting a search result."""
        from code_puppy.plugins.dx_docs.tools import _format_search_result
        from code_puppy.plugins.dx_docs.client import DXSearchResult

        search_result = DXSearchResult(
            page_id="test123",
            title="Test Title",
            url="https://example.com",
            highlighted="Highlighted text",
        )

        formatted = _format_search_result(search_result)

        assert formatted["page_id"] == "test123"
        assert formatted["title"] == "Test Title"
        assert formatted["url"] == "https://example.com"
        assert formatted["excerpt"] == "Highlighted text"


# =============================================================================
# DX CONTENT SEARCH CLIENT TESTS
# =============================================================================


class TestDXContentSearchClient:
    """Tests for dx_content_search_client module."""

    def test_import_dx_content_search_client(self):
        """Test that dx_content_search_client module can be imported."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
            ContentSearchError,
            ContentSearchAPIError,
            VALID_PRODUCTS,
        )

        assert DXContentSearchClient is not None
        assert ContentSearchError is not None
        assert ContentSearchAPIError is not None
        assert VALID_PRODUCTS is not None

    def test_dx_content_search_client_init(self):
        """Test DXContentSearchClient initialization."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
            CONTENT_SEARCH_ENDPOINT,
        )

        client = DXContentSearchClient()
        assert client.endpoint == CONTENT_SEARCH_ENDPOINT
        assert client.timeout == 60  # Default timeout

    def test_dx_content_search_client_custom_endpoint(self):
        """Test DXContentSearchClient with custom endpoint."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
        )

        client = DXContentSearchClient(
            endpoint="https://custom.endpoint/sse",
            timeout=120,
        )
        assert client.endpoint == "https://custom.endpoint/sse"
        assert client.timeout == 120

    def test_content_search_result_model(self):
        """Test ContentSearchResult pydantic model."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchResult,
        )

        result = ContentSearchResult(
            title="Test Title",
            content="This is some test content about Kafka.",
            url="https://dx.walmart.com/test",
            source="dx-docs",
            score=0.95,
            product="kafka",
        )

        assert result.title == "Test Title"
        assert result.content == "This is some test content about Kafka."
        assert result.url == "https://dx.walmart.com/test"
        assert result.source == "dx-docs"
        assert result.score == 0.95
        assert result.product == "kafka"

    def test_content_search_result_minimal(self):
        """Test ContentSearchResult with minimal fields."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchResult,
        )

        result = ContentSearchResult(
            title="Minimal Result",
            content="Just the basics.",
        )

        assert result.title == "Minimal Result"
        assert result.content == "Just the basics."
        assert result.url is None
        assert result.source is None
        assert result.score is None
        assert result.product is None

    def test_valid_products_frozenset(self):
        """Test VALID_PRODUCTS contains expected values."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            VALID_PRODUCTS,
        )

        assert "kafka" in VALID_PRODUCTS
        assert "wcnp" in VALID_PRODUCTS
        assert "looper" in VALID_PRODUCTS
        assert "concord" in VALID_PRODUCTS
        assert "azure" in VALID_PRODUCTS
        assert "elementai" in VALID_PRODUCTS
        assert "element" in VALID_PRODUCTS  # Alias

    def test_parse_single_result_valid(self):
        """Test parsing a valid result dict."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
        )

        client = DXContentSearchClient()
        data = {
            "title": "Kafka Consumer Guide",
            "content": "How to configure Kafka consumers.",
            "url": "https://dx.walmart.com/kafka/consumers",
            "source": "dx-docs",
            "score": 0.87,
        }

        result = client._parse_single_result(data)

        assert result is not None
        assert result.title == "Kafka Consumer Guide"
        assert result.content == "How to configure Kafka consumers."
        assert result.url == "https://dx.walmart.com/kafka/consumers"
        assert result.source == "dx-docs"
        assert result.score == 0.87

    def test_parse_single_result_with_alternative_field_names(self):
        """Test parsing result with alternative field names."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
        )

        client = DXContentSearchClient()
        data = {
            "name": "Alt Title",  # Alternative to title
            "snippet": "Alt content snippet.",  # Alternative to content
            "link": "https://example.com",  # Alternative to url
        }

        result = client._parse_single_result(data)

        assert result is not None
        assert result.title == "Alt Title"
        assert result.content == "Alt content snippet."
        assert result.url == "https://example.com"

    def test_parse_single_result_invalid(self):
        """Test parsing invalid result data."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            DXContentSearchClient,
        )

        client = DXContentSearchClient()

        # Non-dict returns None
        assert client._parse_single_result("string") is None
        assert client._parse_single_result([1, 2, 3]) is None
        assert client._parse_single_result(None) is None

        # Empty dict returns None (no title or content)
        assert client._parse_single_result({}) is None

    def test_search_tech_content_product_in_query(self, monkeypatch):
        """Test that product filter is correctly included in the search query."""
        from code_puppy.plugins.dx_docs import (
            content_search_client as dx_content_search_client,
        )

        captured_args = {}

        def mock_call_tool(self, tool_name, arguments):
            captured_args["tool"] = tool_name
            captured_args["args"] = arguments
            return {"_collected_text": []}

        monkeypatch.setattr(
            dx_content_search_client.DXContentSearchClient,
            "_call_tool",
            mock_call_tool,
        )
        monkeypatch.setattr(
            dx_content_search_client,
            "ensure_authenticated",
            lambda: "mock-token",
        )

        client = dx_content_search_client.DXContentSearchClient()
        client.search_tech_content("test query", product="kafka")

        # Verify product is embedded in query
        assert captured_args["args"]["query"] == "[kafka] test query"

    def test_search_tech_content_empty_query_raises(self):
        """Test that empty query raises an error."""
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchAPIError,
            DXContentSearchClient,
        )

        client = DXContentSearchClient()

        with pytest.raises(ContentSearchAPIError, match="Query cannot be empty"):
            client.search_tech_content("")

        with pytest.raises(ContentSearchAPIError, match="Query cannot be empty"):
            client.search_tech_content("   ")


class TestDXSemanticSearchTool:
    """Tests for dx_semantic_search tool function."""

    def test_import_dx_semantic_search(self):
        """Test that dx_semantic_search can be imported."""
        from code_puppy.plugins.dx_docs.tools import (
            dx_semantic_search,
            DX_TOOLS,
            DX_TOOL_FUNCTIONS,
        )

        assert dx_semantic_search is not None
        assert "dx_semantic_search" in DX_TOOLS
        assert dx_semantic_search in DX_TOOL_FUNCTIONS

    def test_dx_semantic_search_in_registry(self):
        """Test that dx_semantic_search is in TOOL_REGISTRY after plugin load."""
        from code_puppy.tools import TOOL_REGISTRY
        from code_puppy.plugins.dx_docs.tools import DX_TOOLS

        TOOL_REGISTRY.update(DX_TOOLS)

        assert "dx_semantic_search" in TOOL_REGISTRY

    def test_format_semantic_search_result(self):
        """Test formatting a semantic search result."""
        from code_puppy.plugins.dx_docs.tools import _format_semantic_search_result
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchResult,
        )

        result = ContentSearchResult(
            title="Test Title",
            content="Test content here.",
            url="https://dx.walmart.com/test",
            source="stackoverflow",
            score=0.92,
            product="kafka",
        )

        formatted = _format_semantic_search_result(result)

        assert formatted["title"] == "Test Title"
        assert formatted["content"] == "Test content here."
        assert formatted["url"] == "https://dx.walmart.com/test"
        assert formatted["source"] == "stackoverflow"
        assert formatted["score"] == 0.92
        assert formatted["product"] == "kafka"

    def test_format_semantic_search_result_minimal(self):
        """Test formatting a minimal semantic search result."""
        from code_puppy.plugins.dx_docs.tools import _format_semantic_search_result
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchResult,
        )

        result = ContentSearchResult(
            title="Minimal",
            content="Just content.",
        )

        formatted = _format_semantic_search_result(result)

        assert formatted["title"] == "Minimal"
        assert formatted["content"] == "Just content."
        assert "url" not in formatted
        assert "source" not in formatted
        assert "score" not in formatted
        assert "product" not in formatted

    def test_handle_dx_error_content_search_api_error(self):
        """Test error handling for content search API errors."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchAPIError,
        )

        error = ContentSearchAPIError("Request failed", status_code=500)
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "content_search_api_error"
        assert result["status_code"] == 500

    def test_handle_dx_error_content_search_error(self):
        """Test error handling for generic content search errors."""
        from code_puppy.plugins.dx_docs.tools import _handle_dx_error
        from code_puppy.plugins.dx_docs.content_search_client import (
            ContentSearchError,
        )

        error = ContentSearchError("Something went wrong")
        result = _handle_dx_error(error)

        assert result["success"] is False
        assert result["error_type"] == "content_search_error"


# =============================================================================
# INTEGRATION TESTS (require authentication)
# =============================================================================


@pytest.mark.integration
class TestDXIntegration:
    """Integration tests that require actual DX authentication.

    These tests are skipped by default. Run with:
        pytest -m integration tests/test_dx_tools.py
    """

    def test_dx_search_real(self):
        """Test real DX search."""
        from code_puppy.plugins.dx_docs.client import DXClient
        from code_puppy.plugins.dx_docs.auth import is_token_valid

        if not is_token_valid():
            pytest.skip("No valid DX token available")

        client = DXClient()
        results = client.search("WCNP")

        assert len(results) > 0
        assert results[0].page_id is not None
        assert results[0].title is not None

    def test_dx_get_page_content_real(self):
        """Test real DX page content retrieval."""
        from code_puppy.plugins.dx_docs.client import DXClient
        from code_puppy.plugins.dx_docs.auth import is_token_valid

        if not is_token_valid():
            pytest.skip("No valid DX token available")

        client = DXClient()
        # First search for a page
        results = client.search("WCNP")
        if not results:
            pytest.skip("No search results found")

        # Then get the content
        page = client.get_page_content(results[0].page_id)

        assert page.page_id == results[0].page_id
        assert len(page.content) > 0


# =============================================================================
# AUTO-RETRY DECORATOR TESTS
# =============================================================================


class TestAutoAuthRetry:
    """Tests for the _with_auto_auth_retry decorator."""

    def test_auto_retry_on_token_not_found(self, mock_context, monkeypatch):
        """Test that auto-retry triggers auth when token is not found."""
        from unittest.mock import MagicMock, patch
        from code_puppy.plugins.dx_docs import tools as dx_tools
        from code_puppy.plugins.dx_docs.auth import DXTokenNotFoundError

        # Track call count
        call_count = 0

        def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises auth error
                raise DXTokenNotFoundError("No token")
            # Second call succeeds
            return []

        # Mock the client and auth
        mock_client = MagicMock()
        mock_client.search = mock_search

        with patch.object(dx_tools, "get_dx_client", return_value=mock_client):
            with patch.object(
                dx_tools,
                "ensure_mcp_cli_and_authenticate",
                return_value=(True, "Success"),
            ) as mock_auth:
                result = dx_tools.dx_search(mock_context, "test query")

        # Auth should have been called
        mock_auth.assert_called_once_with(auto_install=True)
        # Function should have been called twice (initial + retry)
        assert call_count == 2
        # Result should be successful
        assert result["success"] is True

    def test_auto_retry_on_token_expired(self, mock_context, monkeypatch):
        """Test that auto-retry triggers auth when token is expired."""
        from unittest.mock import MagicMock, patch
        from code_puppy.plugins.dx_docs import tools as dx_tools
        from code_puppy.plugins.dx_docs.auth import DXTokenExpiredError

        call_count = 0

        def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DXTokenExpiredError("Token expired")
            return []

        mock_client = MagicMock()
        mock_client.search = mock_search

        with patch.object(dx_tools, "get_dx_client", return_value=mock_client):
            with patch.object(
                dx_tools,
                "ensure_mcp_cli_and_authenticate",
                return_value=(True, "Success"),
            ) as mock_auth:
                result = dx_tools.dx_search(mock_context, "test query")

        mock_auth.assert_called_once()
        assert call_count == 2
        assert result["success"] is True

    def test_auto_retry_auth_failure(self, mock_context, monkeypatch):
        """Test that auth failure returns proper error."""
        from unittest.mock import MagicMock, patch
        from code_puppy.plugins.dx_docs import tools as dx_tools
        from code_puppy.plugins.dx_docs.auth import DXTokenNotFoundError

        def mock_search(*args, **kwargs):
            raise DXTokenNotFoundError("No token")

        mock_client = MagicMock()
        mock_client.search = mock_search

        with patch.object(dx_tools, "get_dx_client", return_value=mock_client):
            with patch.object(
                dx_tools,
                "ensure_mcp_cli_and_authenticate",
                return_value=(False, "Auth failed"),
            ):
                result = dx_tools.dx_search(mock_context, "test query")

        assert result["success"] is False
        assert result["error_type"] == "authentication_failed"
        assert "Auth failed" in result["error"]

    def test_no_retry_on_other_errors(self, mock_context, monkeypatch):
        """Test that non-auth errors don't trigger retry."""
        from unittest.mock import MagicMock, patch
        from code_puppy.plugins.dx_docs import tools as dx_tools
        from code_puppy.plugins.dx_docs.client import DXAPIError

        call_count = 0

        def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise DXAPIError("Server error", status_code=500)

        mock_client = MagicMock()
        mock_client.search = mock_search

        with patch.object(dx_tools, "get_dx_client", return_value=mock_client):
            with patch.object(
                dx_tools,
                "ensure_mcp_cli_and_authenticate",
                return_value=(True, "Success"),
            ) as mock_auth:
                result = dx_tools.dx_search(mock_context, "test query")

        # Auth should NOT have been called
        mock_auth.assert_not_called()
        # Function should have been called only once
        assert call_count == 1
        # Result should be error
        assert result["success"] is False
        assert result["error_type"] == "api_error"
