"""Unit tests for MS Graph meeting workflow module.

Tests the meeting management workflow tools:
- msgraph_email_meeting_attendees
- msgraph_nudge_non_responders
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from code_puppy.tools.msgraph.workflows_meeting import (
    msgraph_email_meeting_attendees,
    msgraph_nudge_non_responders,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_event_with_attendees():
    """Create mock event data with various attendee responses."""
    return {
        "id": "event-123-abc",
        "subject": "Weekly Trade Prep",
        "start": {
            "dateTime": "2025-12-20T10:00:00",
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": "2025-12-20T11:00:00",
            "timeZone": "UTC",
        },
        "location": {
            "displayName": "Conference Room B",
        },
        "organizer": {
            "emailAddress": {
                "name": "Monica Schechter",
                "address": "monica.schechter@walmart.com",
            }
        },
        "attendees": [
            {
                "emailAddress": {
                    "name": "Alice Smith",
                    "address": "alice.smith@walmart.com",
                },
                "type": "required",
                "status": {"response": "accepted"},
            },
            {
                "emailAddress": {
                    "name": "Bob Jones",
                    "address": "bob.jones@walmart.com",
                },
                "type": "required",
                "status": {"response": "tentativelyAccepted"},
            },
            {
                "emailAddress": {
                    "name": "Charlie Brown",
                    "address": "charlie.brown@walmart.com",
                },
                "type": "required",
                "status": {"response": "none"},
            },
            {
                "emailAddress": {
                    "name": "Diana Prince",
                    "address": "diana.prince@walmart.com",
                },
                "type": "optional",
                "status": {"response": "declined"},
            },
        ],
    }


class TestMsgraphEmailMeetingAttendees:
    """Tests for msgraph_email_meeting_attendees workflow."""

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_preview_mode(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test emailing attendees in preview mode (no actual send)."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please submit your slides",
            email_body="Hi, please send your deck updates by Friday.",
            preview_only=True,
        )

        assert result["success"] is True
        assert result["preview_only"] is True
        assert result["sent_count"] == 0
        # All attendees minus organizer (who isn't in attendees list anyway)
        assert len(result["recipients"]) == 4  
        assert result["email"]["subject"] == "Please submit your slides"

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_exclude_organizer(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test that organizer is excluded by default."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Test",
            email_body="Test body",
            include_organizer=False,
            preview_only=True,
        )

        assert result["success"] is True
        recipient_emails = [r["email"] for r in result["recipients"]]
        assert "monica.schechter@walmart.com" not in recipient_emails

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_include_organizer(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test including organizer in recipients."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Test",
            email_body="Test body",
            include_organizer=True,
            preview_only=True,
        )

        assert result["success"] is True
        # Organizer should not be in skipped list
        skipped_reasons = [s["reason"] for s in result.get("skipped", [])]
        assert "organizer" not in skipped_reasons

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_with_cc(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test adding CC recipients."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Test",
            email_body="Test body",
            cc_emails=["admin@walmart.com", "support@walmart.com"],
            preview_only=True,
        )

        assert result["success"] is True
        assert len(result["cc_recipients"]) == 2
        assert "admin@walmart.com" in result["cc_recipients"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_by_event_id(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test finding meeting by event ID."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = mock_event_with_attendees

        result = msgraph_email_meeting_attendees(
            mock_context,
            event_id="event-123-abc",
            email_subject="Test",
            email_body="Test body",
            preview_only=True,
        )

        assert result["success"] is True
        assert result["meeting"]["id"] == "event-123-abc"

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_meeting_not_found(
        self, mock_client_fn, mock_context
    ):
        """Test error when meeting not found."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": []}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Nonexistent Meeting",
            email_subject="Test",
            email_body="Test body",
        )

        assert result["success"] is False
        assert "No upcoming meeting found" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_missing_params(
        self, mock_client_fn, mock_context
    ):
        """Test error when neither meeting_subject nor event_id provided."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        result = msgraph_email_meeting_attendees(
            mock_context,
            email_subject="Test",
            email_body="Test body",
        )

        assert result["success"] is False
        assert "meeting_subject or event_id" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_send_mode(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test actually sending emails (preview_only=False)."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}
        mock_client.post.return_value = {}  # Successful send

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Test",
            email_body="Test body",
            preview_only=False,
        )

        assert result["success"] is True
        assert result["preview_only"] is False
        assert result["sent_count"] > 0
        # Verify sendMail was called
        assert mock_client.post.called

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_not_authenticated(
        self, mock_client_fn, mock_context
    ):
        """Test error when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Test",
            email_subject="Test",
            email_body="Test body",
        )

        assert result["success"] is False


class TestMsgraphNudgeNonResponders:
    """Tests for msgraph_nudge_non_responders workflow."""

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_preview_mode(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test nudging non-responders in preview mode."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please RSVP",
            email_body="Hi, please respond to the meeting invite.",
            preview_only=True,
        )

        assert result["success"] is True
        assert result["preview_only"] is True
        assert result["sent_count"] == 0
        # Should categorize attendees
        assert "attendee_status" in result
        assert len(result["attendee_status"]["accepted"]) == 1
        assert len(result["attendee_status"]["tentative"]) == 1
        assert len(result["attendee_status"]["no_response"]) == 1
        assert len(result["attendee_status"]["declined"]) == 1

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_includes_tentative(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test that tentative responders are included by default."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please RSVP",
            email_body="Please respond.",
            include_tentative=True,
            preview_only=True,
        )

        assert result["success"] is True
        # Should include both no_response and tentative
        assert len(result["will_send_to"]) == 2
        emails = [r["email"] for r in result["will_send_to"]]
        assert "bob.jones@walmart.com" in emails  # tentative
        assert "charlie.brown@walmart.com" in emails  # no response

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_excludes_tentative(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test excluding tentative responders."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please RSVP",
            email_body="Please respond.",
            include_tentative=False,
            preview_only=True,
        )

        assert result["success"] is True
        # Should only include no_response
        assert len(result["will_send_to"]) == 1
        assert result["will_send_to"][0]["email"] == "charlie.brown@walmart.com"

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_all_responded(self, mock_client_fn, mock_context):
        """Test when everyone has responded."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        
        # Event where everyone responded
        event = {
            "id": "event-all-responded",
            "subject": "All Responded Meeting",
            "start": {"dateTime": "2025-12-20T10:00:00"},
            "end": {"dateTime": "2025-12-20T11:00:00"},
            "organizer": {
                "emailAddress": {"address": "org@walmart.com"}
            },
            "attendees": [
                {
                    "emailAddress": {"name": "A", "address": "a@walmart.com"},
                    "status": {"response": "accepted"},
                },
                {
                    "emailAddress": {"name": "B", "address": "b@walmart.com"},
                    "status": {"response": "accepted"},
                },
            ],
        }
        mock_client.get.return_value = {"value": [event]}

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="All Responded",
            email_subject="RSVP",
            email_body="Please respond.",
            include_tentative=False,
            preview_only=True,
        )

        assert result["success"] is True
        assert len(result["will_send_to"]) == 0
        assert "Everyone has responded" in result.get("message", "")

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_send_mode(
        self, mock_client_fn, mock_context, mock_event_with_attendees
    ):
        """Test actually sending nudge emails."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_with_attendees]}
        mock_client.post.return_value = {}  # Successful send

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please RSVP",
            email_body="Please respond.",
            preview_only=False,
        )

        assert result["success"] is True
        assert result["preview_only"] is False
        assert result["sent_count"] > 0

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_meeting_not_found(self, mock_client_fn, mock_context):
        """Test error when meeting not found."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": []}

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Nonexistent",
            email_subject="RSVP",
            email_body="Please respond.",
        )

        assert result["success"] is False
        assert "No meeting found" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_missing_params(self, mock_client_fn, mock_context):
        """Test error when neither meeting_subject nor event_id provided."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        result = msgraph_nudge_non_responders(
            mock_context,
            email_subject="RSVP",
            email_body="Please respond.",
        )

        assert result["success"] is False
        assert "meeting_subject or event_id" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_not_authenticated(self, mock_client_fn, mock_context):
        """Test error when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Test",
            email_subject="RSVP",
            email_body="Please respond.",
        )

        assert result["success"] is False


class TestMeetingWorkflowToolSignatures:
    """Smoke tests to verify all meeting workflow tools have correct signatures."""

    def test_email_meeting_attendees_signature(self):
        """Verify msgraph_email_meeting_attendees has expected parameters."""
        import inspect
        sig = inspect.signature(msgraph_email_meeting_attendees)
        params = list(sig.parameters.keys())
        
        assert "ctx" in params
        assert "email_subject" in params
        assert "email_body" in params
        assert "meeting_subject" in params
        assert "event_id" in params
        assert "cc_emails" in params
        assert "include_organizer" in params
        assert "preview_only" in params

    def test_nudge_non_responders_signature(self):
        """Verify msgraph_nudge_non_responders has expected parameters."""
        import inspect
        sig = inspect.signature(msgraph_nudge_non_responders)
        params = list(sig.parameters.keys())
        
        assert "ctx" in params
        assert "email_subject" in params
        assert "email_body" in params
        assert "meeting_subject" in params
        assert "event_id" in params
        assert "include_tentative" in params
        assert "preview_only" in params

    def test_preview_only_defaults_true(self):
        """Verify preview_only defaults to True (safety first)."""
        import inspect
        
        # Check email_meeting_attendees
        sig1 = inspect.signature(msgraph_email_meeting_attendees)
        assert sig1.parameters["preview_only"].default is True
        
        # Check nudge_non_responders
        sig2 = inspect.signature(msgraph_nudge_non_responders)
        assert sig2.parameters["preview_only"].default is True
