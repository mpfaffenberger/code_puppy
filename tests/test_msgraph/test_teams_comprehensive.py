"""Comprehensive tests for teams.py to achieve higher coverage.

These tests target specific branches and error paths.
"""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.msgraph.teams import (
    msgraph_list_teams,
    msgraph_get_team,
    msgraph_list_channels,
    msgraph_get_channel,
    msgraph_send_channel_message,
    msgraph_list_channel_messages,
    msgraph_list_chats,
    msgraph_send_chat_message,
    msgraph_send_direct_message,
    msgraph_create_online_meeting,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return MagicMock()


class TestTeamsFunctions:
    """Test Teams functions for coverage."""

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_teams_success(self, mock_client_fn, mock_context):
        """Test listing joined teams."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "value": [
                {
                    "id": "team-1",
                    "displayName": "Platform Team",
                    "description": "Platform engineering",
                },
                {
                    "id": "team-2",
                    "displayName": "DevOps",
                    "description": "DevOps team",
                },
            ]
        }

        result = msgraph_list_teams(mock_context)

        assert result["success"] is True
        assert len(result["teams"]) == 2

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_teams_error(self, mock_client_fn, mock_context):
        """Test list teams error handling."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_list_teams(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_team_success(self, mock_client_fn, mock_context):
        """Test getting team details."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "id": "team-123",
            "displayName": "Platform Team",
            "description": "Platform engineering",
        }

        result = msgraph_get_team(mock_context, team_id="team-123")

        assert result["success"] is True
        assert result["team"]["id"] == "team-123"

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_team_error(self, mock_client_fn, mock_context):
        """Test get team error handling."""
        mock_client_fn.side_effect = Exception("Not found")

        result = msgraph_get_team(mock_context, team_id="invalid")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channels_success(self, mock_client_fn, mock_context):
        """Test listing team channels."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "value": [
                {"id": "ch-1", "displayName": "General", "description": "General chat"},
                {"id": "ch-2", "displayName": "Random", "description": "Random chat"},
            ]
        }

        result = msgraph_list_channels(mock_context, team_id="team-123")

        assert result["success"] is True
        assert len(result["channels"]) == 2

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channels_error(self, mock_client_fn, mock_context):
        """Test list channels error."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_list_channels(mock_context, team_id="team-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_channel_success(self, mock_client_fn, mock_context):
        """Test getting channel details."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "id": "ch-123",
            "displayName": "General",
            "description": "General discussion",
        }

        result = msgraph_get_channel(
            mock_context,
            team_id="team-123",
            channel_id="ch-123",
        )

        assert result["success"] is True
        assert result["channel"]["id"] == "ch-123"

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_channel_error(self, mock_client_fn, mock_context):
        """Test get channel error."""
        mock_client_fn.side_effect = Exception("Not found")

        result = msgraph_get_channel(
            mock_context,
            team_id="team-123",
            channel_id="invalid",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_channel_message_success(self, mock_client_fn, mock_context):
        """Test sending channel message."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.post.return_value = {
            "id": "msg-123",
            "body": {"content": "Hello team!"},
            "createdDateTime": "2025-12-18T10:00:00Z",
            "from": {"user": {"displayName": "Test User"}},
        }

        result = msgraph_send_channel_message(
            mock_context,
            team_id="team-123",
            channel_id="ch-123",
            content="Hello team!",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_channel_message_error(self, mock_client_fn, mock_context):
        """Test send channel message error."""
        mock_client_fn.side_effect = Exception("Post failed")

        result = msgraph_send_channel_message(
            mock_context,
            team_id="team-123",
            channel_id="ch-123",
            content="Hello!",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channel_messages_success(self, mock_client_fn, mock_context):
        """Test listing channel messages."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "value": [
                {
                    "id": "msg-1",
                    "body": {"content": "Message 1"},
                    "createdDateTime": "2025-12-18T10:00:00Z",
                    "from": {"user": {"displayName": "User 1"}},
                },
            ]
        }

        result = msgraph_list_channel_messages(
            mock_context,
            team_id="team-123",
            channel_id="ch-123",
        )

        assert result["success"] is True
        assert len(result["messages"]) == 1

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channel_messages_error(self, mock_client_fn, mock_context):
        """Test list channel messages error."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_list_channel_messages(
            mock_context,
            team_id="team-123",
            channel_id="ch-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_chats_success(self, mock_client_fn, mock_context):
        """Test listing chats."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get.return_value = {
            "value": [
                {
                    "id": "chat-1",
                    "chatType": "oneOnOne",
                    "topic": None,
                    "members": [],
                },
            ]
        }

        result = msgraph_list_chats(mock_context)

        assert result["success"] is True
        assert len(result["chats"]) == 1

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_chats_error(self, mock_client_fn, mock_context):
        """Test list chats error."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_list_chats(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_chat_message_success(self, mock_client_fn, mock_context):
        """Test sending chat message."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.post.return_value = {
            "id": "msg-123",
            "body": {"content": "Hello!"},
            "createdDateTime": "2025-12-18T10:00:00Z",
            "from": {"user": {"displayName": "Me"}},
        }

        result = msgraph_send_chat_message(
            mock_context,
            chat_id="chat-123",
            content="Hello!",
        )

        assert result["success"] is True
        assert result["chat_id"] == "chat-123"

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_chat_message_error(self, mock_client_fn, mock_context):
        """Test send chat message error."""
        mock_client_fn.side_effect = Exception("Post failed")

        result = msgraph_send_chat_message(
            mock_context,
            chat_id="chat-123",
            content="Hello!",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_direct_message_success(self, mock_client_fn, mock_context):
        """Test sending direct message."""
        client = MagicMock()
        mock_client_fn.return_value = client

        # First call creates/gets chat, second sends message
        client.post.side_effect = [
            {"id": "chat-new", "chatType": "oneOnOne"},  # Create chat
            {
                "id": "msg-123",
                "body": {"content": "Hi!"},
                "createdDateTime": "2025-12-18T10:00:00Z",
            },  # Send message
        ]

        result = msgraph_send_direct_message(
            mock_context,
            user_email="alice@walmart.com",
            content="Hi Alice!",
        )

        assert result["success"] is True
        assert result["recipient"] == "alice@walmart.com"
        assert result["chat_id"] == "chat-new"

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_direct_message_no_chat_id(self, mock_client_fn, mock_context):
        """Test direct message when no chat ID returned."""
        client = MagicMock()
        mock_client_fn.return_value = client

        # Chat creation returns no ID
        client.post.return_value = {}  # No id field

        result = msgraph_send_direct_message(
            mock_context,
            user_email="alice@walmart.com",
            content="Hi!",
        )

        assert result["success"] is False
        assert "no chat ID" in result["error"]

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_direct_message_error(self, mock_client_fn, mock_context):
        """Test direct message error."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_send_direct_message(
            mock_context,
            user_email="alice@walmart.com",
            content="Hi!",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_create_online_meeting_success(self, mock_client_fn, mock_context):
        """Test creating online meeting."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.post.return_value = {
            "id": "meeting-123",
            "joinUrl": "https://teams.microsoft.com/meet/12345",
            "subject": "Test Meeting",
            "startDateTime": "2025-12-18T10:00:00Z",
            "endDateTime": "2025-12-18T11:00:00Z",
        }

        result = msgraph_create_online_meeting(
            mock_context,
            subject="Test Meeting",
            start="2025-12-18T10:00:00Z",
            end="2025-12-18T11:00:00Z",
        )

        assert result["success"] is True
        assert "joinUrl" in result["meeting"] or "join_url" in str(result)

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_create_online_meeting_with_attendees(self, mock_client_fn, mock_context):
        """Test creating online meeting with attendees."""
        client = MagicMock()
        mock_client_fn.return_value = client
        client.post.return_value = {
            "id": "meeting-123",
            "joinUrl": "https://teams.microsoft.com/meet/12345",
            "subject": "Team Sync",
            "startDateTime": "2025-12-18T10:00:00Z",
            "endDateTime": "2025-12-18T11:00:00Z",
        }

        result = msgraph_create_online_meeting(
            mock_context,
            subject="Team Sync",
            start="2025-12-18T10:00:00Z",
            end="2025-12-18T11:00:00Z",
            attendees=["alice@walmart.com", "bob@walmart.com"],
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_create_online_meeting_error(self, mock_client_fn, mock_context):
        """Test create meeting error."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_create_online_meeting(
            mock_context,
            subject="Test",
            start="2025-12-18T10:00:00Z",
            end="2025-12-18T11:00:00Z",
        )

        assert result["success"] is False
