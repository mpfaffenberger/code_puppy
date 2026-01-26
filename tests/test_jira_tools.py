"""Unit tests for Jira tools module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.jira_tools import (
    MAX_CHARACTER_LIMIT,
    _format_issue,
    _format_issue_summary,
    _handle_jira_error,
    _parse_application_service_input,
    _resolve_application_service_id,
    _truncate_content,
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


class TestTruncateContent:
    """Test suite for _truncate_content helper."""

    def test_truncate_empty_content(self):
        """Test truncating empty content."""
        result = _truncate_content("")
        assert result["content"] == ""
        assert result["total_content_length"] == 0
        assert result["content_truncated"] is False
        assert result["remaining_content_length"] == 0
        assert result["character_limit"] == MAX_CHARACTER_LIMIT

    def test_truncate_small_content_no_limit(self):
        """Test small content with no limit (uses MAX_CHARACTER_LIMIT)."""
        content = "Hello, World!"
        result = _truncate_content(content)
        assert result["content"] == content
        assert result["total_content_length"] == 13
        assert result["content_truncated"] is False
        assert result["remaining_content_length"] == 0

    def test_truncate_with_custom_limit(self):
        """Test truncation with custom character limit."""
        content = "Hello, World!"
        result = _truncate_content(content, character_limit=5)
        assert result["content"] == "Hello"
        assert result["total_content_length"] == 13
        assert result["content_truncated"] is True
        assert result["remaining_content_length"] == 8
        assert result["character_limit"] == 5

    def test_truncate_with_offset(self):
        """Test truncation with character offset."""
        content = "Hello, World!"
        result = _truncate_content(content, character_limit=5, character_offset=7)
        assert result["content"] == "World"
        assert result["total_content_length"] == 13
        assert result["content_truncated"] is True
        assert result["remaining_content_length"] == 1  # "!" remains
        assert result["character_offset"] == 7

    def test_truncate_clamps_to_max(self):
        """Test that character_limit is clamped to MAX_CHARACTER_LIMIT."""
        content = "A" * 100
        result = _truncate_content(content, character_limit=MAX_CHARACTER_LIMIT + 1000)
        assert result["character_limit"] == MAX_CHARACTER_LIMIT

    def test_truncate_negative_offset_becomes_zero(self):
        """Test that negative offset is treated as 0."""
        content = "Hello, World!"
        result = _truncate_content(content, character_offset=-5)
        assert result["character_offset"] == 0
        assert result["content"].startswith("Hello")

    def test_truncate_zero_limit_uses_max(self):
        """Test that limit=0 uses MAX_CHARACTER_LIMIT."""
        content = "Hello"
        result = _truncate_content(content, character_limit=0)
        assert result["character_limit"] == MAX_CHARACTER_LIMIT


class TestHandleJiraError:
    """Test suite for _handle_jira_error helper."""

    def test_handle_auth_error(self):
        """Test handling JiraAuthError."""
        error = JiraAuthError("Auth failed")
        result = _handle_jira_error(error)
        assert result["success"] is False
        assert result["error_type"] == "authentication"


# =============================================================================
# APPLICATION/SERVICE FIELD TESTS
# =============================================================================


class TestParseApplicationServiceInput:
    """Test suite for _parse_application_service_input helper."""

    def test_parse_list_format_valid(self):
        """Test parsing valid list format."""
        result = _parse_application_service_input(
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"]
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_list_format_invalid_length(self):
        """Test parsing list with wrong number of elements."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["Level1", "Level2"])

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["L1", "L2", "L3", "L4"])

    def test_parse_string_arrow_delimiter(self):
        """Test parsing string with ' -> ' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_dot_delimiter(self):
        """Test parsing string with '.' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech.AP - Invoices and Payments.Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_slash_delimiter(self):
        """Test parsing string with '/' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech/AP - Invoices and Payments/Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_pipe_delimiter(self):
        """Test parsing string with '|' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech|AP - Invoices and Payments|Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_greater_than_delimiter(self):
        """Test parsing string with '>' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech>AP - Invoices and Payments>Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_with_whitespace(self):
        """Test parsing string with extra whitespace."""
        result = _parse_application_service_input(
            "  EBS Finance Tech  ->  AP - Invoices and Payments  ->  Pay from Scan  "
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_wrong_delimiter_count(self):
        """Test parsing string with wrong number of delimiters."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input("Level1 -> Level2")

    def test_parse_string_no_delimiter(self):
        """Test parsing string without supported delimiter."""
        with pytest.raises(ValueError, match="separated by"):
            _parse_application_service_input("Level1 Level2 Level3")

    def test_parse_invalid_type(self):
        """Test parsing with invalid type."""
        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input(12345)

        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input({"key": "value"})


class TestResolveApplicationServiceId:
    """Test suite for _resolve_application_service_id helper."""

    def test_resolve_id_success(self):
        """Test successful ID resolution."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
                {
                    "id": "2125771",
                    "values": ["Other", "Service", "Name"],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
        )

        assert result == "2125770"

    def test_resolve_id_with_issue_context(self):
        """Test ID resolution with issue context."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
            issue_id="28750593",
        )

        assert result == "2125770"
        # Verify the payload included fieldContext
        call_args = mock_client._make_request.call_args
        assert call_args[1]["json"]["fieldContext"] == {"issueKeyOrId": "28750593"}

    def test_resolve_id_not_found(self):
        """Test ID resolution when path is not found."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {"id": "2125771", "values": ["Other", "Service", "Name"]},
            ]
        }

        with pytest.raises(ValueError, match="path not found"):
            _resolve_application_service_id(
                mock_client, ["Nonexistent", "Path", "Here"]
            )

    def test_resolve_id_invalid_path_length(self):
        """Test ID resolution with invalid path length."""
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _resolve_application_service_id(mock_client, ["Level1", "Level2"])

    def test_resolve_id_api_error(self):
        """Test ID resolution when API call fails."""
        mock_client = MagicMock()
        mock_client._make_request.side_effect = JiraAPIError("API Error")

        with pytest.raises(ValueError, match="Failed to fetch"):
            _resolve_application_service_id(
                mock_client, ["Level1", "Level2", "Level3"]
            )


class TestFormatIssueWithApplicationService:
    """Test suite for _format_issue with application_service field."""

    def test_format_issue_with_resolved_app_service(self):
        """Test formatting issue with resolved application service (3 elements)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": [
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert (
            result["application_service"]
            == "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )

    def test_format_issue_with_app_service_id_only(self):
        """Test formatting issue with just the ID (1 element)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": ["2125770"],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] == "2125770"

    def test_format_issue_without_app_service(self):
        """Test formatting issue without application service field."""
        issue = {
            "key": "PROJ-123",
            "fields": {},
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None

    def test_format_issue_with_none_app_service(self):
        """Test formatting issue with None application service."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": None,
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None


class TestJiraCreateIssueWithApplicationService:
    """Test suite for jira_create_issue with application_service."""

    def test_create_issue_with_app_service_list(self, mock_context):
        """Test creating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify that create_issue was called with the resolved ID
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_with_app_service_string(self, mock_context):
        """Test creating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_app_service_no_template_issue(self, mock_context):
        """Test creating issue when no template issue is found."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {"issues": []}  # No template
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Should still work, just without issue context in nFeed call
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_story_without_app_service_fails(self, mock_context):
        """Test that creating a Story without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Story",
            summary="Test Story",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Story" in result["error"]

    def test_create_bug_without_app_service_fails(self, mock_context):
        """Test that creating a Bug without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Bug",
            summary="Test Bug",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Bug" in result["error"]

    def test_create_task_without_app_service_succeeds(self, mock_context):
        """Test that creating a Task without application_service succeeds."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Task",
                summary="Test Task",
                # No application_service provided - this is OK for Tasks
            )

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-456"
        # Verify create_issue was called without application_service field
        create_call = mock_client.create_issue.call_args
        # Should not have the application_service custom field
        assert "customfield_20400" not in create_call[1]


class TestJiraUpdateIssueWithApplicationService:
    """Test suite for jira_update_issue with application_service."""

    def test_update_issue_with_app_service_list(self, mock_context):
        """Test updating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify update was called with resolved ID
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]

    def test_update_issue_with_app_service_string(self, mock_context):
        """Test updating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]
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
# APPLICATION/SERVICE FIELD TESTS
# =============================================================================


class TestParseApplicationServiceInput:
    """Test suite for _parse_application_service_input helper."""

    def test_parse_list_format_valid(self):
        """Test parsing valid list format."""
        result = _parse_application_service_input(
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"]
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_list_format_invalid_length(self):
        """Test parsing list with wrong number of elements."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["Level1", "Level2"])

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["L1", "L2", "L3", "L4"])

    def test_parse_string_arrow_delimiter(self):
        """Test parsing string with ' -> ' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_dot_delimiter(self):
        """Test parsing string with '.' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech.AP - Invoices and Payments.Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_slash_delimiter(self):
        """Test parsing string with '/' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech/AP - Invoices and Payments/Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_pipe_delimiter(self):
        """Test parsing string with '|' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech|AP - Invoices and Payments|Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_greater_than_delimiter(self):
        """Test parsing string with '>' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech>AP - Invoices and Payments>Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_with_whitespace(self):
        """Test parsing string with extra whitespace."""
        result = _parse_application_service_input(
            "  EBS Finance Tech  ->  AP - Invoices and Payments  ->  Pay from Scan  "
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_wrong_delimiter_count(self):
        """Test parsing string with wrong number of delimiters."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input("Level1 -> Level2")

    def test_parse_string_no_delimiter(self):
        """Test parsing string without supported delimiter."""
        with pytest.raises(ValueError, match="separated by"):
            _parse_application_service_input("Level1 Level2 Level3")

    def test_parse_invalid_type(self):
        """Test parsing with invalid type."""
        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input(12345)

        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input({"key": "value"})


class TestResolveApplicationServiceId:
    """Test suite for _resolve_application_service_id helper."""

    def test_resolve_id_success(self):
        """Test successful ID resolution."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
                {
                    "id": "2125771",
                    "values": ["Other", "Service", "Name"],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
        )

        assert result == "2125770"

    def test_resolve_id_with_issue_context(self):
        """Test ID resolution with issue context."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
            issue_id="28750593",
        )

        assert result == "2125770"
        # Verify the payload included fieldContext
        call_args = mock_client._make_request.call_args
        assert call_args[1]["json"]["fieldContext"] == {"issueKeyOrId": "28750593"}

    def test_resolve_id_not_found(self):
        """Test ID resolution when path is not found."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {"id": "2125771", "values": ["Other", "Service", "Name"]},
            ]
        }

        with pytest.raises(ValueError, match="path not found"):
            _resolve_application_service_id(
                mock_client, ["Nonexistent", "Path", "Here"]
            )

    def test_resolve_id_invalid_path_length(self):
        """Test ID resolution with invalid path length."""
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _resolve_application_service_id(mock_client, ["Level1", "Level2"])

    def test_resolve_id_api_error(self):
        """Test ID resolution when API call fails."""
        mock_client = MagicMock()
        mock_client._make_request.side_effect = JiraAPIError("API Error")

        with pytest.raises(ValueError, match="Failed to fetch"):
            _resolve_application_service_id(
                mock_client, ["Level1", "Level2", "Level3"]
            )


class TestFormatIssueWithApplicationService:
    """Test suite for _format_issue with application_service field."""

    def test_format_issue_with_resolved_app_service(self):
        """Test formatting issue with resolved application service (3 elements)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": [
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert (
            result["application_service"]
            == "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )

    def test_format_issue_with_app_service_id_only(self):
        """Test formatting issue with just the ID (1 element)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": ["2125770"],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] == "2125770"

    def test_format_issue_without_app_service(self):
        """Test formatting issue without application service field."""
        issue = {
            "key": "PROJ-123",
            "fields": {},
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None

    def test_format_issue_with_none_app_service(self):
        """Test formatting issue with None application service."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": None,
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None


class TestJiraCreateIssueWithApplicationService:
    """Test suite for jira_create_issue with application_service."""

    def test_create_issue_with_app_service_list(self, mock_context):
        """Test creating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify that create_issue was called with the resolved ID
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_with_app_service_string(self, mock_context):
        """Test creating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_app_service_no_template_issue(self, mock_context):
        """Test creating issue when no template issue is found."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {"issues": []}  # No template
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Should still work, just without issue context in nFeed call
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_story_without_app_service_fails(self, mock_context):
        """Test that creating a Story without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Story",
            summary="Test Story",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Story" in result["error"]

    def test_create_bug_without_app_service_fails(self, mock_context):
        """Test that creating a Bug without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Bug",
            summary="Test Bug",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Bug" in result["error"]

    def test_create_task_without_app_service_succeeds(self, mock_context):
        """Test that creating a Task without application_service succeeds."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Task",
                summary="Test Task",
                # No application_service provided - this is OK for Tasks
            )

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-456"
        # Verify create_issue was called without application_service field
        create_call = mock_client.create_issue.call_args
        # Should not have the application_service custom field
        assert "customfield_20400" not in create_call[1]


class TestJiraUpdateIssueWithApplicationService:
    """Test suite for jira_update_issue with application_service."""

    def test_update_issue_with_app_service_list(self, mock_context):
        """Test updating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify update was called with resolved ID
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]

    def test_update_issue_with_app_service_string(self, mock_context):
        """Test updating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]


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
        # Verify truncation metadata is returned
        assert "description_total_length" in result
        assert "description_truncated" in result
        assert "character_limit" in result

    def test_get_issue_not_found(self, mock_context):
        """Test get issue not found."""
        with patch(
            "code_puppy.tools.jira_tools.JiraClient",
            side_effect=JiraNotFoundError("Not found"),
        ):
            result = jira_get_issue(mock_context, "PROJ-999")

        assert result["success"] is False
        assert result["error_type"] == "not_found"

    def test_get_issue_truncates_large_description(self, mock_context):
        """Test that large descriptions are truncated."""
        large_description = "A" * 50000  # Larger than MAX_CHARACTER_LIMIT
        issue = {
            "key": "PROJ-123",
            "fields": {
                "summary": "Test",
                "description": large_description,
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
            },
        }
        mock_client = MagicMock()
        mock_client.get_issue.return_value = issue
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_issue(mock_context, "PROJ-123")

        assert result["success"] is True
        assert result["description_truncated"] is True
        assert result["description_total_length"] == 50000
        assert len(result["issue"]["description"]) == MAX_CHARACTER_LIMIT
        assert result["description_remaining_length"] == 50000 - MAX_CHARACTER_LIMIT

    def test_get_issue_with_character_offset(self, mock_context):
        """Test paginating through large description with offset."""
        large_description = "A" * 35000 + "B" * 10000  # 45000 chars total
        issue = {
            "key": "PROJ-123",
            "fields": {
                "summary": "Test",
                "description": large_description,
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
            },
        }
        mock_client = MagicMock()
        mock_client.get_issue.return_value = issue
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_issue(mock_context, "PROJ-123", character_offset=30000)

        assert result["success"] is True
        assert result["character_offset"] == 30000
        # Should get the remaining 15000 chars (capped to MAX_CHARACTER_LIMIT but only 15000 remain)
        assert len(result["issue"]["description"]) == 15000
        assert result["description_truncated"] is False  # No more content after this


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
        # Verify truncation metadata
        assert "comments_total_length" in result
        assert result["comments_truncated"] is False

    def test_get_comments_truncates_large_comments(self, mock_context):
        """Test that large combined comment content is truncated."""
        large_body = "X" * 35000  # Each comment body is 35k chars
        mock_client = MagicMock()
        mock_client.get_comments.return_value = {
            "comments": [
                {
                    "id": "1",
                    "author": {"displayName": "John Doe"},
                    "body": large_body,
                    "created": "2025-01-01T12:00:00.000+0000",
                },
            ],
            "total": 1,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_comments(mock_context, "PROJ-123")

        assert result["success"] is True
        assert result["comments_truncated"] is True
        assert "comments_content" in result  # Returns combined content when truncated
        assert len(result["comments_content"]) == MAX_CHARACTER_LIMIT
        assert result["comments_remaining_length"] > 0

    def test_get_comments_with_offset(self, mock_context):
        """Test paginating through comments with offset."""
        mock_client = MagicMock()
        mock_client.get_comments.return_value = {
            "comments": [
                {
                    "id": "1",
                    "author": {"displayName": "John Doe"},
                    "body": "Short comment",
                    "created": "2025-01-01T12:00:00.000+0000",
                },
            ],
            "total": 1,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_get_comments(mock_context, "PROJ-123", character_offset=10)

        assert result["success"] is True
        # When offset > 0, returns combined content format
        assert "comments_content" in result
        assert result["character_offset"] == 10


# =============================================================================
# JQL ERROR SUGGESTION TESTS
# =============================================================================


class TestParseJqlErrorSuggestion:
    """Test suite for _parse_jql_error_suggestion helper."""

    def test_project_name_vs_key_suggestion(self):
        """Test suggestion for project name vs key error."""
        from code_puppy.tools.jira_tools import _parse_jql_error_suggestion

        error_msg = (
            "The value 'My Long Project Name' does not exist for the field 'project'."
        )
        suggestion = _parse_jql_error_suggestion(error_msg)

        assert suggestion is not None
        assert (
            "project KEY" in suggestion.lower() or "project key" in suggestion.lower()
        )
        assert "jira_list_projects" in suggestion

    def test_field_not_exist_suggestion(self):
        """Test suggestion for field not exist error."""
        from code_puppy.tools.jira_tools import _parse_jql_error_suggestion

        error_msg = "Field 'Start Date' does not exist or you do not have permission."
        suggestion = _parse_jql_error_suggestion(error_msg)

        assert suggestion is not None
        assert "quotes" in suggestion.lower() or "quoting" in suggestion.lower()

    def test_jql_syntax_error_suggestion(self):
        """Test suggestion for general JQL syntax errors."""
        from code_puppy.tools.jira_tools import _parse_jql_error_suggestion

        error_msg = "Error in the JQL Query: Unable to parse the query."
        suggestion = _parse_jql_error_suggestion(error_msg)

        assert suggestion is not None
        assert "quote" in suggestion.lower()

    def test_no_suggestion_for_unknown_error(self):
        """Test that unknown errors return None."""
        from code_puppy.tools.jira_tools import _parse_jql_error_suggestion

        error_msg = "Some completely random error message."
        suggestion = _parse_jql_error_suggestion(error_msg)

        assert suggestion is None

    def test_invalid_operator_suggestion(self):
        """Test suggestion for invalid operator error."""
        from code_puppy.tools.jira_tools import _parse_jql_error_suggestion

        error_msg = "'LIKE' is not a valid operator for this field."
        suggestion = _parse_jql_error_suggestion(error_msg)

        assert suggestion is not None
        assert "operator" in suggestion.lower()


class TestHandleJiraErrorWithSuggestions:
    """Test that _handle_jira_error provides suggestions for API errors."""

    def test_api_error_with_project_suggestion(self):
        """Test that project name error gets helpful suggestion."""
        error = JiraAPIError(
            "Jira API error (HTTP 400): The value 'My Project' does not exist for the field 'project'.",
            status_code=400,
        )
        result = _handle_jira_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "suggestion" in result
        assert "jira_list_projects" in result["suggestion"]

    def test_api_error_without_suggestion(self):
        """Test that unknown API error doesn't crash when no suggestion."""
        error = JiraAPIError("Some random API error", status_code=500)
        result = _handle_jira_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        # Should not have suggestion key if no suggestion available
        # (or it could be present but None)


# =============================================================================
# JIRA LIST PROJECTS TESTS
# =============================================================================


class TestJiraListProjects:
    """Test suite for jira_list_projects tool."""

    def test_list_projects_success(self, mock_context):
        """Test successful project listing."""
        from code_puppy.tools.jira_tools import jira_list_projects

        mock_client = MagicMock()
        mock_client.list_projects.return_value = {
            "projects": [
                {"key": "PROJ", "name": "My Project", "id": "10001"},
                {"key": "TEST", "name": "Test Project", "id": "10002"},
            ],
            "total": 2,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_list_projects(mock_context)

        assert result["success"] is True
        assert len(result["projects"]) == 2
        assert result["projects"][0]["key"] == "PROJ"
        assert result["total"] == 2
        assert "hint" in result  # Should include usage hint

    def test_list_projects_with_search(self, mock_context):
        """Test project listing with search query."""
        from code_puppy.tools.jira_tools import jira_list_projects

        mock_client = MagicMock()
        mock_client.search_projects.return_value = {
            "projects": [
                {"key": "FIN", "name": "Financial Services", "id": "10003"},
            ],
            "total": 1,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_list_projects(mock_context, search_query="financial")

        assert result["success"] is True
        assert len(result["projects"]) == 1
        assert result["projects"][0]["key"] == "FIN"
        # Should have called search_projects, not list_projects
        mock_client.search_projects.assert_called_once_with(
            query="financial", max_results=20
        )

    def test_list_projects_caps_max_results(self, mock_context):
        """Test that max_results is capped at 50."""
        from code_puppy.tools.jira_tools import jira_list_projects

        mock_client = MagicMock()
        mock_client.list_projects.return_value = {"projects": [], "total": 0}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            jira_list_projects(mock_context, max_results=100)

        # Should cap at 50
        mock_client.list_projects.assert_called_once_with(max_results=50)

    def test_list_projects_error(self, mock_context):
        """Test error handling for project listing."""
        from code_puppy.tools.jira_tools import jira_list_projects

        mock_client = MagicMock()
        mock_client.list_projects.side_effect = JiraAuthError("Auth failed")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("code_puppy.tools.jira_tools.JiraClient", return_value=mock_client):
            result = jira_list_projects(mock_context)

        assert result["success"] is False
        assert result["error_type"] == "authentication"


# =============================================================================
# APPLICATION/SERVICE FIELD TESTS
# =============================================================================


class TestParseApplicationServiceInput:
    """Test suite for _parse_application_service_input helper."""

    def test_parse_list_format_valid(self):
        """Test parsing valid list format."""
        result = _parse_application_service_input(
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"]
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_list_format_invalid_length(self):
        """Test parsing list with wrong number of elements."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["Level1", "Level2"])

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input(["L1", "L2", "L3", "L4"])

    def test_parse_string_arrow_delimiter(self):
        """Test parsing string with ' -> ' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_dot_delimiter(self):
        """Test parsing string with '.' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech.AP - Invoices and Payments.Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_slash_delimiter(self):
        """Test parsing string with '/' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech/AP - Invoices and Payments/Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_pipe_delimiter(self):
        """Test parsing string with '|' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech|AP - Invoices and Payments|Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_greater_than_delimiter(self):
        """Test parsing string with '>' delimiter."""
        result = _parse_application_service_input(
            "EBS Finance Tech>AP - Invoices and Payments>Pay from Scan"
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_with_whitespace(self):
        """Test parsing string with extra whitespace."""
        result = _parse_application_service_input(
            "  EBS Finance Tech  ->  AP - Invoices and Payments  ->  Pay from Scan  "
        )
        assert result == [
            "EBS Finance Tech",
            "AP - Invoices and Payments",
            "Pay from Scan",
        ]

    def test_parse_string_wrong_delimiter_count(self):
        """Test parsing string with wrong number of delimiters."""
        with pytest.raises(ValueError, match="exactly 3 levels"):
            _parse_application_service_input("Level1 -> Level2")

    def test_parse_string_no_delimiter(self):
        """Test parsing string without supported delimiter."""
        with pytest.raises(ValueError, match="separated by"):
            _parse_application_service_input("Level1 Level2 Level3")

    def test_parse_invalid_type(self):
        """Test parsing with invalid type."""
        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input(12345)

        with pytest.raises(ValueError, match="must be a list or string"):
            _parse_application_service_input({"key": "value"})


class TestResolveApplicationServiceId:
    """Test suite for _resolve_application_service_id helper."""

    def test_resolve_id_success(self):
        """Test successful ID resolution."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
                {
                    "id": "2125771",
                    "values": ["Other", "Service", "Name"],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
        )

        assert result == "2125770"

    def test_resolve_id_with_issue_context(self):
        """Test ID resolution with issue context."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                },
            ]
        }

        result = _resolve_application_service_id(
            mock_client,
            ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"],
            issue_id="28750593",
        )

        assert result == "2125770"
        # Verify the payload included fieldContext
        call_args = mock_client._make_request.call_args
        assert call_args[1]["json"]["fieldContext"] == {"issueKeyOrId": "28750593"}

    def test_resolve_id_not_found(self):
        """Test ID resolution when path is not found."""
        mock_client = MagicMock()
        mock_client._make_request.return_value = {
            "options": [
                {"id": "2125771", "values": ["Other", "Service", "Name"]},
            ]
        }

        with pytest.raises(ValueError, match="path not found"):
            _resolve_application_service_id(
                mock_client, ["Nonexistent", "Path", "Here"]
            )

    def test_resolve_id_invalid_path_length(self):
        """Test ID resolution with invalid path length."""
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="exactly 3 levels"):
            _resolve_application_service_id(mock_client, ["Level1", "Level2"])

    def test_resolve_id_api_error(self):
        """Test ID resolution when API call fails."""
        mock_client = MagicMock()
        mock_client._make_request.side_effect = JiraAPIError("API Error")

        with pytest.raises(ValueError, match="Failed to fetch"):
            _resolve_application_service_id(
                mock_client, ["Level1", "Level2", "Level3"]
            )


class TestFormatIssueWithApplicationService:
    """Test suite for _format_issue with application_service field."""

    def test_format_issue_with_resolved_app_service(self):
        """Test formatting issue with resolved application service (3 elements)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": [
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert (
            result["application_service"]
            == "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
        )

    def test_format_issue_with_app_service_id_only(self):
        """Test formatting issue with just the ID (1 element)."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": ["2125770"],
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] == "2125770"

    def test_format_issue_without_app_service(self):
        """Test formatting issue without application service field."""
        issue = {
            "key": "PROJ-123",
            "fields": {},
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None

    def test_format_issue_with_none_app_service(self):
        """Test formatting issue with None application service."""
        issue = {
            "key": "PROJ-123",
            "fields": {
                "customfield_20400": None,
            },
        }

        with patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = _format_issue(issue)

        assert result["application_service"] is None


class TestJiraCreateIssueWithApplicationService:
    """Test suite for jira_create_issue with application_service."""

    def test_create_issue_with_app_service_list(self, mock_context):
        """Test creating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify that create_issue was called with the resolved ID
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_with_app_service_string(self, mock_context):
        """Test creating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_issue_app_service_no_template_issue(self, mock_context):
        """Test creating issue when no template issue is found."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.search_issues.return_value = {"issues": []}  # No template
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Story",
                summary="Test",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Should still work, just without issue context in nFeed call
        create_call = mock_client.create_issue.call_args
        assert create_call[1]["customfield_20400"] == ["2125770"]

    def test_create_story_without_app_service_fails(self, mock_context):
        """Test that creating a Story without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Story",
            summary="Test Story",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Story" in result["error"]

    def test_create_bug_without_app_service_fails(self, mock_context):
        """Test that creating a Bug without application_service fails validation."""
        result = jira_create_issue(
            mock_context,
            project_key="PROJ",
            issue_type="Bug",
            summary="Test Bug",
            # No application_service provided
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "application_service field is required" in result["error"]
        assert "Bug" in result["error"]

    def test_create_task_without_app_service_succeeds(self, mock_context):
        """Test that creating a Task without application_service succeeds."""
        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "12345", "key": "PROJ-456"}
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ):
            result = jira_create_issue(
                mock_context,
                project_key="PROJ",
                issue_type="Task",
                summary="Test Task",
                # No application_service provided - this is OK for Tasks
            )

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-456"
        # Verify create_issue was called without application_service field
        create_call = mock_client.create_issue.call_args
        # Should not have the application_service custom field
        assert "customfield_20400" not in create_call[1]


class TestJiraUpdateIssueWithApplicationService:
    """Test suite for jira_update_issue with application_service."""

    def test_update_issue_with_app_service_list(self, mock_context):
        """Test updating issue with application service as list."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service=[
                    "EBS Finance Tech",
                    "AP - Invoices and Payments",
                    "Pay from Scan",
                ],
            )

        assert result["success"] is True
        # Verify update was called with resolved ID
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]

    def test_update_issue_with_app_service_string(self, mock_context):
        """Test updating issue with application service as string."""
        mock_client = MagicMock()
        mock_client.update_issue.return_value = None
        mock_client.search_issues.return_value = {
            "issues": [{"id": "28750593", "key": "PROJ-100"}]
        }
        mock_client._make_request.return_value = {
            "options": [
                {
                    "id": "2125770",
                    "values": [
                        "EBS Finance Tech",
                        "AP - Invoices and Payments",
                        "Pay from Scan",
                    ],
                }
            ]
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch(
            "code_puppy.tools.jira_tools.JiraClient", return_value=mock_client
        ), patch(
            "code_puppy.tools.jira_tools.get_application_service_field",
            return_value="customfield_20400",
        ):
            result = jira_update_issue(
                mock_context,
                issue_key="PROJ-123",
                application_service="EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan",
            )

        assert result["success"] is True
        update_call = mock_client.update_issue.call_args
        assert update_call[1]["fields"]["customfield_20400"] == ["2125770"]
