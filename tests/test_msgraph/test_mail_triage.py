"""Tests for mail triage and inbox zero workflows."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.mail_triage import (
    msgraph_analyze_inbox,
    msgraph_extract_email_actions,
    msgraph_bulk_triage,
    msgraph_inbox_zero_status,
)


@pytest.fixture
def mock_ctx():
    """Create a mock context."""
    return MagicMock()


@pytest.fixture
def sample_emails():
    """Sample email data for testing."""
    return [
        {
            "id": "email-1",
            "subject": "Action Required: Please review the proposal",
            "from": {"emailAddress": {"address": "boss@walmart.com", "name": "Boss"}},
            "receivedDateTime": "2024-12-17T10:00:00Z",
            "importance": "high",
            "isRead": False,
            "bodyPreview": "Please review this by end of day.",
            "hasAttachments": True,
            "conversationId": "conv-1",
        },
        {
            "id": "email-2",
            "subject": "Newsletter: Weekly Update",
            "from": {"emailAddress": {"address": "noreply@newsletter.com", "name": "Newsletter"}},
            "receivedDateTime": "2024-12-17T09:00:00Z",
            "importance": "normal",
            "isRead": False,
            "bodyPreview": "Here is your weekly update...",
            "hasAttachments": False,
            "conversationId": "conv-2",
        },
        {
            "id": "email-3",
            "subject": "Question about project timeline?",
            "from": {"emailAddress": {"address": "colleague@walmart.com", "name": "Colleague"}},
            "receivedDateTime": "2024-12-17T08:00:00Z",
            "importance": "normal",
            "isRead": False,
            "bodyPreview": "Can you let me know when you expect to finish?",
            "hasAttachments": False,
            "conversationId": "conv-3",
        },
    ]


class TestAnalyzeInbox:
    """Tests for msgraph_analyze_inbox."""

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_success(self, mock_client, mock_ctx, sample_emails):
        """Test analyzing inbox successfully."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx, days_back=7, unread_only=True)

        assert result["success"] is True
        assert result["total_count"] == 3
        assert "by_sender_domain" in result
        assert "action_items" in result
        assert "notifications" in result

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_finds_action_items(self, mock_client, mock_ctx, sample_emails):
        """Test that action items are identified."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        # Email 1 has "Action Required" and "by end of day"
        assert len(result["action_items"]) >= 1
        action_subjects = [a["subject"] for a in result["action_items"]]
        assert any("Action Required" in s for s in action_subjects)

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_finds_notifications(self, mock_client, mock_ctx, sample_emails):
        """Test that notification emails are identified."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        # Email 2 is from noreply@
        assert len(result["notifications"]) >= 1

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_finds_questions(self, mock_client, mock_ctx, sample_emails):
        """Test that questions needing response are identified."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        # Email 3 has a question mark in subject
        assert len(result["needs_response"]) >= 1

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_groups_by_domain(self, mock_client, mock_ctx, sample_emails):
        """Test that emails are grouped by sender domain."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        assert "walmart.com" in result["by_sender_domain"]
        assert result["by_sender_domain"]["walmart.com"] == 2

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_top_senders(self, mock_client, mock_ctx, sample_emails):
        """Test that top senders are identified."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        assert len(result["top_senders"]) > 0
        assert all("name" in s and "count" in s for s in result["top_senders"])

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_not_authenticated(self, mock_client, mock_ctx):
        """Test analyzing when not authenticated."""
        mock_client.return_value = None

        result = msgraph_analyze_inbox(mock_ctx)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_analyze_inbox_summary_stats(self, mock_client, mock_ctx, sample_emails):
        """Test that summary stats are calculated."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_analyze_inbox(mock_ctx)

        assert "summary" in result
        assert "high_priority" in result["summary"]
        assert "action_items" in result["summary"]


class TestExtractEmailActions:
    """Tests for msgraph_extract_email_actions."""

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_extract_actions_success(self, mock_client, mock_ctx):
        """Test extracting actions from an email."""
        mock_client.return_value.get.side_effect = [
            # Get email
            {
                "id": "email-1",
                "subject": "Please review proposal",
                "from": {"emailAddress": {"address": "boss@walmart.com", "name": "Boss"}},
                "body": {"content": "Please review this by Friday."},
                "importance": "high",
                "receivedDateTime": "2024-12-17T10:00:00Z",
            },
            # Get todo lists
            {"value": []},
        ]
        mock_client.return_value.post.side_effect = [
            # Create todo list
            {"id": "list-1", "displayName": "Email Follow-ups"},
            # Create task
            {"id": "task-1", "title": "Review and respond"},
        ]

        result = msgraph_extract_email_actions(
            mock_ctx, email_id="email-1", create_todo=True
        )

        assert result["success"] is True
        assert len(result["actions"]) > 0
        assert len(result["tasks_created"]) > 0

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_extract_actions_no_todo(self, mock_client, mock_ctx):
        """Test extracting actions without creating todos."""
        mock_client.return_value.get.return_value = {
            "id": "email-1",
            "subject": "FYI: Update",
            "from": {"emailAddress": {"address": "info@walmart.com", "name": "Info"}},
            "body": {"content": "Just an update."},
            "importance": "normal",
            "receivedDateTime": "2024-12-17T10:00:00Z",
        }

        result = msgraph_extract_email_actions(
            mock_ctx, email_id="email-1", create_todo=False
        )

        assert result["success"] is True
        assert result["tasks_created"] == []

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_extract_actions_uses_existing_list(self, mock_client, mock_ctx):
        """Test that existing todo list is used if available."""
        mock_client.return_value.get.side_effect = [
            # Get email
            {
                "id": "email-1",
                "subject": "Task",
                "from": {"emailAddress": {"address": "x@y.com", "name": "X"}},
                "body": {"content": "Do this."},
                "importance": "normal",
                "receivedDateTime": "2024-12-17T10:00:00Z",
            },
            # Get todo lists - existing list found
            {"value": [{"id": "existing-list", "displayName": "Email Follow-ups"}]},
        ]
        mock_client.return_value.post.return_value = {"id": "task-1", "title": "Task"}

        result = msgraph_extract_email_actions(
            mock_ctx, email_id="email-1", create_todo=True
        )

        assert result["success"] is True
        # Should not have created a new list
        assert mock_client.return_value.post.call_count == 1  # Only task creation


class TestBulkTriage:
    """Tests for msgraph_bulk_triage."""

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_preview(self, mock_client, mock_ctx, sample_emails):
        """Test bulk triage in preview mode."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_bulk_triage(
            mock_ctx,
            action="archive",
            from_sender="newsletter",
            preview_only=True,
        )

        assert result["success"] is True
        assert result["preview_only"] is True
        assert "Would archive" in result["message"]

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_execute_archive(self, mock_client, mock_ctx, sample_emails):
        """Test executing bulk archive."""
        mock_client.return_value.get.side_effect = [
            {"value": sample_emails[:1]},  # List emails
            {"id": "archive-folder"},  # Get archive folder
        ]
        mock_client.return_value.post.return_value = {}  # Move

        result = msgraph_bulk_triage(
            mock_ctx,
            action="archive",
            email_ids=["email-1"],
            preview_only=False,
        )

        assert result["success"] is True
        assert result["preview_only"] is False
        assert result["processed"] > 0

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_delete(self, mock_client, mock_ctx, sample_emails):
        """Test bulk delete."""
        mock_client.return_value.get.return_value = {"value": sample_emails[:1]}
        mock_client.return_value.delete.return_value = None

        result = msgraph_bulk_triage(
            mock_ctx,
            action="delete",
            email_ids=["email-1"],
            preview_only=False,
        )

        assert result["success"] is True
        assert result["processed"] == 1

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_mark_read(self, mock_client, mock_ctx, sample_emails):
        """Test bulk mark as read."""
        mock_client.return_value.get.return_value = {"value": sample_emails[:1]}
        mock_client.return_value.patch.return_value = {}

        result = msgraph_bulk_triage(
            mock_ctx,
            action="mark_read",
            email_ids=["email-1"],
            preview_only=False,
        )

        assert result["success"] is True
        mock_client.return_value.patch.assert_called()

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_move_requires_folder(self, mock_client, mock_ctx, sample_emails):
        """Test that move action requires target folder."""
        mock_client.return_value.get.return_value = {"value": sample_emails[:1]}

        result = msgraph_bulk_triage(
            mock_ctx,
            action="move",
            email_ids=["email-1"],
            preview_only=False,
        )

        assert result["success"] is False
        assert "target_folder" in result["error"]

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_bulk_triage_filter_by_subject(self, mock_client, mock_ctx, sample_emails):
        """Test filtering by subject."""
        mock_client.return_value.get.return_value = {"value": sample_emails}

        result = msgraph_bulk_triage(
            mock_ctx,
            action="archive",
            subject_contains="newsletter",
            preview_only=True,
        )

        assert result["success"] is True
        # Should only match email-2
        assert result["count"] == 1


class TestInboxZeroStatus:
    """Tests for msgraph_inbox_zero_status."""

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_inbox_zero_achieved(self, mock_client, mock_ctx):
        """Test when inbox zero is achieved."""
        mock_client.return_value.get.side_effect = [
            # Inbox folder
            {"id": "inbox", "unreadItemCount": 0, "totalItemCount": 50},
            # Focused inbox
            {"value": []},
            # Other inbox
            {"value": []},
            # Oldest unread
            {"value": []},
        ]

        result = msgraph_inbox_zero_status(mock_ctx)

        assert result["success"] is True
        assert result["at_inbox_zero"] is True
        assert result["score"] == 100
        assert result["unread"] == 0

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_inbox_with_unread(self, mock_client, mock_ctx):
        """Test inbox status with unread emails."""
        mock_client.return_value.get.side_effect = [
            # Inbox folder
            {"id": "inbox", "unreadItemCount": 25, "totalItemCount": 100},
            # Focused inbox
            {"value": [{}, {}, {}]},  # 3 focused
            # Other inbox
            {"value": list(range(20))},  # 20 other
            # Oldest unread
            {
                "value": [
                    {
                        "receivedDateTime": "2024-12-10T10:00:00Z",
                        "subject": "Old Email",
                        "from": {"emailAddress": {"name": "Sender"}},
                    }
                ]
            },
        ]

        result = msgraph_inbox_zero_status(mock_ctx)

        assert result["success"] is True
        assert result["at_inbox_zero"] is False
        assert result["score"] == 75  # 100 - 25
        assert result["unread"] == 25
        assert result["oldest_unread"] is not None
        assert len(result["recommendations"]) > 0

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_inbox_status_not_authenticated(self, mock_client, mock_ctx):
        """Test status when not authenticated."""
        mock_client.return_value = None

        result = msgraph_inbox_zero_status(mock_ctx)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_triage.get_msgraph_client")
    def test_inbox_status_recommendations(self, mock_client, mock_ctx):
        """Test that recommendations are generated."""
        mock_client.return_value.get.side_effect = [
            # Heavy inbox
            {"id": "inbox", "unreadItemCount": 75, "totalItemCount": 200},
            # More other than focused
            {"value": [{}, {}]},  # 2 focused
            {"value": list(range(50))},  # 50 other
            # Old unread
            {
                "value": [
                    {
                        "receivedDateTime": "2024-11-01T10:00:00Z",
                        "subject": "Very Old",
                        "from": {"emailAddress": {"name": "Old Sender"}},
                    }
                ]
            },
        ]

        result = msgraph_inbox_zero_status(mock_ctx)

        assert result["success"] is True
        # Should have multiple recommendations
        assert len(result["recommendations"]) >= 2
