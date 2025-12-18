"""Unit tests for MS Graph users module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.users import (
    msgraph_get_me,
    msgraph_get_user,
    msgraph_search_users,
    msgraph_get_manager,
    msgraph_get_direct_reports,
)
from code_puppy.plugins.walmart_specific.msgraph_client import MSGraphAuthError


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_user_data():
    """Create mock user data from MS Graph API."""
    return {
        "id": "user-123-abc",
        "displayName": "John Doe",
        "mail": "john.doe@walmart.com",
        "userPrincipalName": "john.doe@walmart.com",
        "jobTitle": "Senior Engineer",
        "department": "Technology",
        "officeLocation": "Bentonville, AR",
        "mobilePhone": "+1-555-123-4567",
        "businessPhones": ["+1-555-987-6543"],
    }


@pytest.fixture
def mock_manager_data():
    """Create mock manager data."""
    return {
        "id": "manager-456-def",
        "displayName": "Jane Smith",
        "mail": "jane.smith@walmart.com",
        "userPrincipalName": "jane.smith@walmart.com",
        "jobTitle": "Engineering Manager",
        "department": "Technology",
        "officeLocation": "Bentonville, AR",
        "mobilePhone": None,
        "businessPhones": [],
    }


@pytest.fixture
def mock_direct_reports_data():
    """Create mock direct reports list."""
    return {
        "value": [
            {
                "id": "report-1",
                "displayName": "Alice Johnson",
                "mail": "alice.johnson@walmart.com",
                "userPrincipalName": "alice.johnson@walmart.com",
                "jobTitle": "Software Engineer",
                "department": "Technology",
                "officeLocation": "Bentonville, AR",
                "mobilePhone": None,
                "businessPhones": [],
            },
            {
                "id": "report-2",
                "displayName": "Bob Williams",
                "mail": "bob.williams@walmart.com",
                "userPrincipalName": "bob.williams@walmart.com",
                "jobTitle": "Software Engineer",
                "department": "Technology",
                "officeLocation": "Dallas, TX",
                "mobilePhone": None,
                "businessPhones": [],
            },
        ]
    }


class TestMSGraphUserTools:
    """Test suite for MS Graph user tools."""

    def test_msgraph_get_me(self, mock_context, mock_user_data):
        """Test successful retrieval of current user profile."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_user_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_me(mock_context)

            assert result["success"] is True
            assert "user" in result
            assert result["user"]["display_name"] == "John Doe"
            assert result["user"]["mail"] == "john.doe@walmart.com"
            assert result["user"]["job_title"] == "Senior Engineer"
            assert result["user"]["department"] == "Technology"
            mock_client.get.assert_called_once_with("/me")

    def test_msgraph_get_me_auth_error(self, mock_context):
        """Test handling of 401 authentication error."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_get_me(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert "authentication" in result.get("error_type", "").lower()
            assert "Authentication failed" in result["error"]

    def test_msgraph_get_user(self, mock_context, mock_user_data):
        """Test successful retrieval of user by ID."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_user_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_user(mock_context, "user-123-abc")

            assert result["success"] is True
            assert "user" in result
            assert result["user"]["id"] == "user-123-abc"
            assert result["user"]["display_name"] == "John Doe"
            mock_client.get.assert_called_once_with("/users/user-123-abc")

    def test_msgraph_get_user_by_email(self, mock_context, mock_user_data):
        """Test retrieval of user by email/UPN."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_user_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_user(mock_context, "john.doe@walmart.com")

            assert result["success"] is True
            assert result["user"]["mail"] == "john.doe@walmart.com"
            mock_client.get.assert_called_once_with("/users/john.doe@walmart.com")

    def test_msgraph_search_users(self, mock_context):
        """Test searching users in the directory."""
        mock_search_response = {
            "value": [
                {
                    "id": "user-1",
                    "displayName": "John Doe",
                    "mail": "john.doe@walmart.com",
                    "userPrincipalName": "john.doe@walmart.com",
                    "jobTitle": "Engineer",
                    "department": "Tech",
                    "officeLocation": None,
                    "mobilePhone": None,
                    "businessPhones": [],
                },
                {
                    "id": "user-2",
                    "displayName": "John Smith",
                    "mail": "john.smith@walmart.com",
                    "userPrincipalName": "john.smith@walmart.com",
                    "jobTitle": "Manager",
                    "department": "Tech",
                    "officeLocation": None,
                    "mobilePhone": None,
                    "businessPhones": [],
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_search_response
            mock_get_client.return_value = mock_client

            result = msgraph_search_users(mock_context, "John")

            assert result["success"] is True
            assert "users" in result
            assert result["total_count"] == 2
            assert result["query"] == "John"
            assert len(result["users"]) == 2
            assert result["users"][0]["display_name"] == "John Doe"
            assert result["users"][1]["display_name"] == "John Smith"

    def test_msgraph_search_users_with_limit(self, mock_context):
        """Test search with custom limit parameter."""
        mock_search_response = {
            "value": [
                {
                    "id": "user-1",
                    "displayName": "Test User",
                    "mail": "test@walmart.com",
                    "userPrincipalName": "test@walmart.com",
                    "jobTitle": None,
                    "department": None,
                    "officeLocation": None,
                    "mobilePhone": None,
                    "businessPhones": [],
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_search_response
            mock_get_client.return_value = mock_client

            result = msgraph_search_users(mock_context, "Test", limit=5)

            assert result["success"] is True
            # Verify the limit was passed to the API
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 5

    def test_msgraph_search_users_empty_results(self, mock_context):
        """Test search with no matching results."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_search_users(mock_context, "NonexistentUser123")

            assert result["success"] is True
            assert result["users"] == []
            assert result["total_count"] == 0

    def test_msgraph_get_manager(self, mock_context, mock_manager_data):
        """Test getting user's manager."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_manager_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_manager(mock_context, "user-123")

            assert result["success"] is True
            assert "manager" in result
            assert result["manager"]["display_name"] == "Jane Smith"
            assert result["manager"]["job_title"] == "Engineering Manager"
            assert result["user_id"] == "user-123"
            mock_client.get.assert_called_once_with("/users/user-123/manager")

    def test_msgraph_get_manager_for_me(self, mock_context, mock_manager_data):
        """Test getting current user's manager using 'me'."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_manager_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_manager(mock_context)  # Default is "me"

            assert result["success"] is True
            assert result["manager"]["display_name"] == "Jane Smith"
            assert result["user_id"] == "me"
            mock_client.get.assert_called_once_with("/me/manager")

    def test_msgraph_get_direct_reports(self, mock_context, mock_direct_reports_data):
        """Test getting user's direct reports."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_direct_reports_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_direct_reports(mock_context, "manager-456")

            assert result["success"] is True
            assert "direct_reports" in result
            assert result["count"] == 2
            assert result["user_id"] == "manager-456"
            assert len(result["direct_reports"]) == 2
            assert result["direct_reports"][0]["display_name"] == "Alice Johnson"
            assert result["direct_reports"][1]["display_name"] == "Bob Williams"
            mock_client.get.assert_called_once()

    def test_msgraph_get_direct_reports_for_me(
        self, mock_context, mock_direct_reports_data
    ):
        """Test getting current user's direct reports using 'me'."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_direct_reports_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_direct_reports(mock_context)  # Default is "me"

            assert result["success"] is True
            assert result["count"] == 2
            assert result["user_id"] == "me"
            # Verify the endpoint used
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/directReports"

    def test_msgraph_get_direct_reports_with_limit(self, mock_context):
        """Test getting direct reports with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_get_direct_reports(mock_context, "user-123", limit=25)

            assert result["success"] is True
            # Verify the limit was passed to the API
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 25

    def test_msgraph_get_direct_reports_empty(self, mock_context):
        """Test user with no direct reports."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_get_direct_reports(mock_context, "individual-contributor")

            assert result["success"] is True
            assert result["direct_reports"] == []
            assert result["count"] == 0


class TestMSGraphUserFormatting:
    """Test suite for user data formatting."""

    def test_user_fields_are_formatted_correctly(self, mock_context, mock_user_data):
        """Verify all user fields are properly mapped from API response."""
        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_user_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_me(mock_context)

            user = result["user"]
            assert user["id"] == "user-123-abc"
            assert user["display_name"] == "John Doe"
            assert user["mail"] == "john.doe@walmart.com"
            assert user["user_principal_name"] == "john.doe@walmart.com"
            assert user["job_title"] == "Senior Engineer"
            assert user["department"] == "Technology"
            assert user["office_location"] == "Bentonville, AR"
            assert user["mobile_phone"] == "+1-555-123-4567"
            assert user["business_phones"] == ["+1-555-987-6543"]

    def test_missing_fields_return_none(self, mock_context):
        """Test handling of missing optional fields in user data."""
        minimal_user_data = {
            "id": "minimal-user",
            "displayName": "Minimal User",
            # All other fields missing
        }

        with patch(
            "code_puppy.tools.msgraph.users.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = minimal_user_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_me(mock_context)

            user = result["user"]
            assert user["id"] == "minimal-user"
            assert user["display_name"] == "Minimal User"
            assert user["mail"] is None
            assert user["job_title"] is None
            assert user["department"] is None
            assert user["business_phones"] == []
