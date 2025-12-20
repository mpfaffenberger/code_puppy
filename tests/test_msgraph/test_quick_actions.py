"""Tests for MS Graph Quick Actions."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.quick_actions import (
    msgraph_quick_acknowledge,
    msgraph_suggest_response,
    msgraph_quick_calendar_action,
    msgraph_quick_delegate,
    msgraph_proactive_suggestions,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestQuickAcknowledge:
    """Tests for msgraph_quick_acknowledge."""

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_acknowledge_preview(self, mock_client, mock_ctx):
        """Test acknowledgment preview mode."""
        mock_client.return_value.get.side_effect = [
            # Original email
            {
                "id": "msg-1",
                "subject": "Project Update",
                "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                "conversationId": "conv-1",
            },
            # Manager check - is manager
            {"mail": "boss@test.com"},
        ]

        result = msgraph_quick_acknowledge(
            mock_ctx,
            email_id="msg-1",
            acknowledgment_type="received",
            send=False,
        )

        assert result["success"] is True
        assert result["mode"] == "preview"
        assert result["sent"] is False
        assert result["relationship_detected"] == "manager"
        assert "Boss" in result["reply"]["body"]

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_acknowledge_send(self, mock_client, mock_ctx):
        """Test actually sending acknowledgment."""
        mock_client.return_value.get.side_effect = [
            {
                "id": "msg-1",
                "subject": "Question",
                "from": {"emailAddress": {"name": "Colleague", "address": "coll@test.com"}},
            },
            # Not manager
            {"mail": "other@test.com"},
            # People API
            {"value": []},
        ]
        mock_client.return_value.post.return_value = {}

        result = msgraph_quick_acknowledge(
            mock_ctx,
            email_id="msg-1",
            acknowledgment_type="reviewing",
            send=True,
        )

        assert result["success"] is True
        assert result["sent"] is True
        mock_client.return_value.post.assert_called_once()

    def test_empty_email_id(self, mock_ctx):
        """Test that empty email_id is rejected."""
        result = msgraph_quick_acknowledge(
            mock_ctx, email_id="", acknowledgment_type="received"
        )

        assert result["success"] is False
        assert "empty" in result["error"].lower()


class TestSuggestResponse:
    """Tests for msgraph_suggest_response."""

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_accept_intent(self, mock_client, mock_ctx):
        """Test response suggestion for accept intent."""
        mock_client.return_value.get.side_effect = [
            # Original email
            {
                "id": "msg-1",
                "subject": "Would you like to present?",
                "from": {"emailAddress": {"name": "Organizer", "address": "org@test.com"}},
                "body": {"content": "We'd love for you to present at the conference."},
                "importance": "normal",
            },
            # Not manager
            {"mail": "other@test.com"},
            # People API
            {"value": []},
        ]

        result = msgraph_suggest_response(
            mock_ctx, email_id="msg-1", intent="accept"
        )

        assert result["success"] is True
        assert result["mode"] == "suggestion"
        assert "accept" in result["suggested_response"]["draft"].lower() or "happy" in result["suggested_response"]["draft"].lower()

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_decline_intent_from_manager(self, mock_client, mock_ctx):
        """Test decline response for manager."""
        mock_client.return_value.get.side_effect = [
            {
                "id": "msg-1",
                "subject": "Extra project",
                "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                "body": {"content": "Can you take on this?"},
                "importance": "high",
            },
            # Is manager
            {"mail": "boss@test.com", "displayName": "Boss"},
        ]

        result = msgraph_suggest_response(
            mock_ctx, email_id="msg-1", intent="decline"
        )

        assert result["success"] is True
        assert result["relationship"]["type"] == "manager"
        assert result["relationship"]["urgency"] == "high"
        assert "formal" in result["guidance"]["relationship_adjustment"].lower() or "proactive" in result["guidance"]["relationship_adjustment"].lower()

    def test_empty_intent(self, mock_ctx):
        """Test that empty intent is rejected."""
        result = msgraph_suggest_response(mock_ctx, email_id="msg-1", intent="")

        assert result["success"] is False
        assert "empty" in result["error"].lower()


class TestQuickCalendarAction:
    """Tests for msgraph_quick_calendar_action."""

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_accept_preview(self, mock_client, mock_ctx):
        """Test accepting meeting in preview mode."""
        mock_client.return_value.get.return_value = {
            "id": "event-1",
            "subject": "Team Sync",
            "start": {"dateTime": "2024-12-18T10:00:00Z"},
            "end": {"dateTime": "2024-12-18T11:00:00Z"},
            "organizer": {"emailAddress": {"name": "Organizer", "address": "org@test.com"}},
            "responseStatus": {"response": "notResponded"},
        }

        result = msgraph_quick_calendar_action(
            mock_ctx, event_id="event-1", action="accept", send=False
        )

        assert result["success"] is True
        assert result["mode"] == "preview"
        assert result["action"]["type"] == "accept"
        assert result["sent"] is False

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_decline_with_alternative(self, mock_client, mock_ctx):
        """Test declining with alternative time."""
        mock_client.return_value.get.return_value = {
            "id": "event-1",
            "subject": "Meeting",
            "start": {"dateTime": "2024-12-18T10:00:00Z"},
            "end": {"dateTime": "2024-12-18T11:00:00Z"},
            "organizer": {"emailAddress": {"name": "Org", "address": "o@t.com"}},
            "responseStatus": {"response": "notResponded"},
        }

        result = msgraph_quick_calendar_action(
            mock_ctx,
            event_id="event-1",
            action="decline",
            propose_new_time="Tuesday at 3pm",
            send=False,
        )

        assert result["success"] is True
        assert "Tuesday at 3pm" in result["action"]["message"]

    def test_invalid_action(self, mock_ctx):
        """Test that invalid action is rejected."""
        result = msgraph_quick_calendar_action(
            mock_ctx, event_id="event-1", action="invalid"
        )

        assert result["success"] is False
        assert "accept" in result["error"]


class TestQuickDelegate:
    """Tests for msgraph_quick_delegate."""

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_delegate_preview(self, mock_client, mock_ctx):
        """Test delegation preview."""
        mock_client.return_value.get.return_value = {
            "id": "msg-1",
            "subject": "Technical Question",
            "from": {"emailAddress": {"name": "External", "address": "ext@company.com"}},
            "body": {"content": "Need help with..."},
        }

        result = msgraph_quick_delegate(
            mock_ctx,
            email_id="msg-1",
            delegate_to="expert@test.com",
            context_for_delegate="Can you help with this technical question?",
            send=False,
        )

        assert result["success"] is True
        assert result["mode"] == "preview"
        assert result["delegation"]["to"] == "expert@test.com"
        assert result["delegation"]["cc"] == "ext@company.com"

    def test_missing_context(self, mock_ctx):
        """Test that missing context is rejected."""
        result = msgraph_quick_delegate(
            mock_ctx,
            email_id="msg-1",
            delegate_to="expert@test.com",
            context_for_delegate="",
        )

        assert result["success"] is False
        assert "context" in result["error"].lower()

    def test_invalid_email(self, mock_ctx):
        """Test that invalid email is rejected."""
        result = msgraph_quick_delegate(
            mock_ctx,
            email_id="msg-1",
            delegate_to="not-an-email",
            context_for_delegate="Please help.",
        )

        assert result["success"] is False
        assert "email" in result["error"].lower()


class TestProactiveSuggestions:
    """Tests for msgraph_proactive_suggestions."""

    @patch("code_puppy.tools.msgraph.quick_actions.get_msgraph_client")
    def test_generates_suggestions(self, mock_client, mock_ctx):
        """Test that suggestions are generated."""
        mock_client.return_value.get.side_effect = [
            # Calendar events with pending response
            {
                "value": [
                    {
                        "subject": "Meeting",
                        "start": {"dateTime": "2024-12-18T10:00:00Z"},
                        "responseStatus": {"response": "notResponded"},
                        "organizer": {"emailAddress": {"name": "Org"}},
                    }
                ]
            },
            # People API
            {
                "value": [
                    {"emailAddresses": [{"address": "vip@test.com"}]}
                ]
            },
            # Unread emails
            {
                "value": [
                    {
                        "from": {"emailAddress": {"name": "VIP", "address": "vip@test.com"}},
                        "subject": "Important",
                    }
                ]
            },
            # Inbox count
            {"unreadItemCount": 100},
        ]

        result = msgraph_proactive_suggestions(mock_ctx)

        assert result["success"] is True
        assert len(result["suggestions"]) >= 1
        # Should have calendar suggestion
        categories = [s["category"] for s in result["suggestions"]]
        assert "calendar" in categories or "email" in categories
