"""Unit tests for Jira client module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from code_puppy.plugins.walmart_specific.jira_client import (
    JiraAPIError,
    JiraAuthError,
    JiraClient,
    JiraError,
    JiraNotFoundError,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def valid_session_data() -> dict:
    """Valid session data for testing."""
    return {
        "cookies": {"JSESSIONID": "test-session"},
        "all_cookies": {"JSESSIONID": "test-session", "other": "cookie"},
        "base_url": "https://jira.walmart.com",
        "timestamp": "2025-01-01T12:00:00",
    }


@pytest.fixture
def session_file(tmp_path: Path, valid_session_data: dict) -> Path:
    """Create a valid session file."""
    file_path = tmp_path / "jira.json"
    file_path.write_text(json.dumps(valid_session_data))
    return file_path


@pytest.fixture
def mock_rate_limiter():
    """Mock the rate limiter."""
    with patch(
        "code_puppy.plugins.walmart_specific.jira_client.SharedRateLimiter"
    ) as mock:
        instance = Mock()
        instance.wait_if_needed = Mock()
        instance.record_request = Mock()
        mock.return_value = instance
        yield instance


# =============================================================================
# EXCEPTION TESTS
# =============================================================================


class TestJiraExceptions:
    """Test suite for Jira exception classes."""

    def test_jira_error_base(self):
        """Test JiraError base exception."""
        error = JiraError("Test error")
        assert str(error) == "Test error"

    def test_jira_auth_error_default_message(self):
        """Test JiraAuthError with default message."""
        error = JiraAuthError()
        assert "Authentication failed" in str(error)

    def test_jira_auth_error_custom_message(self):
        """Test JiraAuthError with custom message."""
        error = JiraAuthError("Custom auth error")
        assert str(error) == "Custom auth error"

    def test_jira_not_found_error_default_message(self):
        """Test JiraNotFoundError with default message."""
        error = JiraNotFoundError()
        assert "not found" in str(error)

    def test_jira_api_error_with_status_code(self):
        """Test JiraAPIError stores status code."""
        error = JiraAPIError("API error", status_code=500)
        assert str(error) == "API error"
        assert error.status_code == 500

    def test_jira_api_error_without_status_code(self):
        """Test JiraAPIError without status code."""
        error = JiraAPIError("API error")
        assert error.status_code is None


# =============================================================================
# CLIENT INITIALIZATION TESTS
# =============================================================================


class TestJiraClientInit:
    """Test suite for JiraClient initialization."""

    def test_init_with_valid_session(self, session_file: Path, mock_rate_limiter):
        """Test successful initialization with valid session."""
        client = JiraClient(session_file_path=str(session_file))
        assert client.base_url == "https://jira.walmart.com"
        assert "JSESSIONID" in client.cookies
        client.close()

    def test_init_missing_session_file(self, tmp_path: Path):
        """Test initialization fails when session file is missing."""
        missing_file = tmp_path / "nonexistent.json"
        with pytest.raises(JiraError, match="Session file not found"):
            JiraClient(session_file_path=str(missing_file))

    def test_init_invalid_json(self, tmp_path: Path):
        """Test initialization fails with invalid JSON."""
        bad_file = tmp_path / "jira.json"
        bad_file.write_text("not valid json")
        with pytest.raises(JiraError, match="Invalid JSON"):
            JiraClient(session_file_path=str(bad_file))

    def test_init_missing_cookies_field(self, tmp_path: Path):
        """Test initialization fails when cookies field is missing."""
        file_path = tmp_path / "jira.json"
        file_path.write_text(json.dumps({"base_url": "https://jira.walmart.com"}))
        with pytest.raises(JiraError, match="missing 'cookies' field"):
            JiraClient(session_file_path=str(file_path))

    def test_init_invalid_cookies_type(self, tmp_path: Path):
        """Test initialization fails when cookies is not a dict."""
        file_path = tmp_path / "jira.json"
        file_path.write_text(json.dumps({"cookies": "not a dict"}))
        with pytest.raises(JiraError, match="Invalid 'cookies' field"):
            JiraClient(session_file_path=str(file_path))

    def test_init_uses_all_cookies_over_cookies(
        self, tmp_path: Path, mock_rate_limiter
    ):
        """Test that all_cookies is preferred over cookies."""
        file_path = tmp_path / "jira.json"
        data = {
            "cookies": {"old": "cookie"},
            "all_cookies": {"new": "cookie"},
            "timestamp": "2025-01-01T12:00:00",
        }
        file_path.write_text(json.dumps(data))
        client = JiraClient(session_file_path=str(file_path))
        assert "new" in client.cookies
        assert "old" not in client.cookies
        client.close()

    def test_init_default_base_url(self, tmp_path: Path, mock_rate_limiter):
        """Test default base URL when not in session."""
        file_path = tmp_path / "jira.json"
        data = {"cookies": {"JSESSIONID": "test"}, "timestamp": "2025-01-01T12:00:00"}
        file_path.write_text(json.dumps(data))
        client = JiraClient(session_file_path=str(file_path))
        assert client.base_url == "https://jira.walmart.com"
        client.close()

    def test_init_os_error(self, tmp_path: Path):
        """Test initialization handles OS errors."""
        file_path = tmp_path / "jira.json"
        file_path.write_text(json.dumps({"cookies": {"test": "value"}}))

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            with pytest.raises(JiraError, match="Failed to load session file"):
                JiraClient(session_file_path=str(file_path))


# =============================================================================
# STALENESS TESTS
# =============================================================================


class TestJiraClientStaleness:
    """Test suite for session staleness checks."""

    def test_staleness_warning_no_timestamp(self, tmp_path: Path, mock_rate_limiter):
        """Test warning when timestamp is missing."""
        file_path = tmp_path / "jira.json"
        file_path.write_text(json.dumps({"cookies": {"test": "value"}}))

        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.emit_warning"
        ) as mock_warn:
            client = JiraClient(session_file_path=str(file_path))
            mock_warn.assert_called_once()
            assert "no timestamp" in mock_warn.call_args[0][0]
            client.close()

    def test_staleness_warning_old_session(self, tmp_path: Path, mock_rate_limiter):
        """Test warning when session is stale."""
        file_path = tmp_path / "jira.json"
        data = {
            "cookies": {"test": "value"},
            "timestamp": "2020-01-01T12:00:00",  # Very old
        }
        file_path.write_text(json.dumps(data))

        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.emit_warning"
        ) as mock_warn:
            client = JiraClient(session_file_path=str(file_path))
            mock_warn.assert_called_once()
            assert "hours old" in mock_warn.call_args[0][0]
            client.close()

    def test_staleness_warning_invalid_timestamp(
        self, tmp_path: Path, mock_rate_limiter
    ):
        """Test warning when timestamp format is invalid."""
        file_path = tmp_path / "jira.json"
        data = {
            "cookies": {"test": "value"},
            "timestamp": "not-a-valid-timestamp",
        }
        file_path.write_text(json.dumps(data))

        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.emit_warning"
        ) as mock_warn:
            client = JiraClient(session_file_path=str(file_path))
            mock_warn.assert_called_once()
            assert "Invalid timestamp" in mock_warn.call_args[0][0]
            client.close()

    def test_no_staleness_warning_fresh_session(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test no warning for fresh session."""
        # Update session file with current timestamp
        from datetime import datetime

        data = json.loads(session_file.read_text())
        data["timestamp"] = datetime.now().isoformat()
        session_file.write_text(json.dumps(data))

        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.emit_warning"
        ) as mock_warn:
            client = JiraClient(session_file_path=str(session_file))
            mock_warn.assert_not_called()
            client.close()


# =============================================================================
# USER AGENT TESTS
# =============================================================================


class TestJiraClientUserAgent:
    """Test suite for User-Agent building."""

    def test_user_agent_basic(self, session_file: Path, mock_rate_limiter):
        """Test basic User-Agent without token."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.get_puppy_token",
            return_value=None,
        ):
            client = JiraClient(session_file_path=str(session_file))
            assert "Code Puppy Walmart Internal" in client.client.headers["User-Agent"]
            client.close()

    def test_user_agent_with_user_id(self, session_file: Path, mock_rate_limiter):
        """Test User-Agent includes user_id from token."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.get_puppy_token",
            return_value="fake-token",
        ):
            with patch(
                "code_puppy.plugins.walmart_specific.jira_client.decode_jwt_without_validation",
                return_value={"sub": "testuser"},
            ):
                client = JiraClient(session_file_path=str(session_file))
                assert "testuser" in client.client.headers["User-Agent"]
                client.close()

    def test_user_agent_token_error_silent(self, session_file: Path, mock_rate_limiter):
        """Test User-Agent building handles token errors silently."""
        with patch(
            "code_puppy.plugins.walmart_specific.jira_client.get_puppy_token",
            side_effect=Exception("Token error"),
        ):
            client = JiraClient(session_file_path=str(session_file))
            assert "Code Puppy" in client.client.headers["User-Agent"]
            client.close()


# =============================================================================
# HTTP REQUEST TESTS
# =============================================================================


class TestJiraClientMakeRequest:
    """Test suite for _make_request method."""

    def test_make_request_success(self, session_file: Path, mock_rate_limiter):
        """Test successful request."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "PROJ-123"}
        mock_response.text = '{"key": "PROJ-123"}'

        with patch.object(client.client, "request", return_value=mock_response):
            result = client._make_request("GET", "/rest/api/2/issue/PROJ-123")
            assert result["key"] == "PROJ-123"
            mock_rate_limiter.record_request.assert_called_once()

        client.close()

    def test_make_request_401_auth_error(self, session_file: Path, mock_rate_limiter):
        """Test 401 raises JiraAuthError."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraAuthError, match="Authentication failed"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_403_auth_error(self, session_file: Path, mock_rate_limiter):
        """Test 403 raises JiraAuthError."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 403

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraAuthError, match="Authentication failed"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_404_not_found(self, session_file: Path, mock_rate_limiter):
        """Test 404 raises JiraNotFoundError."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 404

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraNotFoundError, match="not found"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-999")

        client.close()

    def test_make_request_500_api_error_with_message(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test 500 error with JSON error message."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"errorMessages": ["Server error"]}

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraAPIError, match="Server error"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_500_api_error_with_message_field(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test 500 error with 'message' field."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal error"}

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraAPIError, match="Internal error"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_500_api_error_text_fallback(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test 500 error falls back to response text."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("Not JSON")
        mock_response.text = "Raw error text"

        with patch.object(client.client, "request", return_value=mock_response):
            with pytest.raises(JiraAPIError, match="Raw error text"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_http_error(self, session_file: Path, mock_rate_limiter):
        """Test HTTP connection error."""
        client = JiraClient(session_file_path=str(session_file))

        with patch.object(
            client.client, "request", side_effect=httpx.HTTPError("Connection failed")
        ):
            with pytest.raises(JiraAPIError, match="HTTP request failed"):
                client._make_request("GET", "/rest/api/2/issue/PROJ-123")

        client.close()

    def test_make_request_204_no_content(self, session_file: Path, mock_rate_limiter):
        """Test 204 No Content returns empty dict."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(client.client, "request", return_value=mock_response):
            result = client._make_request("PUT", "/rest/api/2/issue/PROJ-123")
            assert result == {}

        client.close()

    def test_make_request_empty_response(self, session_file: Path, mock_rate_limiter):
        """Test empty response body returns empty dict."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = ""

        with patch.object(client.client, "request", return_value=mock_response):
            result = client._make_request("PUT", "/rest/api/2/issue/PROJ-123")
            assert result == {}

        client.close()


# =============================================================================
# GET ISSUE TESTS
# =============================================================================


class TestJiraClientGetIssue:
    """Test suite for get_issue method."""

    def test_get_issue_basic(self, session_file: Path, mock_rate_limiter):
        """Test basic issue retrieval."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {
            "key": "PROJ-123",
            "fields": {"summary": "Test issue"},
        }

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.get_issue("PROJ-123")
            assert result["key"] == "PROJ-123"
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert "PROJ-123" in call_args[0][1]

        client.close()

    def test_get_issue_with_fields(self, session_file: Path, mock_rate_limiter):
        """Test issue retrieval with specific fields."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {"key": "PROJ-123"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.get_issue("PROJ-123", fields=["summary", "status"])
            call_kwargs = mock_req.call_args[1]
            assert "summary,status" in str(call_kwargs.get("params", {}))

        client.close()

    def test_get_issue_with_expand(self, session_file: Path, mock_rate_limiter):
        """Test issue retrieval with expand parameter."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {"key": "PROJ-123"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.get_issue("PROJ-123", expand="changelog")
            call_kwargs = mock_req.call_args[1]
            assert "changelog" in str(call_kwargs.get("params", {}))

        client.close()


# =============================================================================
# SEARCH ISSUES TESTS
# =============================================================================


class TestJiraClientSearchIssues:
    """Test suite for search_issues method."""

    def test_search_issues_basic(self, session_file: Path, mock_rate_limiter):
        """Test basic JQL search."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"issues": []}'
        mock_response.json.return_value = {
            "issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}],
            "total": 2,
        }

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.search_issues("project = PROJ")
            assert len(result["issues"]) == 2
            # Verify POST method used
            assert mock_req.call_args[0][0] == "POST"

        client.close()

    def test_search_issues_with_pagination(self, session_file: Path, mock_rate_limiter):
        """Test search with pagination parameters."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"issues": []}'
        mock_response.json.return_value = {"issues": [], "total": 100}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.search_issues("project = PROJ", max_results=10, start_at=50)
            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["maxResults"] == 10
            assert payload["startAt"] == 50

        client.close()

    def test_search_issues_with_fields(self, session_file: Path, mock_rate_limiter):
        """Test search with specific fields."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"issues": []}'
        mock_response.json.return_value = {"issues": []}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.search_issues("project = PROJ", fields=["summary", "status"])
            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"] == ["summary", "status"]

        client.close()


# =============================================================================
# CREATE ISSUE TESTS
# =============================================================================


class TestJiraClientCreateIssue:
    """Test suite for create_issue method."""

    def test_create_issue_basic(self, session_file: Path, mock_rate_limiter):
        """Test basic issue creation."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {"id": "12345", "key": "PROJ-123"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.create_issue(
                project_key="PROJ",
                issue_type="Story",
                summary="Test issue",
            )
            assert result["key"] == "PROJ-123"

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"]["project"]["key"] == "PROJ"
            assert payload["fields"]["issuetype"]["name"] == "Story"
            assert payload["fields"]["summary"] == "Test issue"

        client.close()

    def test_create_issue_with_description(self, session_file: Path, mock_rate_limiter):
        """Test issue creation with description."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {"key": "PROJ-123"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.create_issue(
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                description="Detailed description",
            )
            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"]["description"] == "Detailed description"

        client.close()

    def test_create_issue_with_extra_fields(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test issue creation with extra fields."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.text = '{"key": "PROJ-123"}'
        mock_response.json.return_value = {"key": "PROJ-123"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.create_issue(
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                labels=["backend", "urgent"],
                priority={"name": "High"},
            )
            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"]["labels"] == ["backend", "urgent"]
            assert payload["fields"]["priority"] == {"name": "High"}

        client.close()


# =============================================================================
# UPDATE ISSUE TESTS
# =============================================================================


class TestJiraClientUpdateIssue:
    """Test suite for update_issue method."""

    def test_update_issue_fields(self, session_file: Path, mock_rate_limiter):
        """Test updating issue fields."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.update_issue(
                "PROJ-123", fields={"summary": "Updated title"}
            )
            assert result == {}

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"]["summary"] == "Updated title"

        client.close()

    def test_update_issue_with_update_operations(
        self, session_file: Path, mock_rate_limiter
    ):
        """Test updating issue with update operations."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.update_issue("PROJ-123", update={"labels": [{"add": "urgent"}]})
            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["update"]["labels"] == [{"add": "urgent"}]

        client.close()


# =============================================================================
# COMMENT TESTS
# =============================================================================


class TestJiraClientComments:
    """Test suite for comment methods."""

    def test_add_comment(self, session_file: Path, mock_rate_limiter):
        """Test adding a comment."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.text = '{"id": "10001"}'
        mock_response.json.return_value = {"id": "10001", "body": "Test comment"}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.add_comment("PROJ-123", "Test comment")
            assert result["id"] == "10001"

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["body"] == "Test comment"

        client.close()

    def test_get_comments(self, session_file: Path, mock_rate_limiter):
        """Test getting comments."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"comments": []}'
        mock_response.json.return_value = {
            "comments": [{"id": "1", "body": "Comment 1"}],
            "total": 1,
        }

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.get_comments("PROJ-123")
            assert len(result["comments"]) == 1

            call_kwargs = mock_req.call_args[1]
            params = call_kwargs.get("params", {})
            assert params["maxResults"] == 50
            assert params["startAt"] == 0

        client.close()

    def test_get_comments_with_pagination(self, session_file: Path, mock_rate_limiter):
        """Test getting comments with pagination."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"comments": []}'
        mock_response.json.return_value = {"comments": []}

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.get_comments("PROJ-123", max_results=10, start_at=20)
            call_kwargs = mock_req.call_args[1]
            params = call_kwargs.get("params", {})
            assert params["maxResults"] == 10
            assert params["startAt"] == 20

        client.close()


# =============================================================================
# TRANSITION TESTS
# =============================================================================


class TestJiraClientTransitions:
    """Test suite for transition methods."""

    def test_get_transitions(self, session_file: Path, mock_rate_limiter):
        """Test getting available transitions."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"transitions": []}'
        mock_response.json.return_value = {
            "transitions": [
                {"id": "11", "name": "In Progress"},
                {"id": "21", "name": "Done"},
            ]
        }

        with patch.object(client.client, "request", return_value=mock_response):
            result = client.get_transitions("PROJ-123")
            assert len(result["transitions"]) == 2

        client.close()

    def test_transition_issue_basic(self, session_file: Path, mock_rate_limiter):
        """Test basic issue transition."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            result = client.transition_issue("PROJ-123", "21")
            assert result == {}

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["transition"]["id"] == "21"

        client.close()

    def test_transition_issue_with_comment(self, session_file: Path, mock_rate_limiter):
        """Test transition with comment."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.transition_issue("PROJ-123", "21", comment="Moving to done")

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["update"]["comment"][0]["add"]["body"] == "Moving to done"

        client.close()

    def test_transition_issue_with_fields(self, session_file: Path, mock_rate_limiter):
        """Test transition with fields."""
        client = JiraClient(session_file_path=str(session_file))

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch.object(
            client.client, "request", return_value=mock_response
        ) as mock_req:
            client.transition_issue(
                "PROJ-123", "21", fields={"resolution": {"name": "Done"}}
            )

            call_kwargs = mock_req.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["fields"]["resolution"]["name"] == "Done"

        client.close()


# =============================================================================
# CONTEXT MANAGER TESTS
# =============================================================================


class TestJiraClientContextManager:
    """Test suite for context manager and cleanup."""

    def test_context_manager(self, session_file: Path, mock_rate_limiter):
        """Test using client as context manager."""
        with JiraClient(session_file_path=str(session_file)) as client:
            assert client is not None
            assert isinstance(client, JiraClient)

    def test_context_manager_closes_client(self, session_file: Path, mock_rate_limiter):
        """Test context manager closes HTTP client."""
        with JiraClient(session_file_path=str(session_file)) as client:
            mock_close = Mock()
            client.client.close = mock_close

        mock_close.assert_called_once()

    def test_close_method(self, session_file: Path, mock_rate_limiter):
        """Test explicit close method."""
        client = JiraClient(session_file_path=str(session_file))
        mock_close = Mock()
        client.client.close = mock_close

        client.close()

        mock_close.assert_called_once()
