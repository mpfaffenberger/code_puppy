"""Tests for Presence tools."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.presence import (
    msgraph_get_my_presence,
    msgraph_get_user_presence,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestMSGraphPresence:
    """Tests for presence/availability operations."""

    def test_msgraph_get_my_presence(self, mock_context):
        """Test getting your own presence status."""
        with patch(
            "code_puppy.tools.msgraph.presence.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "user-001",
                "availability": "Available",
                "activity": "Available",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_my_presence(mock_context)

            assert result["success"] is True
            assert result["presence"]["availability"] == "Available"

    def test_msgraph_get_user_presence(self, mock_context):
        """Test getting another user's presence status."""
        with patch(
            "code_puppy.tools.msgraph.presence.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "user-002",
                "availability": "Busy",
                "activity": "InAMeeting",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_user_presence(mock_context, "jane@example.com")

            assert result["success"] is True
            assert result["user_id"] == "jane@example.com"
            assert result["presence"]["availability"] == "Busy"
            assert result["presence"]["activity"] == "InAMeeting"

    def test_msgraph_get_my_presence_away(self, mock_context):
        """Test presence when user is away."""
        with patch(
            "code_puppy.tools.msgraph.presence.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "user-001",
                "availability": "Away",
                "activity": "Away",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_my_presence(mock_context)

            assert result["success"] is True
            assert result["presence"]["availability"] == "Away"
