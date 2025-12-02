"""Unit tests for Jira tools module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.jira_tools import (
    _format_issue,
    _format_issue_summary,
    _handle_jira_error,
    jira_add_comment,
    jira_create_issue,
    jira_get_comments,
    jira_get_issue,
    jira_search,
    jira_transition_issue,
    jira_update_issue,
)
from code_puppy.plugins.walmart_specific.jira_client import (
    JiraAPIError,
    JiraAuthError,
    JiraError,
    JiraNotFoundError,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_context():
    """Mock PydanticAI run context."""
    return MagicMock()


@pytest.fixture
def sample_issue():
    """Sample Jira issue data."""
    return {
        "key": "PROJ-123",
        "fields": {
            "summary": "Test issue",
            "status": {"name": "Open"},
            "issuetype": {"name": "Story"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "John Doe"},
            "reporter": {"displayName": "Jane Smith"},
            "created": "2025-01-01T12:00:00.000+0000",
            "updated": "2025-01-02T12:00:00.000+0000",
            "description": "Test description",
            "labels": ["backend", "urgent"],
            "project": {"key": "PROJ"},
        },
    }


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


class TestFormatIssue:
    """Test suite for _format_issue helper."""

    def test_format_issue_full(self, sample_issue):
        """Test formatting issue with all fields."""
        result = _format_issue(sample_issue)
        assert result["key"] == "PROJ-123"
        assert result["summary"] == "Test issue"
        assert result["status"] == "Open"
        assert result["type"] == "Story"
        assert result["priority"] == "Medium"
        assert result["assignee"] == "John Doe"
        assert result["reporter"] == "Jane Smith"
        assert result["labels"] == ["backend", "urgent"]
        assert result["project"] == "PROJ"

    def test_format_issue_minimal(self):
        """Test formatting issue with minimal fields."""
        issue = {"key": "PROJ-1", "fields": {}}
        result = _format_issue(issue)
        assert result["key"] == "PROJ-1"
        assert result["summary"] is None
        assert result["assignee"] is None

    def test_format_issue_null_assignee(self):
        """Test formatting issue with null assignee."""
        issue = {
            "key": "PROJ-1",
            "fields": {"assignee": None, "reporter": None},
        }
        result = _format_issue(issue)
        assert result["assignee"] is None
        assert result["reporter"] is None


class TestFormatIssueSummary:
    """Test suite for _format_issue_summary helper."""

    def test_format_issue_summary(self, sample_issue):
        """Test formatting issue summary (minimal fields)."""
        result = _format_issue_summary(sample_issue)
        assert result["key"] == "PROJ-123"
        assert result["summary"] == "Test issue"
        assert result["status"] == "Open"
        assert result["type"] == "Story"
        assert result["assignee"] == "John Doe"
        # Should not include extra fields
        assert "description" not in result
        assert "labels" not in result


class TestHandleJiraError:
    """Test suite for _handle_jira_error helper."""

    def test_handle_auth_error(self):
        """Test handling JiraAuthError."""
        error = JiraAuthError("Auth failed")
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "authentication"
        assert "suggestion" in result

    def test_handle_not_found_error(self):
        """Test handling JiraNotFoundError."""
        error = JiraNotFoundError("Issue not found")
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "not_found"

    def test_handle_api_error(self):
        """Test handling JiraAPIError."""
        error = JiraAPIError("API error", status_code=500)
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "api_error"

    def test_handle_generic_jira_error(self):
        """Test handling generic JiraError."""
        error = JiraError("Generic error")
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "jira"

    def test_handle_unknown_error(self):
        """Test handling unknown exception."""
        error = ValueError("Unknown error")
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "unknown"


# =============================================================================
# JIRA SEARCH TESTS
# =============================================================================


class TestJiraSearch:
    """Test suite for jira_search tool."""

    def test_search_success(self, mock_context, sample_issue):
        """Test successful search."""
        mock_client = MagicMock()
        mock_client.search_issues.return_value = {
            "issues": [sample_issue],
            "total": 1,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_search(mock_context, "project = PROJ")

        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["issues"]) == 1
        assert result["issues"][0]["key"] == "PROJ-123"

    def test_search_caps_max_results(self, mock_context):
        """Test that max_results is capped at 50."""
        mock_client = MagicMock()
        mock_client.search_issues.return_value = {"issues": [], "total": 0}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            jira_search(mock_context, "project = PROJ", max_results=100)

        # Verify max_results was capped
        call_kwargs = mock_client.search_issues.call_args[1]
        assert call_kwargs["max_results"] == 50

    def test_search_error(self, mock_context):
        """Test search with error."""
        with patch(
            "code_puppy.tools.jira_tools.JiraClient",
            side_effect=JiraAuthError("Auth failed"),
        ):
            result = jira_search(mock_context, "project = PROJ")

        assert result["success"] is False
        assert result["error_type"] == "authentication"


# =============================================================================
# JIRA GET ISSUE TESTS
# =============================================================================


class TestJiraGetIssue:
    """Test suite for jira_get_issue tool."""

    def test_get_issue_success(self, mock_context, sample_issue):
        """Test successful get issue."""
        mock_client = MagicMock()
        mock_client.get_issue.return_value = sample_issue
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_issue(mock_context, "PROJ-123")

        assert result["success"] is True
        assert result["issue"]["key"] == "PROJ-123"
        assert result["issue"]["summary"] == "Test issue"

    def test_get_issue_not_found(self, mock_context):
        """Test get issue not found."""
        with patch(
            "code_puppy.tools.jira_tools.JiraClient",
            side_effect=JiraNotFoundError("Not found"),
        ):
            result = jira_get_issue(mock_context, "PROJ-999")

        assert result["success"] is False
        assert result["error_type"] == "not_found"


# =============================================================================
# JIRA CREATE ISSUE TESTS
# =============================================================================


class TestJiraCreateIssue:
    """Test suite for jira_create_issue tool."""

    def test_create_issue_success(self, mock_context):
        """Test successful issue creation."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {
            "id": "12345",
            "key": "PROJ-456",
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="New feature",
                description="Details here",
            )

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-456"
        assert result["summary"] == "New feature"

    def test_create_issue_without_description(self, mock_context):
        """Test issue creation without description."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"key": "PROJ-789"}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Bug",
                summary="Bug report",
            )

        assert result["success"] is True
        mock_client.create_issue.assert_called_once_with(
            project_key="PROJ",
            issue_type="Bug",
            summary="Bug report",
            description=None,
        )


# =============================================================================
# JIRA ADD COMMENT TESTS
# =============================================================================


class TestJiraAddComment:
    """Test suite for jira_add_comment tool."""

    def test_add_comment_success(self, mock_context):
        """Test successful comment addition."""
        mock_client = MagicMock()
        mock_client.add_comment.return_value = {"id": "10001"}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_add_comment(mock_context, "PROJ-123", "This is my comment")

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-123"
        assert result["comment_id"] == "10001"


# =============================================================================
# JIRA UPDATE ISSUE TESTS
# =============================================================================


class TestJiraUpdateIssue:
    """Test suite for jira_update_issue tool."""

    def test_update_issue_success(self, mock_context):
        """Test successful issue update."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = {}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_update_issue(
                mock_context, "PROJ-123", summary="Updated title"
            )

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-123"
        assert "summary" in result["updated_fields"]

    def test_update_issue_no_fields(self, mock_context):
        """Test update with no fields provided."""
        result = jira_update_issue(mock_context, "PROJ-123")

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "No fields provided" in result["error"]

    def test_update_issue_multiple_fields(self, mock_context):
        """Test update with multiple fields."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = {}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_update_issue(
                mock_context,
                "PROJ-123",
                summary="New title",
                description="New desc",
                assignee="jdoe",
            )

        assert result["success"] is True
        assert set(result["updated_fields"]) == {"summary", "description", "assignee"}


# =============================================================================
# JIRA TRANSITION TESTS
# =============================================================================


class TestJiraTransitionIssue:
    """Test suite for jira_transition_issue tool."""

    def test_transition_success(self, mock_context):
        """Test successful transition."""
        mock_client = MagicMock()
        mock_client.get_transitions.return_value = {
            "transitions": [
                {"id": "11", "name": "In Progress"},
                {"id": "21", "name": "Done"},
            ]
        }
        mock_client.transition_issue.return_value = {}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_transition_issue(mock_context, "PROJ-123", "Done")

        assert result["success"] is True
        assert result["new_status"] == "Done"
        mock_client.transition_issue.assert_called_once_with(
            "PROJ-123", "21", comment=None
        )

    def test_transition_case_insensitive(self, mock_context):
        """Test transition is case-insensitive."""
        mock_client = MagicMock()
        mock_client.get_transitions.return_value = {
            "transitions": [{"id": "21", "name": "Done"}]
        }
        mock_client.transition_issue.return_value = {}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_transition_issue(mock_context, "PROJ-123", "done")

        assert result["success"] is True

    def test_transition_with_comment(self, mock_context):
        """Test transition with comment."""
        mock_client = MagicMock()
        mock_client.get_transitions.return_value = {
            "transitions": [{"id": "21", "name": "Done"}]
        }
        mock_client.transition_issue.return_value = {}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_transition_issue(
                mock_context, "PROJ-123", "Done", comment="Completed work"
            )

        assert result["success"] is True
        mock_client.transition_issue.assert_called_once_with(
            "PROJ-123", "21", comment="Completed work"
        )

    def test_transition_invalid_status(self, mock_context):
        """Test transition with invalid status."""
        mock_client = MagicMock()
        mock_client.get_transitions.return_value = {
            "transitions": [
                {"id": "11", "name": "In Progress"},
                {"id": "21", "name": "Done"},
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_transition_issue(mock_context, "PROJ-123", "Invalid")

        assert result["success"] is False
        assert result["error_type"] == "invalid_transition"
        assert "In Progress" in result["available_transitions"]
        assert "Done" in result["available_transitions"]


# =============================================================================
# JIRA GET COMMENTS TESTS
# =============================================================================


class TestJiraGetComments:
    """Test suite for jira_get_comments tool."""

    def test_get_comments_success(self, mock_context):
        """Test successful get comments."""
        mock_client = MagicMock()
        mock_client.get_comments.return_value = {
            "comments": [
                {
                    "id": "1",
                    "author": {"displayName": "John Doe"},
                    "body": "First comment",
                    "created": "2025-01-01T12:00:00.000+0000",
                },
                {
                    "id": "2",
                    "author": {"displayName": "Jane Smith"},
                    "body": "Second comment",
                    "created": "2025-01-02T12:00:00.000+0000",
                },
            ],
            "total": 2,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_comments(mock_context, "PROJ-123")

        assert result["success"] is True
        assert result["total"] == 2
        assert len(result["comments"]) == 2
        assert result["comments"][0]["author"] == "John Doe"
        assert result["comments"][1]["body"] == "Second comment"
