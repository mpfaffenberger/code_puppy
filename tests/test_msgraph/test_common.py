"""Unit tests for MS Graph common module.

Tests error handling and the generic API request tool.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from code_puppy.tools.msgraph.common import (
    _handle_msgraph_error,
    get_msgraph_client,
    msgraph_api_request,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphError,
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphAPIError,
    MSGraphThrottledError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestHandleMsgraphError:
    """Tests for _handle_msgraph_error function."""

    def test_handle_auth_error(self):
        """Test handling MSGraphAuthError."""
        error = MSGraphAuthError("Token expired")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "authentication"
        assert "Authentication failed" in result["error"]
        assert "Token expired" in result["error"]

    def test_handle_not_found_error(self):
        """Test handling MSGraphNotFoundError."""
        error = MSGraphNotFoundError("User not found")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "not_found"
        assert "Resource not found" in result["error"]
        assert "User not found" in result["error"]

    def test_handle_throttled_error_with_retry(self):
        """Test handling MSGraphThrottledError with retry_after."""
        error = MSGraphThrottledError("Too many requests", retry_after=30)
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "throttled"
        assert "Rate limited" in result["error"]
        assert "retry after 30s" in result["error"]
        assert result["retry_after"] == 30

    def test_handle_throttled_error_without_retry(self):
        """Test handling MSGraphThrottledError without retry_after."""
        error = MSGraphThrottledError("Too many requests")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "throttled"
        assert result["retry_after"] is None

    def test_handle_api_error(self):
        """Test handling MSGraphAPIError."""
        error = MSGraphAPIError("Bad request", status_code=400, error_code="BadRequest")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "API error" in result["error"]
        assert result["status_code"] == 400
        assert result["error_code"] == "BadRequest"

    def test_handle_api_error_without_details(self):
        """Test handling MSGraphAPIError without status/code."""
        error = MSGraphAPIError("Something went wrong")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert result["status_code"] is None
        assert result["error_code"] is None

    def test_handle_generic_msgraph_error(self):
        """Test handling generic MSGraphError."""
        error = MSGraphError("Generic MS Graph error")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "msgraph"
        assert "Microsoft Graph error" in result["error"]

    def test_handle_unknown_error(self):
        """Test handling unknown exception types."""
        error = ValueError("Something unexpected")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "unknown"
        assert "Unexpected error" in result["error"]

    def test_handle_runtime_error(self):
        """Test handling RuntimeError."""
        error = RuntimeError("Runtime problem")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "unknown"
        assert "Runtime problem" in result["error"]


class TestMsgraphApiRequest:
    """Tests for msgraph_api_request generic tool."""

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_get_request(self, mock_client_fn, mock_context):
        """Test making a GET request."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"displayName": "John Doe"}

        result = msgraph_api_request(
            mock_context,
            method="GET",
            endpoint="/me",
        )

        assert result["success"] is True
        assert result["method"] == "GET"
        assert result["endpoint"] == "/me"
        assert result["response"]["displayName"] == "John Doe"
        mock_client.get.assert_called_once_with("/me", params=None)

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_get_request_with_params(self, mock_client_fn, mock_context):
        """Test making a GET request with query parameters."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": []}

        result = msgraph_api_request(
            mock_context,
            method="GET",
            endpoint="/me/messages",
            params={"$top": 10, "$select": "subject"},
        )

        assert result["success"] is True
        mock_client.get.assert_called_once_with(
            "/me/messages", params={"$top": 10, "$select": "subject"}
        )

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_post_request(self, mock_client_fn, mock_context):
        """Test making a POST request."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {"id": "new-event-123"}

        result = msgraph_api_request(
            mock_context,
            method="POST",
            endpoint="/me/events",
            body={"subject": "New Meeting"},
        )

        assert result["success"] is True
        assert result["method"] == "POST"
        mock_client.post.assert_called_once_with(
            "/me/events", body={"subject": "New Meeting"}, params=None
        )

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_patch_request(self, mock_client_fn, mock_context):
        """Test making a PATCH request."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.patch.return_value = {}

        result = msgraph_api_request(
            mock_context,
            method="PATCH",
            endpoint="/me/events/123",
            body={"subject": "Updated Meeting"},
        )

        assert result["success"] is True
        assert result["method"] == "PATCH"
        mock_client.patch.assert_called_once()

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_delete_request(self, mock_client_fn, mock_context):
        """Test making a DELETE request."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.delete.return_value = {}

        result = msgraph_api_request(
            mock_context,
            method="DELETE",
            endpoint="/me/events/123",
        )

        assert result["success"] is True
        assert result["method"] == "DELETE"
        mock_client.delete.assert_called_once_with("/me/events/123", params=None)

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_put_request(self, mock_client_fn, mock_context):
        """Test making a PUT request."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.put.return_value = {"updated": True}

        result = msgraph_api_request(
            mock_context,
            method="PUT",
            endpoint="/me/drive/items/123/content",
            body={"content": "file data"},
        )

        assert result["success"] is True
        assert result["method"] == "PUT"
        mock_client.put.assert_called_once()

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_lowercase_method_normalized(self, mock_client_fn, mock_context):
        """Test that lowercase method is normalized to uppercase."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {}

        result = msgraph_api_request(
            mock_context,
            method="get",
            endpoint="/me",
        )

        assert result["success"] is True
        assert result["method"] == "GET"

    def test_invalid_method(self, mock_context):
        """Test error on invalid HTTP method."""
        result = msgraph_api_request(
            mock_context,
            method="INVALID",
            endpoint="/me",
        )

        assert result["success"] is False
        assert result["error_type"] == "invalid_method"
        assert "Invalid HTTP method" in result["error"]

    def test_empty_endpoint(self, mock_context):
        """Test error on empty endpoint."""
        result = msgraph_api_request(
            mock_context,
            method="GET",
            endpoint="",
        )

        assert result["success"] is False
        assert result["error_type"] == "invalid_endpoint"
        assert "Endpoint cannot be empty" in result["error"]

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_auth_error_propagated(self, mock_client_fn, mock_context):
        """Test that auth errors are properly handled."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.side_effect = MSGraphAuthError("Token expired")

        result = msgraph_api_request(
            mock_context,
            method="GET",
            endpoint="/me",
        )

        assert result["success"] is False
        assert result["error_type"] == "authentication"

    @patch("code_puppy.tools.msgraph.common.get_msgraph_client")
    def test_not_found_error_propagated(self, mock_client_fn, mock_context):
        """Test that not found errors are properly handled."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.side_effect = MSGraphNotFoundError("Resource not found")

        result = msgraph_api_request(
            mock_context,
            method="GET",
            endpoint="/users/nonexistent",
        )

        assert result["success"] is False
        assert result["error_type"] == "not_found"


class TestGetMsgraphClient:
    """Tests for get_msgraph_client helper."""

    @patch("code_puppy.tools.msgraph.common.MSGraphClient")
    def test_returns_client_instance(self, mock_client_class):
        """Test that get_msgraph_client returns a client instance."""
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance

        result = get_msgraph_client()

        assert result == mock_instance
        mock_client_class.assert_called_once()

    @patch("code_puppy.tools.msgraph.common.MSGraphClient")
    def test_propagates_auth_error(self, mock_client_class):
        """Test that auth errors from client creation are propagated."""
        mock_client_class.side_effect = MSGraphAuthError("No tokens")

        with pytest.raises(MSGraphAuthError):
            get_msgraph_client()
