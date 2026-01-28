"""Unit tests for MS Graph common utilities including truncation."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.common import (
    truncate_content,
    truncate_list_response,
    apply_response_limit,
    MAX_RESPONSE_CHARS,
    msgraph_api_request,
    msgraph_authenticate,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphAPIError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestTruncateContent:
    """Test suite for truncate_content utility."""

    def test_truncate_content_no_truncation_needed(self):
        """Test that short content is not truncated."""
        content = "This is a short message."
        result = truncate_content(content)

        assert result["content"] == content
        assert result["truncated"] is False
        assert result["char_offset"] == 0
        assert result["next_offset"] is None
        assert result["total_chars"] == len(content)

    def test_truncate_content_truncation_applied(self):
        """Test that long content is truncated at max_chars."""
        # Create content larger than the limit
        content = "A" * 15000
        result = truncate_content(content, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is True
        assert result["char_offset"] == 0
        assert result["next_offset"] == 10000
        assert result["total_chars"] == 15000
        assert "message" in result

    def test_truncate_content_with_offset(self):
        """Test truncation with character offset."""
        content = "A" * 15000
        result = truncate_content(content, char_offset=5000, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is False  # Remaining after offset is exactly 10000
        assert result["char_offset"] == 5000
        assert result["next_offset"] is None
        assert result["total_chars"] == 15000

    def test_truncate_content_offset_with_more_truncation(self):
        """Test that offset + remaining content still needs truncation."""
        content = "A" * 25000
        result = truncate_content(content, char_offset=5000, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is True
        assert result["char_offset"] == 5000
        assert result["next_offset"] == 15000
        assert result["total_chars"] == 25000

    def test_truncate_content_offset_exceeds_length(self):
        """Test that offset beyond content length returns empty."""
        content = "A" * 100
        result = truncate_content(content, char_offset=200)

        assert result["content"] == ""
        assert result["truncated"] is False
        assert result["char_offset"] == 200
        assert result["next_offset"] is None
        assert result["total_chars"] == 100
        assert "message" in result  # Should have a message about offset exceeding

    def test_truncate_content_custom_max_chars(self):
        """Test truncation with custom max_chars limit."""
        content = "A" * 500
        result = truncate_content(content, max_chars=100)

        assert len(result["content"]) == 100
        assert result["truncated"] is True
        assert result["next_offset"] == 100

    def test_truncate_content_empty_string(self):
        """Test truncation with empty content."""
        result = truncate_content("")

        assert result["content"] == ""
        assert result["truncated"] is False
        assert result["total_chars"] == 0


class TestTruncateListResponse:
    """Test suite for truncate_list_response utility."""

    def test_truncate_list_no_truncation_needed(self):
        """Test that small lists are not truncated."""
        items = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
        result = truncate_list_response(items)

        assert result["items"] == items
        assert result["truncated"] is False
        assert result["item_offset"] == 0
        assert result["next_offset"] is None
        assert result["items_returned"] == 2
        assert result["total_items"] == 2

    def test_truncate_list_truncation_applied(self):
        """Test that large lists are truncated to fit max_chars."""
        # Create items that exceed the limit
        items = [{"id": i, "data": "X" * 500} for i in range(50)]
        result = truncate_list_response(items, max_chars=5000)

        assert len(result["items"]) < 50
        assert result["truncated"] is True
        assert result["next_offset"] is not None
        assert result["items_returned"] < 50
        assert "message" in result

    def test_truncate_list_with_item_offset(self):
        """Test list truncation with item offset."""
        items = [{"id": i, "name": f"Item {i}"} for i in range(20)]
        result = truncate_list_response(items, char_offset=10)

        # Should skip first 10 items
        assert result["items"][0]["id"] == 10
        assert result["item_offset"] == 10
        assert result["items_returned"] == 10

    def test_truncate_list_offset_exceeds_length(self):
        """Test that offset beyond list length returns empty."""
        items = [{"id": i} for i in range(5)]
        result = truncate_list_response(items, char_offset=10)

        assert result["items"] == []
        assert result["truncated"] is False
        assert result["items_returned"] == 0
        assert result["total_items"] == 5

    def test_truncate_list_empty_list(self):
        """Test truncation with empty list."""
        result = truncate_list_response([])

        assert result["items"] == []
        assert result["truncated"] is False
        assert result["items_returned"] == 0
        assert result["total_items"] == 0

    def test_truncate_list_single_large_item(self):
        """Test truncation when single item exceeds limit."""
        # Single item that's too large
        items = [{"data": "X" * 20000}]
        result = truncate_list_response(items, max_chars=1000)

        # Should return empty since no items fit
        assert result["items"] == []
        assert result["truncated"] is True


class TestApplyResponseLimit:
    """Test suite for apply_response_limit utility."""

    def test_apply_response_limit_no_truncation(self):
        """Test that small responses pass through unchanged."""
        response = {"success": True, "data": "small data"}
        result = apply_response_limit(response)

        assert result == response
        assert "_truncation_warning" not in result

    def test_apply_response_limit_adds_warning(self):
        """Test that large responses get warning metadata."""
        response = {"success": True, "body": "X" * 20000}
        result = apply_response_limit(response, max_chars=5000)

        assert "_response_size" in result
        assert "_truncation_warning" in result

    def test_apply_response_limit_truncates_large_fields(self):
        """Test that known large fields are truncated."""
        response = {"success": True, "body": "X" * 20000}
        result = apply_response_limit(response, max_chars=5000)

        # Body field should be truncated
        assert len(result["body"]) < 20000
        assert result.get("_body_truncated") is True
        assert result.get("_body_original_length") == 20000


class TestMsgraphApiRequest:
    """Test suite for msgraph_api_request tool."""

    def test_msgraph_api_request_get(self, mock_context):
        """Test GET request."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"id": "123", "name": "Test"}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/profile"
            )

            assert result["success"] is True
            assert result["method"] == "GET"
            assert result["endpoint"] == "/me/profile"
            assert result["truncated"] is False

    def test_msgraph_api_request_post(self, mock_context):
        """Test POST request."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "new-123"}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context,
                method="POST",
                endpoint="/me/messages",
                body={"subject": "Test"},
            )

            assert result["success"] is True
            assert result["method"] == "POST"
            mock_client.post.assert_called_once()

    def test_msgraph_api_request_invalid_method(self, mock_context):
        """Test invalid HTTP method."""
        result = msgraph_api_request(
            mock_context, method="INVALID", endpoint="/me/profile"
        )

        assert result["success"] is False
        assert result["error_type"] == "invalid_method"

    def test_msgraph_api_request_empty_endpoint(self, mock_context):
        """Test empty endpoint."""
        result = msgraph_api_request(mock_context, method="GET", endpoint="")

        assert result["success"] is False
        assert result["error_type"] == "invalid_endpoint"

    def test_msgraph_api_request_large_response_truncation(self, mock_context):
        """Test that large responses are truncated."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Return a large response
            mock_client.get.return_value = {"data": "X" * 15000}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/large-data"
            )

            assert result["success"] is True
            assert result["truncated"] is True
            assert result["total_chars"] > MAX_RESPONSE_CHARS
            assert result["next_offset"] is not None

    def test_msgraph_api_request_with_char_offset(self, mock_context):
        """Test char_offset parameter for pagination."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"data": "X" * 15000}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context,
                method="GET",
                endpoint="/me/large-data",
                char_offset=10000,
            )

            assert result["success"] is True
            assert result["char_offset"] == 10000

    def test_msgraph_api_request_auth_error(self, mock_context):
        """Test authentication error handling."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/profile"
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMsgraphAuthenticate:
    """Test suite for msgraph_authenticate tool."""

    def test_msgraph_authenticate_success(self, mock_context):
        """Test successful authentication."""
        with patch(
            "code_puppy.tools.msgraph.common.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.return_value = "Authentication successful"

            result = msgraph_authenticate(mock_context)

            assert result["success"] is True
            assert "successful" in result["message"].lower()

    def test_msgraph_authenticate_failure(self, mock_context):
        """Test failed authentication."""
        with patch(
            "code_puppy.tools.msgraph.common.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.return_value = "Authentication failed"

            result = msgraph_authenticate(mock_context)

            assert result["success"] is False

    def test_msgraph_authenticate_exception(self, mock_context):
        """Test authentication exception handling."""
        with patch(
            "code_puppy.tools.msgraph.common.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.side_effect = Exception("Network error")

            result = msgraph_authenticate(mock_context)

            assert result["success"] is False
            assert "error" in result


class TestMaxResponseCharsConstant:
    """Test the MAX_RESPONSE_CHARS constant."""

    def test_max_response_chars_value(self):
        """Test that MAX_RESPONSE_CHARS is set to 10,000."""
        assert MAX_RESPONSE_CHARS == 10_000

    def test_max_response_chars_used_by_default(self):
        """Test that truncation uses MAX_RESPONSE_CHARS by default."""
        content = "A" * 15000
        result = truncate_content(content)

        assert len(result["content"]) == MAX_RESPONSE_CHARS
        assert result["next_offset"] == MAX_RESPONSE_CHARS
