"""Unit tests for MS Graph Teams module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.teams import (
    msgraph_list_teams,
    msgraph_get_team,
    msgraph_list_channels,
    msgraph_get_channel,
    msgraph_list_channel_messages,
    msgraph_send_channel_message,
    msgraph_create_online_meeting,
    msgraph_list_chats,
    msgraph_list_chat_messages,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphThrottledError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture(autouse=True)
def auto_approve_msgraph_actions():
    """Auto-approve all msgraph approval requests in tests."""
    with patch(
        "code_puppy.tools.msgraph.teams.require_user_approval"
    ):
        yield


@pytest.fixture
def mock_teams_data():
    """Create mock teams list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "team-123-abc",
                "displayName": "Engineering Team",
                "description": "Main engineering team",
                "visibility": "private",
                "webUrl": "https://teams.microsoft.com/l/team/team-123-abc",
            },
            {
                "id": "team-456-def",
                "displayName": "Product Team",
                "description": "Product development team",
                "visibility": "public",
                "webUrl": "https://teams.microsoft.com/l/team/team-456-def",
            },
        ]
    }


@pytest.fixture
def mock_team_data():
    """Create mock single team data from MS Graph API."""
    return {
        "id": "team-123-abc",
        "displayName": "Engineering Team",
        "description": "Main engineering team",
        "visibility": "private",
        "webUrl": "https://teams.microsoft.com/l/team/team-123-abc",
    }


@pytest.fixture
def mock_channels_data():
    """Create mock channels list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "channel-general-123",
                "displayName": "General",
                "description": "General discussion channel",
                "membershipType": "standard",
                "webUrl": "https://teams.microsoft.com/l/channel/channel-general-123",
            },
            {
                "id": "channel-dev-456",
                "displayName": "Development",
                "description": "Development discussions",
                "membershipType": "private",
                "webUrl": "https://teams.microsoft.com/l/channel/channel-dev-456",
            },
        ]
    }


@pytest.fixture
def mock_channel_data():
    """Create mock single channel data from MS Graph API."""
    return {
        "id": "channel-general-123",
        "displayName": "General",
        "description": "General discussion channel",
        "membershipType": "standard",
        "webUrl": "https://teams.microsoft.com/l/channel/channel-general-123",
    }


@pytest.fixture
def mock_messages_data():
    """Create mock channel messages data from MS Graph API."""
    return {
        "value": [
            {
                "id": "msg-001",
                "from": {
                    "user": {
                        "id": "user-abc-123",
                        "displayName": "John Doe",
                    }
                },
                "body": {
                    "contentType": "text",
                    "content": "Hello team!",
                },
                "createdDateTime": "2025-01-15T10:30:00Z",
                "lastModifiedDateTime": "2025-01-15T10:30:00Z",
                "messageType": "message",
                "importance": "normal",
            },
            {
                "id": "msg-002",
                "from": {
                    "user": {
                        "id": "user-def-456",
                        "displayName": "Jane Smith",
                    }
                },
                "body": {
                    "contentType": "html",
                    "content": "<p>Important update!</p>",
                },
                "createdDateTime": "2025-01-15T11:00:00Z",
                "lastModifiedDateTime": "2025-01-15T11:05:00Z",
                "messageType": "message",
                "importance": "high",
            },
        ]
    }


@pytest.fixture
def mock_sent_message_data():
    """Create mock sent message response from MS Graph API."""
    return {
        "id": "msg-new-001",
        "from": {
            "user": {
                "id": "current-user-id",
                "displayName": "Current User",
            }
        },
        "body": {
            "contentType": "text",
            "content": "Test message content",
        },
        "createdDateTime": "2025-01-15T12:00:00Z",
        "lastModifiedDateTime": "2025-01-15T12:00:00Z",
        "messageType": "message",
        "importance": "normal",
    }


@pytest.fixture
def mock_meeting_data():
    """Create mock online meeting data from MS Graph API."""
    return {
        "id": "meeting-xyz-789",
        "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/meeting-xyz-789",
        "subject": "Sprint Planning",
        "startDateTime": "2025-01-20T14:00:00Z",
        "endDateTime": "2025-01-20T15:00:00Z",
        "joinInformation": {
            "content": "Join meeting info...",
        },
    }


@pytest.fixture
def mock_chats_data():
    """Create mock chats list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "chat-001-abc",
                "topic": None,  # 1:1 chats often have no topic
                "chatType": "oneOnOne",
                "createdDateTime": "2025-01-10T09:00:00Z",
                "lastUpdatedDateTime": "2025-01-15T16:30:00Z",
                "webUrl": "https://teams.microsoft.com/l/chat/chat-001-abc",
            },
            {
                "id": "chat-002-def",
                "topic": "Project Discussion",
                "chatType": "group",
                "createdDateTime": "2025-01-05T10:00:00Z",
                "lastUpdatedDateTime": "2025-01-15T14:00:00Z",
                "webUrl": "https://teams.microsoft.com/l/chat/chat-002-def",
            },
        ]
    }


class TestMSGraphListTeams:
    """Test suite for msgraph_list_teams tool."""

    def test_msgraph_list_teams(self, mock_context, mock_teams_data):
        """Test listing teams successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_teams_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_teams(mock_context)

            assert result["success"] is True
            assert "teams" in result
            assert result["total_count"] == 2
            assert len(result["teams"]) == 2

            # Check first team
            team1 = result["teams"][0]
            assert team1["id"] == "team-123-abc"
            assert team1["display_name"] == "Engineering Team"
            assert team1["description"] == "Main engineering team"
            assert team1["visibility"] == "private"
            assert "teams.microsoft.com" in team1["web_url"]

            # Verify API call
            mock_client.get.assert_called_once_with("/me/joinedTeams")

    def test_msgraph_list_teams_empty(self, mock_context):
        """Test listing teams when user has no teams."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_teams(mock_context)

            assert result["success"] is True
            assert result["teams"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_teams_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_list_teams(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]


class TestMSGraphGetTeam:
    """Test suite for msgraph_get_team tool."""

    def test_msgraph_get_team(self, mock_context, mock_team_data):
        """Test getting team details successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_team_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_team(mock_context, "team-123-abc")

            assert result["success"] is True
            assert "team" in result

            team = result["team"]
            assert team["id"] == "team-123-abc"
            assert team["display_name"] == "Engineering Team"
            assert team["description"] == "Main engineering team"
            assert team["visibility"] == "private"

            # Verify API call
            mock_client.get.assert_called_once_with("/teams/team-123-abc")

    def test_msgraph_get_team_not_found(self, mock_context):
        """Test handling of team not found error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Team not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_team(mock_context, "nonexistent-team-id")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "not_found"
            assert "not found" in result["error"].lower()

    def test_msgraph_get_team_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_team(mock_context, "team-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphListChannels:
    """Test suite for msgraph_list_channels tool."""

    def test_msgraph_list_channels(self, mock_context, mock_channels_data):
        """Test listing channels successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_channels_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_channels(mock_context, "team-123-abc")

            assert result["success"] is True
            assert "channels" in result
            assert result["total_count"] == 2
            assert result["team_id"] == "team-123-abc"
            assert len(result["channels"]) == 2

            # Check first channel
            channel1 = result["channels"][0]
            assert channel1["id"] == "channel-general-123"
            assert channel1["display_name"] == "General"
            assert channel1["description"] == "General discussion channel"
            assert channel1["membership_type"] == "standard"

            # Check second channel
            channel2 = result["channels"][1]
            assert channel2["membership_type"] == "private"

            # Verify API call
            mock_client.get.assert_called_once_with("/teams/team-123-abc/channels")

    def test_msgraph_list_channels_empty(self, mock_context):
        """Test listing channels when team has no channels."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_channels(mock_context, "team-123-abc")

            assert result["success"] is True
            assert result["channels"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_channels_team_not_found(self, mock_context):
        """Test handling when team doesn't exist."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Team not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_channels(mock_context, "nonexistent-team")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphGetChannel:
    """Test suite for msgraph_get_channel tool."""

    def test_msgraph_get_channel(self, mock_context, mock_channel_data):
        """Test getting channel details successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_channel_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_channel(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is True
            assert "channel" in result
            assert result["team_id"] == "team-123-abc"

            channel = result["channel"]
            assert channel["id"] == "channel-general-123"
            assert channel["display_name"] == "General"
            assert channel["description"] == "General discussion channel"
            assert channel["membership_type"] == "standard"

            # Verify API call
            mock_client.get.assert_called_once_with(
                "/teams/team-123-abc/channels/channel-general-123"
            )

    def test_msgraph_get_channel_not_found(self, mock_context):
        """Test handling of channel not found error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Channel not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_channel(
                mock_context, "team-123-abc", "nonexistent-channel"
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_get_channel_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_channel(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphListChannelMessages:
    """Test suite for msgraph_list_channel_messages tool."""

    def test_msgraph_list_channel_messages(self, mock_context, mock_messages_data):
        """Test listing channel messages successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_messages_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is True
            assert "messages" in result
            assert result["total_count"] == 2
            assert result["team_id"] == "team-123-abc"
            assert result["channel_id"] == "channel-general-123"

            # Check first message
            msg1 = result["messages"][0]
            assert msg1["id"] == "msg-001"
            assert msg1["from"]["display_name"] == "John Doe"
            assert msg1["body"] == "Hello team!"
            assert msg1["body_type"] == "text"
            assert msg1["importance"] == "normal"

            # Check second message
            msg2 = result["messages"][1]
            assert msg2["id"] == "msg-002"
            assert msg2["from"]["display_name"] == "Jane Smith"
            assert msg2["body_type"] == "html"
            assert msg2["importance"] == "high"

            # Verify API call with default limit
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert (
                "/teams/team-123-abc/channels/channel-general-123/messages"
                in call_args[0][0]
            )
            assert call_args[1]["params"]["$top"] == 20

    def test_msgraph_list_channel_messages_with_limit(
        self, mock_context, mock_messages_data
    ):
        """Test listing channel messages with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_messages_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "channel-general-123", limit=50
            )

            assert result["success"] is True

            # Verify custom limit
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 50

    def test_msgraph_list_channel_messages_empty(self, mock_context):
        """Test listing messages when channel is empty."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is True
            assert result["messages"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_channel_messages_channel_not_found(self, mock_context):
        """Test handling when channel doesn't exist."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Channel not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "nonexistent-channel"
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_list_channel_messages_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphSendChannelMessage:
    """Test suite for msgraph_send_channel_message tool."""

    def test_msgraph_send_channel_message(self, mock_context, mock_sent_message_data):
        """Test sending a text message successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_sent_message_data
            mock_get_client.return_value = mock_client

            result = msgraph_send_channel_message(
                mock_context,
                "team-123-abc",
                "channel-general-123",
                "Hello everyone!",
            )

            assert result["success"] is True
            assert "message" in result
            assert result["team_id"] == "team-123-abc"
            assert result["channel_id"] == "channel-general-123"

            # Verify message response
            msg = result["message"]
            assert msg["id"] == "msg-new-001"
            assert msg["from"]["display_name"] == "Current User"

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert (
                "/teams/team-123-abc/channels/channel-general-123/messages"
                in call_args[0][0]
            )

            payload = call_args[1]["json"]
            # Content is converted through markdown_to_html, so plain text gets wrapped in <p> tags
            assert "Hello everyone!" in payload["body"]["content"]
            assert payload["body"]["contentType"] == "html"

    def test_msgraph_send_channel_message_html(
        self, mock_context, mock_sent_message_data
    ):
        """Test sending an HTML message."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_sent_message_data["body"]["contentType"] = "html"
            mock_sent_message_data["body"]["content"] = (
                "<p><b>Important:</b> Read this!</p>"
            )
            mock_client.post.return_value = mock_sent_message_data
            mock_get_client.return_value = mock_client

            result = msgraph_send_channel_message(
                mock_context,
                "team-123-abc",
                "channel-general-123",
                "<p><b>Important:</b> Read this!</p>",
                content_type="html",
            )

            assert result["success"] is True

            # Verify HTML content type in request
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["body"]["contentType"] == "html"
            # Note: markdown_to_html will escape existing HTML, so we just check it's included
            assert "Important" in payload["body"]["content"]
            assert "Read this" in payload["body"]["content"]

    def test_msgraph_send_channel_message_channel_not_found(self, mock_context):
        """Test handling when channel doesn't exist."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphNotFoundError("Channel not found")
            mock_get_client.return_value = mock_client

            result = msgraph_send_channel_message(
                mock_context,
                "team-123-abc",
                "nonexistent-channel",
                "Test message",
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_send_channel_message_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_send_channel_message(
                mock_context,
                "team-123-abc",
                "channel-general-123",
                "Test message",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_send_channel_message_throttled(self, mock_context):
        """Test handling of rate limiting error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            error = MSGraphThrottledError("Too many requests")
            error.retry_after = 30
            mock_client.post.side_effect = error
            mock_get_client.return_value = mock_client

            result = msgraph_send_channel_message(
                mock_context,
                "team-123-abc",
                "channel-general-123",
                "Test message",
            )

            assert result["success"] is False
            assert result["error_type"] == "throttled"
            assert result["retry_after"] == 30


class TestMSGraphCreateOnlineMeeting:
    """Test suite for msgraph_create_online_meeting tool."""

    def test_msgraph_create_online_meeting(self, mock_context, mock_meeting_data):
        """Test creating an online meeting successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_meeting_data
            mock_get_client.return_value = mock_client

            result = msgraph_create_online_meeting(
                mock_context,
                subject="Sprint Planning",
                start="2025-01-20T14:00:00Z",
                end="2025-01-20T15:00:00Z",
            )

            assert result["success"] is True
            assert "meeting" in result

            meeting = result["meeting"]
            assert meeting["id"] == "meeting-xyz-789"
            assert "meetup-join" in meeting["join_url"]
            assert meeting["subject"] == "Sprint Planning"
            assert meeting["start"] == "2025-01-20T14:00:00Z"
            assert meeting["end"] == "2025-01-20T15:00:00Z"

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/onlineMeetings"

            payload = call_args[1]["json"]
            assert payload["subject"] == "Sprint Planning"
            assert payload["startDateTime"] == "2025-01-20T14:00:00Z"
            assert payload["endDateTime"] == "2025-01-20T15:00:00Z"

    def test_msgraph_create_online_meeting_with_attendees(
        self, mock_context, mock_meeting_data
    ):
        """Test creating an online meeting with attendees."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_meeting_data
            mock_get_client.return_value = mock_client

            attendees = ["user1@walmart.com", "user2@walmart.com"]
            result = msgraph_create_online_meeting(
                mock_context,
                subject="Team Sync",
                start="2025-01-21T10:00:00Z",
                end="2025-01-21T10:30:00Z",
                attendees=attendees,
            )

            assert result["success"] is True

            # Verify attendees in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "participants" in payload
            assert "attendees" in payload["participants"]
            assert len(payload["participants"]["attendees"]) == 2

    def test_msgraph_create_online_meeting_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_create_online_meeting(
                mock_context,
                subject="Meeting",
                start="2025-01-20T14:00:00Z",
                end="2025-01-20T15:00:00Z",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_create_online_meeting_throttled(self, mock_context):
        """Test handling of rate limiting error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            error = MSGraphThrottledError("Too many requests")
            error.retry_after = 60
            mock_client.post.side_effect = error
            mock_get_client.return_value = mock_client

            result = msgraph_create_online_meeting(
                mock_context,
                subject="Meeting",
                start="2025-01-20T14:00:00Z",
                end="2025-01-20T15:00:00Z",
            )

            assert result["success"] is False
            assert result["error_type"] == "throttled"
            assert result["retry_after"] == 60


class TestMSGraphListChats:
    """Test suite for msgraph_list_chats tool."""

    def test_msgraph_list_chats(self, mock_context, mock_chats_data):
        """Test listing chats successfully."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_chats_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context)

            assert result["success"] is True
            assert "chats" in result
            assert result["total_count"] == 2
            assert len(result["chats"]) == 2

            # Check first chat (1:1)
            chat1 = result["chats"][0]
            assert chat1["id"] == "chat-001-abc"
            assert chat1["topic"] is None  # 1:1 chats often have no topic
            assert chat1["chat_type"] == "oneOnOne"
            assert chat1["created"] == "2025-01-10T09:00:00Z"
            assert chat1["last_updated"] == "2025-01-15T16:30:00Z"

            # Check second chat (group)
            chat2 = result["chats"][1]
            assert chat2["id"] == "chat-002-def"
            assert chat2["topic"] == "Project Discussion"
            assert chat2["chat_type"] == "group"

            # Verify API call with default params
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/chats"
            assert call_args[1]["params"]["$top"] == 20
            # Note: /me/chats doesn't support $orderby, so it's not included

    def test_msgraph_list_chats_with_limit(self, mock_context, mock_chats_data):
        """Test listing chats with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_chats_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context, limit=50)

            assert result["success"] is True

            # Verify custom limit
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 50

    def test_msgraph_list_chats_empty(self, mock_context):
        """Test listing chats when user has no chats."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context)

            assert result["success"] is True
            assert result["chats"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_chats_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context)

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_list_chats_throttled(self, mock_context):
        """Test handling of rate limiting error."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            error = MSGraphThrottledError("Rate limit exceeded")
            error.retry_after = 45
            mock_client.get.side_effect = error
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context)

            assert result["success"] is False
            assert result["error_type"] == "throttled"
            assert result["retry_after"] == 45


class TestMSGraphListChatMessages:
    """Test suite for msgraph_list_chat_messages tool.

    The tool auto-paginates internally until it reaches `beginning_date`
    or runs out of messages. Returns ONLY messages within the date range.
    """

    @staticmethod
    def _msg(msg_id: str, created: str, body: str = "hi") -> dict:
        """Build a minimal raw MS Graph message dict."""
        return {
            "id": msg_id,
            "createdDateTime": created,
            "from": {
                "user": {"id": "u1", "displayName": "Test User"}
            },
            "body": {"content": body, "contentType": "text"},
        }

    # ---------- happy path ----------

    def test_single_page_all_in_range_no_more_pages(self, mock_context):
        """All messages in range, no @odata.nextLink → reached_beginning_date."""
        page = {
            "value": [
                self._msg("m1", "2026-05-04T10:00:00Z"),
                self._msg("m2", "2026-05-03T09:00:00Z"),
            ]
        }
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-05-01"
            )

            assert result["success"] is True
            assert result["message_count"] == 2
            assert result["pages_fetched"] == 1
            assert result["reached_beginning_date"] is True
            assert result["hit_max_pages"] is False
            assert "hint" not in result
            assert result["latest_message_date"] == "2026-05-04T10:00:00Z"
            assert result["earliest_message_date"] == "2026-05-03T09:00:00Z"

            # Verify initial call uses inline query string (no params dict)
            mock_client.get.assert_called_once()
            endpoint = mock_client.get.call_args[0][0]
            assert endpoint.startswith("/me/chats/c1/messages")
            assert "$top=50" in endpoint
            assert "createdDateTime" in endpoint

    def test_stops_when_message_older_than_beginning_date(self, mock_context):
        """Page 2 contains a message older than beginning_date → stop and
        only return messages in range."""
        page1 = {
            "value": [
                self._msg("m1", "2026-05-04T10:00:00Z"),
                self._msg("m2", "2026-05-03T10:00:00Z"),
            ],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=p2"
            ),
        }
        page2 = {
            "value": [
                self._msg("m3", "2026-05-02T10:00:00Z"),
                # This one is older than beginning_date 2026-05-01
                self._msg("m4", "2026-04-30T10:00:00Z"),
                self._msg("m5", "2026-04-29T10:00:00Z"),
            ],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=p3"
            ),
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = [page1, page2]
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-05-01"
            )

            assert result["success"] is True
            # m1, m2 from page 1; m3 from page 2 (m4 stops the loop)
            assert result["message_count"] == 3
            assert [m["id"] for m in result["messages"]] == ["m1", "m2", "m3"]
            assert result["pages_fetched"] == 2
            assert result["reached_beginning_date"] is True
            assert result["hit_max_pages"] is False
            # We should NOT have fetched page 3 - the loop short-circuits
            assert mock_client.get.call_count == 2

    def test_walks_until_no_next_link(self, mock_context):
        """Walks all pages when none exceed beginning_date →
        reached_beginning_date=True (we covered everything)."""
        page1 = {
            "value": [self._msg("m1", "2026-05-04T10:00:00Z")],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=p2"
            ),
        }
        page2 = {
            "value": [self._msg("m2", "2026-05-03T10:00:00Z")]
            # No @odata.nextLink → end of chat
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = [page1, page2]
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            assert result["success"] is True
            assert result["message_count"] == 2
            assert result["pages_fetched"] == 2
            assert result["reached_beginning_date"] is True

    # ---------- max_pages safety ----------

    def test_hit_max_pages_returns_hint(self, mock_context):
        """Stops at max_pages even if more pages exist; surfaces a hint."""
        # Both pages are well within range and both have nextLinks
        page = {
            "value": [self._msg("m1", "2026-05-04T10:00:00Z")],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=more"
            ),
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-01-01",
                max_pages=2,
            )

            assert result["success"] is True
            assert result["hit_max_pages"] is True
            assert result["reached_beginning_date"] is False
            assert result["pages_fetched"] == 2
            assert mock_client.get.call_count == 2
            assert "hint" in result
            assert "max_pages" in result["hint"]

    # ---------- date parsing ----------

    def test_accepts_plain_date(self, mock_context):
        """`beginning_date='2026-04-27'` should parse and work."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-04-27"
            )

            assert result["success"] is True
            assert "2026-04-27" in result["beginning_date"]

    def test_accepts_iso_datetime_with_z_suffix(self, mock_context):
        """`beginning_date='2026-04-27T00:00:00Z'` should parse."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-04-27T00:00:00Z",
            )

            assert result["success"] is True

    def test_naive_datetime_treated_as_utc(self, mock_context):
        """Naive ISO datetime should be assumed UTC, not crash."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-04-27T12:34:56",
            )

            assert result["success"] is True
            assert "+00:00" in result["beginning_date"]

    def test_invalid_date_returns_argument_error(self, mock_context):
        """Bogus date string → success=False, error_type='invalid_argument'."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            # Should never get to the client - fail before any API call
            mock_get_client.return_value = Mock()

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="not-a-date"
            )

            assert result["success"] is False
            assert result["error_type"] == "invalid_argument"
            assert "beginning_date" in result["error"]

    # ---------- edge cases ----------

    def test_empty_chat_returns_empty_list(self, mock_context):
        """Empty chat → success, no messages, reached_beginning_date=True."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            assert result["success"] is True
            assert result["messages"] == []
            assert result["message_count"] == 0
            assert result["reached_beginning_date"] is True
            assert result["earliest_message_date"] is None
            assert result["latest_message_date"] is None

    def test_first_page_already_older_than_window(self, mock_context):
        """All messages older than beginning_date → empty result, no extra calls."""
        page = {
            "value": [
                self._msg("old1", "2025-01-01T10:00:00Z"),
                self._msg("old2", "2024-12-31T10:00:00Z"),
            ],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=more"
            ),
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            assert result["success"] is True
            assert result["messages"] == []
            assert result["reached_beginning_date"] is True
            # Crucially - we should NOT have followed nextLink
            assert mock_client.get.call_count == 1

    def test_message_without_timestamp_is_kept(self, mock_context):
        """Defensive: messages with missing createdDateTime are kept,
        not silently dropped."""
        page = {
            "value": [
                self._msg("m1", "2026-05-04T10:00:00Z"),
                {  # No createdDateTime
                    "id": "m2",
                    "from": {"user": {"id": "u1", "displayName": "x"}},
                    "body": {"content": "x", "contentType": "text"},
                },
            ]
        }
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-05-01"
            )

            assert result["success"] is True
            assert result["message_count"] == 2

    def test_strips_base_url_from_next_link(self, mock_context):
        """@odata.nextLink with absolute URL gets normalized to relative path."""
        page1 = {
            "value": [self._msg("m1", "2026-05-04T10:00:00Z")],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=abc"
            ),
        }
        page2 = {"value": []}

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = [page1, page2]
            mock_get_client.return_value = mock_client

            msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            # Second call should use relative path, not absolute URL
            second_call_endpoint = mock_client.get.call_args_list[1][0][0]
            assert second_call_endpoint == (
                "/me/chats/c1/messages?$skiptoken=abc"
            )

    # ---------- error paths ----------

    def test_chat_not_found(self, mock_context):
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("nope")
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="nope", beginning_date="2026-01-01"
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_auth_error(self, mock_context):
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_throttled(self, mock_context):
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            err = MSGraphThrottledError("slow down")
            err.retry_after = 17
            mock_client.get.side_effect = err
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            assert result["success"] is False
            assert result["error_type"] == "throttled"
            assert result["retry_after"] == 17

    # ---------- response shape contract ----------

    def test_response_shape(self, mock_context):
        """Lock down the response keys so the agent prompt stays accurate."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context, chat_id="c1", beginning_date="2026-01-01"
            )

            expected_keys = {
                "success",
                "messages",
                "message_count",
                "chat_id",
                "beginning_date",
                "ending_date",
                "earliest_message_date",
                "latest_message_date",
                "pages_fetched",
                "reached_beginning_date",
                "hit_max_pages",
            }
            assert expected_keys.issubset(result.keys())
            # Old cursor-style fields should NOT exist anymore
            assert "next_link" not in result
            assert "has_more" not in result
            # ending_date should be None when not specified
            assert result["ending_date"] is None

    # ---------- ending_date filtering ----------

    def test_ending_date_strips_newer_messages(self, mock_context):
        """Messages newer than ending_date are stripped, older ones still kept."""
        page = {
            "value": [
                self._msg("m1", "2026-05-05T10:00:00Z"),  # too new
                self._msg("m2", "2026-05-04T10:00:00Z"),  # too new
                self._msg("m3", "2026-05-03T10:00:00Z"),  # in range
                self._msg("m4", "2026-05-02T10:00:00Z"),  # in range
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-05-01",
                ending_date="2026-05-03T23:59:59Z",
            )

            assert result["success"] is True
            assert result["message_count"] == 2
            assert [m["id"] for m in result["messages"]] == ["m3", "m4"]
            # Echoes back parsed ending_date
            assert "2026-05-03" in result["ending_date"]

    def test_ending_date_inclusive_boundary(self, mock_context):
        """A message exactly at ending_date IS kept (inclusive upper bound)."""
        page = {
            "value": [
                self._msg("m1", "2026-05-05T00:00:01Z"),  # 1s after ending
                self._msg("m2", "2026-05-05T00:00:00Z"),  # exactly at ending
                self._msg("m3", "2026-05-04T00:00:00Z"),  # in range
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-05-01",
                ending_date="2026-05-05T00:00:00Z",
            )

            assert result["success"] is True
            assert [m["id"] for m in result["messages"]] == ["m2", "m3"]

    def test_ending_date_does_not_stop_pagination(self, mock_context):
        """Newer-than-ending messages skip but DON'T short-circuit the loop.

        Critical: pagination must continue past too-new messages because
        older (in-range) messages may still come."""
        page1 = {
            "value": [
                self._msg("m1", "2026-05-10T10:00:00Z"),  # too new
                self._msg("m2", "2026-05-09T10:00:00Z"),  # too new
            ],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=p2"
            ),
        }
        page2 = {
            "value": [
                self._msg("m3", "2026-05-03T10:00:00Z"),  # in range
                self._msg("m4", "2026-05-02T10:00:00Z"),  # in range
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = [page1, page2]
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-05-01",
                ending_date="2026-05-05T00:00:00Z",
            )

            assert result["success"] is True
            assert [m["id"] for m in result["messages"]] == ["m3", "m4"]
            assert mock_client.get.call_count == 2  # walked past page 1's noise

    def test_ending_date_invalid_iso(self, mock_context):
        """Invalid ending_date returns invalid_argument error."""
        result = msgraph_list_chat_messages(
            mock_context,
            chat_id="c1",
            beginning_date="2026-05-01",
            ending_date="not-a-date",
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"
        assert "ending_date" in result["error"]

    def test_ending_date_before_beginning_rejected(self, mock_context):
        """ending_date < beginning_date is a usage error."""
        result = msgraph_list_chat_messages(
            mock_context,
            chat_id="c1",
            beginning_date="2026-05-10",
            ending_date="2026-05-01",
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"
        assert "ending_date" in result["error"]
        assert "beginning_date" in result["error"]

    def test_ending_date_handles_z_suffix(self, mock_context):
        """ending_date with Z suffix parses correctly."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-04-27",
                ending_date="2026-05-05T00:00:00Z",
            )
            assert result["success"] is True
            assert "2026-05-05" in result["ending_date"]
            assert "+00:00" in result["ending_date"]

    # ---------- defensive validation (PR review feedback) ----------

    def test_max_pages_zero_rejected(self, mock_context):
        """max_pages < 1 is a usage error - reject up front, don't 0-loop."""
        result = msgraph_list_chat_messages(
            mock_context,
            chat_id="c1",
            beginning_date="2026-05-01",
            max_pages=0,
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"
        assert "max_pages" in result["error"]

    def test_max_pages_negative_rejected(self, mock_context):
        """Negative max_pages is also rejected."""
        result = msgraph_list_chat_messages(
            mock_context,
            chat_id="c1",
            beginning_date="2026-05-01",
            max_pages=-5,
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_naive_created_datetime_treated_as_utc(self, mock_context):
        """If MS Graph ever returns a naive createdDateTime, don't crash.

        Compare-as-UTC instead of raising TypeError on aware vs naive.
        """
        page = {
            "value": [
                # Naive datetime (no Z, no offset) - defensive case
                self._msg("m1", "2026-05-04T10:00:00"),
                self._msg("m2", "2026-04-30T10:00:00"),  # before beginning
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-05-01",
            )

            assert result["success"] is True
            # m1 is in range (treated as UTC), m2 stops the loop
            assert [m["id"] for m in result["messages"]] == ["m1"]
            assert result["reached_beginning_date"] is True

    def test_hit_max_pages_with_no_in_range_messages_alt_hint(
        self, mock_context
    ):
        """hit_max_pages=True + no messages returned should NOT mention 'oldest'.

        Edge case: every scanned message was newer than ending_date so we
        skipped them all but never reached beginning_date. The original
        hint referenced 'oldest message returned is None' which is misleading.
        """
        # Each page is full of too-new messages, none in range.
        too_new_page = {
            "value": [
                self._msg(f"m{i}", "2026-05-10T10:00:00Z")
                for i in range(5)
            ],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
                "?$skiptoken=more"
            ),
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Always return the too-new page so we exhaust max_pages
            mock_client.get.return_value = too_new_page
            mock_get_client.return_value = mock_client

            result = msgraph_list_chat_messages(
                mock_context,
                chat_id="c1",
                beginning_date="2026-05-01",
                ending_date="2026-05-05T00:00:00Z",
                max_pages=2,
            )

            assert result["success"] is True
            assert result["hit_max_pages"] is True
            assert result["message_count"] == 0
            assert "hint" in result
            # Should NOT use the "oldest message returned is ..." template
            assert "oldest message returned" not in result["hint"]
            # Should mention the actual issue
            assert "no in-range messages" in result["hint"]


class TestMSGraphNormalizeNextlink:
    """Test the @odata.nextLink normalization helper used for pagination.

    Lives in the walmart_specific plugin so it can be shared across tools.
    """

    def test_strips_absolute_url_prefix(self):
        from code_puppy.plugins.walmart_specific.msgraph_client import (
            normalize_nextlink,
        )

        url = (
            "https://graph.microsoft.com/v1.0/me/chats/c1/messages"
            "?$skiptoken=abc"
        )
        assert (
            normalize_nextlink(url)
            == "/me/chats/c1/messages?$skiptoken=abc"
        )

    def test_passes_through_relative_path(self):
        from code_puppy.plugins.walmart_specific.msgraph_client import (
            normalize_nextlink,
        )

        rel = "/me/messages?$skiptoken=xyz"
        assert normalize_nextlink(rel) == rel

    def test_returns_none_for_none(self):
        from code_puppy.plugins.walmart_specific.msgraph_client import (
            normalize_nextlink,
        )

        assert normalize_nextlink(None) is None

    def test_returns_none_for_empty_string(self):
        from code_puppy.plugins.walmart_specific.msgraph_client import (
            normalize_nextlink,
        )

        assert normalize_nextlink("") is None


class TestMSGraphTeamsFormatting:
    """Test suite for Teams data formatting."""


    def test_team_formatting_with_missing_fields(self, mock_context):
        """Verify team formatting handles missing fields gracefully."""
        minimal_teams = {
            "value": [
                {
                    "id": "team-minimal",
                    "displayName": "Minimal Team",
                    # Missing: description, visibility, webUrl
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = minimal_teams
            mock_get_client.return_value = mock_client

            result = msgraph_list_teams(mock_context)

            assert result["success"] is True
            team = result["teams"][0]
            assert team["id"] == "team-minimal"
            assert team["display_name"] == "Minimal Team"
            assert team["description"] is None
            assert team["visibility"] is None
            assert team["web_url"] is None

    def test_channel_formatting_with_missing_fields(self, mock_context):
        """Verify channel formatting handles missing fields gracefully."""
        minimal_channels = {
            "value": [
                {
                    "id": "channel-minimal",
                    "displayName": "Minimal Channel",
                    # Missing: description, membershipType, webUrl
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = minimal_channels
            mock_get_client.return_value = mock_client

            result = msgraph_list_channels(mock_context, "team-123-abc")

            assert result["success"] is True
            channel = result["channels"][0]
            assert channel["id"] == "channel-minimal"
            assert channel["display_name"] == "Minimal Channel"
            assert channel["description"] is None
            assert channel["membership_type"] is None

    def test_message_formatting_with_missing_from(self, mock_context):
        """Verify message formatting handles missing 'from' field."""
        messages_without_from = {
            "value": [
                {
                    "id": "msg-system",
                    "from": None,  # System messages may have null from
                    "body": {
                        "contentType": "text",
                        "content": "Someone joined the team.",
                    },
                    "createdDateTime": "2025-01-15T10:00:00Z",
                    "lastModifiedDateTime": None,
                    "messageType": "systemEventMessage",
                    "importance": "normal",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = messages_without_from
            mock_get_client.return_value = mock_client

            result = msgraph_list_channel_messages(
                mock_context, "team-123-abc", "channel-general-123"
            )

            assert result["success"] is True
            msg = result["messages"][0]
            assert msg["id"] == "msg-system"
            assert msg["from"]["user_id"] is None
            assert msg["from"]["display_name"] is None
            assert msg["message_type"] == "systemEventMessage"

    def test_chat_formatting_with_all_fields(self, mock_context):
        """Verify chat formatting includes all expected fields."""
        full_chat = {
            "value": [
                {
                    "id": "chat-full",
                    "topic": "Full Featured Chat",
                    "chatType": "meeting",
                    "createdDateTime": "2025-01-01T00:00:00Z",
                    "lastUpdatedDateTime": "2025-01-15T23:59:59Z",
                    "webUrl": "https://teams.microsoft.com/l/chat/chat-full",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = full_chat
            mock_get_client.return_value = mock_client

            result = msgraph_list_chats(mock_context)

            assert result["success"] is True
            chat = result["chats"][0]
            assert chat["id"] == "chat-full"
            assert chat["topic"] == "Full Featured Chat"
            assert chat["chat_type"] == "meeting"
            assert chat["created"] == "2025-01-01T00:00:00Z"
            assert chat["last_updated"] == "2025-01-15T23:59:59Z"
            assert "chat-full" in chat["web_url"]

    def test_meeting_formatting_with_join_info(self, mock_context):
        """Verify meeting formatting includes join information."""
        meeting_with_join_info = {
            "id": "meeting-full",
            "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/meeting-full",
            "subject": "Important Meeting",
            "startDateTime": "2025-01-25T09:00:00Z",
            "endDateTime": "2025-01-25T10:00:00Z",
            "joinInformation": {
                "content": "<html>Join meeting instructions...</html>",
            },
        }

        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = meeting_with_join_info
            mock_get_client.return_value = mock_client

            result = msgraph_create_online_meeting(
                mock_context,
                subject="Important Meeting",
                start="2025-01-25T09:00:00Z",
                end="2025-01-25T10:00:00Z",
            )

            assert result["success"] is True
            meeting = result["meeting"]
            assert meeting["join_info"] is not None
            assert "content" in meeting["join_info"]
