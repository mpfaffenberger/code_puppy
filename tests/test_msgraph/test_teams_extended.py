"""Tests for MS Graph Extended Teams capabilities."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.teams_extended import (
    msgraph_get_unread_chats,
    msgraph_search_chat_messages,
    msgraph_get_recent_channel_activity,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestGetUnreadChats:
    """Tests for msgraph_get_unread_chats."""

    @patch("code_puppy.tools.msgraph.teams_extended.get_msgraph_client")
    def test_get_chats_success(self, mock_client, mock_ctx):
        """Test getting unread chats."""
        mock_client.return_value.get.return_value = {
            "value": [
                {
                    "id": "chat-1",
                    "topic": "Project Discussion",
                    "chatType": "group",
                    "lastUpdatedDateTime": "2024-12-17T10:00:00Z",
                    "lastMessagePreview": {
                        "from": {"user": {"displayName": "Alice"}},
                        "body": {"content": "Let's sync tomorrow"},
                        "createdDateTime": "2024-12-17T10:00:00Z",
                    },
                    "webUrl": "https://teams.microsoft.com/chat/1",
                }
            ]
        }

        result = msgraph_get_unread_chats(mock_ctx, top=20)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["chats"][0]["topic"] == "Project Discussion"
        assert result["chats"][0]["last_message"]["from"] == "Alice"

    @patch("code_puppy.tools.msgraph.teams_extended.get_msgraph_client")
    def test_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_get_unread_chats(mock_ctx)

        assert result["success"] is False


class TestSearchChatMessages:
    """Tests for msgraph_search_chat_messages."""

    @patch("code_puppy.tools.msgraph.teams_extended.get_msgraph_client")
    def test_search_success(self, mock_client, mock_ctx):
        """Test searching chat messages."""
        mock_client.return_value.get.side_effect = [
            # Get chats
            {"value": [{"id": "chat-1"}]},
            # Get messages from chat
            {
                "value": [
                    {
                        "id": "msg-1",
                        "body": {"content": "Let's discuss the migration plan"},
                        "from": {"user": {"displayName": "Bob"}},
                        "createdDateTime": "2024-12-17T10:00:00Z",
                    }
                ]
            },
        ]

        result = msgraph_search_chat_messages(
            mock_ctx, query="migration", days_back=7
        )

        assert result["success"] is True
        assert result["count"] == 1
        assert "migration" in result["messages"][0]["content"].lower()

    def test_empty_query(self, mock_ctx):
        """Test that empty query is rejected."""
        result = msgraph_search_chat_messages(mock_ctx, query="")

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    def test_whitespace_query(self, mock_ctx):
        """Test that whitespace-only query is rejected."""
        result = msgraph_search_chat_messages(mock_ctx, query="   ")

        assert result["success"] is False


class TestGetRecentChannelActivity:
    """Tests for msgraph_get_recent_channel_activity."""

    @patch("code_puppy.tools.msgraph.teams_extended.get_msgraph_client")
    def test_get_activity_success(self, mock_client, mock_ctx):
        """Test getting recent channel activity."""
        mock_client.return_value.get.side_effect = [
            # Get joined teams
            {"value": [{"id": "team-1", "displayName": "Engineering"}]},
            # Get channels
            {"value": [{"id": "channel-1", "displayName": "General"}]},
            # Get messages
            {
                "value": [
                    {
                        "id": "msg-1",
                        "messageType": "message",
                        "from": {"user": {"displayName": "Charlie"}},
                        "body": {"content": "New release is out!"},
                        "createdDateTime": "2024-12-17T10:00:00Z",
                        "webUrl": "https://teams.microsoft.com/msg/1",
                    }
                ]
            },
        ]

        result = msgraph_get_recent_channel_activity(mock_ctx, top=10)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["activity"][0]["team"] == "Engineering"
        assert result["activity"][0]["channel"] == "General"
        assert result["activity"][0]["from"] == "Charlie"

    @patch("code_puppy.tools.msgraph.teams_extended.get_msgraph_client")
    def test_specific_team(self, mock_client, mock_ctx):
        """Test getting activity for specific team."""
        mock_client.return_value.get.side_effect = [
            # Get channels
            {"value": [{"id": "channel-1", "displayName": "Announcements"}]},
            # Get messages
            {"value": []},
        ]

        result = msgraph_get_recent_channel_activity(
            mock_ctx, team_id="specific-team-id"
        )

        assert result["success"] is True
