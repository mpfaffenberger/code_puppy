"""Integration tests for Microsoft Graph functionality.

Tests the MSGraphAgent, MSGraphClient, and associated tools
using mocked responses to avoid real API calls.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from code_puppy.agents.agent_msgraph import MSGraphAgent
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphClient,
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphAPIError,
    MSGraphThrottledError,
)
from code_puppy.tools.msgraph import MSGRAPH_TOOLS
from code_puppy.tools.msgraph.users import (
    msgraph_get_me,
    msgraph_get_user,
    msgraph_search_users,
    register_msgraph_get_me,
)
from code_puppy.tools.msgraph.common import _handle_msgraph_error


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_msgraph_client():
    """Create a mock MSGraphClient."""
    client = Mock(spec=MSGraphClient)
    client.get = Mock()
    client.post = Mock()
    client.patch = Mock()
    client.delete = Mock()
    client.close = Mock()
    return client


@pytest.fixture
def mock_run_context():
    """Create a mock RunContext for tool calls."""
    ctx = Mock()
    ctx.deps = None
    return ctx


@pytest.fixture
def sample_user_response():
    """Sample user data from MS Graph API."""
    return {
        "id": "user-12345-abcde",
        "displayName": "John Doe",
        "mail": "john.doe@walmart.com",
        "userPrincipalName": "john.doe@walmart.com",
        "jobTitle": "Software Engineer",
        "department": "Platform Engineering",
        "officeLocation": "Bentonville, AR",
        "mobilePhone": "+1-555-123-4567",
        "businessPhones": ["+1-555-987-6543"],
    }


@pytest.fixture
def sample_events_response():
    """Sample calendar events from MS Graph API."""
    return {
        "value": [
            {
                "id": "event-001",
                "subject": "Team Standup",
                "start": {
                    "dateTime": "2024-01-15T09:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2024-01-15T09:30:00",
                    "timeZone": "UTC",
                },
                "location": {"displayName": "Teams Meeting"},
                "organizer": {
                    "emailAddress": {
                        "name": "Jane Smith",
                        "address": "jane.smith@walmart.com",
                    }
                },
                "attendees": [
                    {
                        "emailAddress": {
                            "name": "John Doe",
                            "address": "john.doe@walmart.com",
                        },
                        "type": "required",
                        "status": {"response": "accepted"},
                    }
                ],
            },
            {
                "id": "event-002",
                "subject": "Sprint Planning",
                "start": {
                    "dateTime": "2024-01-15T14:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2024-01-15T15:00:00",
                    "timeZone": "UTC",
                },
                "location": {"displayName": "Conference Room A"},
                "organizer": {
                    "emailAddress": {
                        "name": "John Doe",
                        "address": "john.doe@walmart.com",
                    }
                },
                "attendees": [],
            },
        ],
        "@odata.count": 2,
    }


# =============================================================================
# AGENT INTEGRATION TESTS
# =============================================================================


class TestMSGraphIntegration:
    """Integration tests for Microsoft Graph functionality."""

    def test_msgraph_agent_instantiation(self):
        """Test that MSGraphAgent can be instantiated with correct properties."""
        agent = MSGraphAgent()

        assert agent.name == "msgraph"
        assert agent.display_name == "Microsoft Graph Agent 📊"
        assert "Microsoft 365" in agent.description
        assert "mail" in agent.description.lower()
        assert "calendar" in agent.description.lower()

    def test_msgraph_agent_tools_list(self):
        """Test that MSGraphAgent returns the correct list of tools."""
        agent = MSGraphAgent()
        tools = agent.get_available_tools()

        # Check it's a list with expected tools
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Verify key user tools are present
        assert "msgraph_get_me" in tools
        assert "msgraph_get_user" in tools
        assert "msgraph_search_users" in tools
        assert "msgraph_get_manager" in tools
        assert "msgraph_get_direct_reports" in tools

        # Verify key mail tools are present
        assert "msgraph_list_messages" in tools
        assert "msgraph_send_mail" in tools
        assert "msgraph_search_mail" in tools

        # Verify key calendar tools are present
        assert "msgraph_list_events" in tools
        assert "msgraph_create_event" in tools
        assert "msgraph_get_availability" in tools

        # Verify key OneDrive tools are present
        assert "msgraph_list_drive_items" in tools
        assert "msgraph_upload_file" in tools
        assert "msgraph_search_files" in tools

        # Verify key Teams tools are present
        assert "msgraph_list_teams" in tools
        assert "msgraph_list_channels" in tools
        assert "msgraph_create_online_meeting" in tools

        # Verify key SharePoint tools are present
        assert "msgraph_list_sites" in tools
        assert "msgraph_search_sharepoint" in tools

        # Verify key Planner tools are present
        assert "msgraph_list_tasks" in tools
        assert "msgraph_create_task" in tools

        # Verify core tool is present
        assert "agent_share_your_reasoning" in tools

    def test_msgraph_agent_system_prompt(self):
        """Test that MSGraphAgent has a comprehensive system prompt."""
        agent = MSGraphAgent()
        prompt = agent.get_system_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 500  # Should be substantial

        # Check key sections are mentioned
        assert "Mail" in prompt or "Outlook" in prompt
        assert "Calendar" in prompt
        assert "OneDrive" in prompt
        assert "Teams" in prompt
        assert "SharePoint" in prompt
        assert "Planner" in prompt
        assert "/msgraph_auth" in prompt  # Auth command mentioned

    def test_msgraph_client_instantiation(self):
        """Test MSGraphClient instantiation with mocked token file."""
        mock_token = "mock-access-token-12345"

        with patch(
            "code_puppy.plugins.walmart_specific.msgraph_client.get_valid_access_token",
            return_value=mock_token,
        ):
            client = MSGraphClient()

            assert client is not None
            assert client._access_token == mock_token
            assert client.client is not None  # httpx client should exist

            # Cleanup
            client.close()

    def test_msgraph_client_no_token_raises_auth_error(self):
        """Test that MSGraphClient raises auth error when no token available."""
        with (
            patch(
                "code_puppy.plugins.walmart_specific.msgraph_client.get_valid_access_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.walmart_specific.msgraph_client.MSGRAPH_TOKENS_FILE",
                Path("/nonexistent/path/tokens.json"),
            ),
        ):
            with pytest.raises(MSGraphAuthError) as exc_info:
                MSGraphClient()

            assert "No Microsoft Graph tokens found" in str(exc_info.value)

    def test_tool_registration(self):
        """Test that tools can be registered with a mock agent."""
        mock_agent = MagicMock()
        mock_tool = Mock()
        mock_agent.tool = Mock(return_value=mock_tool)

        # Test registering msgraph_get_me
        result = register_msgraph_get_me(mock_agent)

        mock_agent.tool.assert_called_once()
        assert result == mock_tool

    def test_msgraph_tools_registry_completeness(self):
        """Test that MSGRAPH_TOOLS dict contains all expected tools."""
        expected_tool_prefixes = [
            "msgraph_get_me",
            "msgraph_get_user",
            "msgraph_search_users",
            "msgraph_get_manager",
            "msgraph_get_direct_reports",
            "msgraph_list_messages",
            "msgraph_send_mail",
            "msgraph_list_events",
            "msgraph_create_event",
            "msgraph_list_teams",
            "msgraph_list_sites",
            "msgraph_list_tasks",
        ]

        for tool_name in expected_tool_prefixes:
            assert tool_name in MSGRAPH_TOOLS, f"Missing tool: {tool_name}"

        # Verify each entry is callable
        for name, register_fn in MSGRAPH_TOOLS.items():
            assert callable(register_fn), f"{name} register function is not callable"


# =============================================================================
# TOOL INTEGRATION TESTS
# =============================================================================


class TestMSGraphToolsIntegration:
    """Integration tests for Microsoft Graph tools."""

    def test_msgraph_get_me_tool(
        self, mock_msgraph_client, mock_run_context, sample_user_response
    ):
        """Test msgraph_get_me tool integration."""
        mock_msgraph_client.get.return_value = sample_user_response

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_get_me(mock_run_context)

            assert result["success"] is True
            assert "user" in result
            assert result["user"]["display_name"] == "John Doe"
            assert result["user"]["mail"] == "john.doe@walmart.com"
            assert result["user"]["job_title"] == "Software Engineer"

            mock_msgraph_client.get.assert_called_once_with("/me")

    def test_msgraph_get_user_tool(
        self, mock_msgraph_client, mock_run_context, sample_user_response
    ):
        """Test msgraph_get_user tool integration."""
        mock_msgraph_client.get.return_value = sample_user_response

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_get_user(mock_run_context, user_id="john.doe@walmart.com")

            assert result["success"] is True
            assert result["user"]["display_name"] == "John Doe"

            mock_msgraph_client.get.assert_called_once_with(
                "/users/john.doe@walmart.com"
            )

    def test_msgraph_search_users_tool(self, mock_msgraph_client, mock_run_context):
        """Test msgraph_search_users tool integration."""
        mock_msgraph_client.get.return_value = {
            "value": [
                {
                    "id": "user-001",
                    "displayName": "John Doe",
                    "mail": "john.doe@walmart.com",
                    "userPrincipalName": "john.doe@walmart.com",
                },
                {
                    "id": "user-002",
                    "displayName": "John Smith",
                    "mail": "john.smith@walmart.com",
                    "userPrincipalName": "john.smith@walmart.com",
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_search_users(mock_run_context, query="John", limit=10)

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["users"]) == 2
            assert result["query"] == "John"

    def test_tool_handles_auth_error(self, mock_msgraph_client, mock_run_context):
        """Test that tools properly handle authentication errors."""
        mock_msgraph_client.get.side_effect = MSGraphAuthError(
            "Token expired. Please re-authenticate."
        )

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_get_me(mock_run_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"

    def test_tool_handles_not_found_error(self, mock_msgraph_client, mock_run_context):
        """Test that tools properly handle not found errors."""
        mock_msgraph_client.get.side_effect = MSGraphNotFoundError("User not found")

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_get_user(
                mock_run_context, user_id="nonexistent@walmart.com"
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_tool_handles_throttled_error(self, mock_msgraph_client, mock_run_context):
        """Test that tools properly handle rate limiting errors."""
        mock_msgraph_client.get.side_effect = MSGraphThrottledError(
            "Rate limited", retry_after=30
        )

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            result = msgraph_get_me(mock_run_context)

            assert result["success"] is False
            assert result["error_type"] == "throttled"
            assert result["retry_after"] == 30


# =============================================================================
# END-TO-END FLOW TESTS
# =============================================================================


class TestMSGraphEndToEndFlow:
    """Test mock end-to-end flows through MS Graph."""

    def test_get_user_then_list_events_flow(
        self,
        mock_msgraph_client,
        mock_run_context,
        sample_user_response,
        sample_events_response,
    ):
        """Test a realistic flow: get user profile, then list their events."""

        # Set up mock to return different responses for different endpoints
        def mock_get(endpoint, **kwargs):
            if endpoint == "/me":
                return sample_user_response
            elif endpoint.startswith("/me/events") or endpoint.startswith(
                "/me/calendarView"
            ):
                return sample_events_response
            return {}

        mock_msgraph_client.get.side_effect = mock_get

        with (
            patch(
                "code_puppy.tools.msgraph.users.get_msgraph_client",
                return_value=mock_msgraph_client,
            ),
            patch(
                "code_puppy.tools.msgraph.calendar.get_msgraph_client",
                return_value=mock_msgraph_client,
            ),
        ):
            # Step 1: Get current user
            from code_puppy.tools.msgraph.users import msgraph_get_me

            user_result = msgraph_get_me(mock_run_context)

            assert user_result["success"] is True
            assert user_result["user"]["display_name"] == "John Doe"

            # Step 2: List their calendar events
            from code_puppy.tools.msgraph.calendar import msgraph_list_events

            events_result = msgraph_list_events(mock_run_context)

            assert events_result["success"] is True
            assert "events" in events_result
            assert len(events_result["events"]) == 2

            # Verify the events have expected data
            event_subjects = [e["subject"] for e in events_result["events"]]
            assert "Team Standup" in event_subjects
            assert "Sprint Planning" in event_subjects

    def test_search_user_then_get_manager_flow(
        self, mock_msgraph_client, mock_run_context
    ):
        """Test flow: search for a user, then get their manager."""
        search_response = {
            "value": [
                {
                    "id": "user-123",
                    "displayName": "Alice Johnson",
                    "mail": "alice.johnson@walmart.com",
                    "userPrincipalName": "alice.johnson@walmart.com",
                }
            ]
        }

        manager_response = {
            "id": "manager-456",
            "displayName": "Bob Manager",
            "mail": "bob.manager@walmart.com",
            "userPrincipalName": "bob.manager@walmart.com",
            "jobTitle": "Engineering Manager",
        }

        def mock_get(endpoint, **kwargs):
            if endpoint == "/users":
                return search_response
            elif "/manager" in endpoint:
                return manager_response
            return {}

        mock_msgraph_client.get.side_effect = mock_get

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client",
            return_value=mock_msgraph_client,
        ):
            from code_puppy.tools.msgraph.users import (
                msgraph_search_users,
                msgraph_get_manager,
            )

            # Step 1: Search for user
            search_result = msgraph_search_users(
                mock_run_context, query="Alice", limit=5
            )

            assert search_result["success"] is True
            assert search_result["total_count"] == 1
            found_user = search_result["users"][0]
            assert found_user["display_name"] == "Alice Johnson"

            # Step 2: Get the user's manager using their ID
            manager_result = msgraph_get_manager(
                mock_run_context, user_id=found_user["id"]
            )

            assert manager_result["success"] is True
            assert manager_result["manager"]["display_name"] == "Bob Manager"
            assert manager_result["manager"]["job_title"] == "Engineering Manager"


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestMSGraphErrorHandling:
    """Test error handling utilities."""

    def test_handle_auth_error(self):
        """Test _handle_msgraph_error with MSGraphAuthError."""
        error = MSGraphAuthError("Token expired")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert "Token expired" in result["error"]
        assert result["error_type"] == "authentication"

    def test_handle_not_found_error(self):
        """Test _handle_msgraph_error with MSGraphNotFoundError."""
        error = MSGraphNotFoundError("Resource /users/xyz not found")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "not_found"

    def test_handle_throttled_error(self):
        """Test _handle_msgraph_error with MSGraphThrottledError."""
        error = MSGraphThrottledError("Rate limited", retry_after=60)
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "throttled"
        assert result["retry_after"] == 60

    def test_handle_api_error(self):
        """Test _handle_msgraph_error with MSGraphAPIError."""
        error = MSGraphAPIError(
            "Bad request", status_code=400, error_code="InvalidRequest"
        )
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert result["status_code"] == 400
        assert result["error_code"] == "InvalidRequest"

    def test_handle_unexpected_error(self):
        """Test _handle_msgraph_error with generic exception."""
        error = ValueError("Something went wrong")
        result = _handle_msgraph_error(error)

        assert result["success"] is False
        assert result["error_type"] == "unknown"
        assert "Something went wrong" in result["error"]
