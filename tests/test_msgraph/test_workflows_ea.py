"""Tests for Executive Assistant workflow tools.

These workflows combine multiple Graph API calls for common EA scenarios:
- 1:1 prep with manager
- Daily standup summary
- Performance summary for self-eval
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.msgraph.workflows_ea import (
    msgraph_prep_one_on_one,
    msgraph_standup_prep,
    msgraph_performance_summary,
)
from code_puppy.tools.msgraph.workflows_meeting import (
    msgraph_email_meeting_attendees,
    msgraph_nudge_non_responders,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return MagicMock()


class TestPrepOneOnOne:
    """Tests for msgraph_prep_one_on_one workflow."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_prep_with_auto_detected_manager(self, mock_client_factory, mock_context):
        """Test 1:1 prep with manager auto-detected from org chart."""
        client = MagicMock()
        mock_client_factory.return_value = client

        now = datetime.now(timezone.utc)

        # Mock manager lookup
        client.get.side_effect = [
            # /me/manager
            {
                "displayName": "Jane Manager",
                "mail": "jane.manager@walmart.com",
                "jobTitle": "Senior Manager",
            },
            # Future events (for upcoming 1:1)
            {
                "value": [
                    {
                        "id": "event-123",
                        "subject": "1:1 with Trevor",
                        "start": {"dateTime": (now + timedelta(days=2)).isoformat()},
                        "end": {
                            "dateTime": (now + timedelta(days=2, hours=1)).isoformat()
                        },
                        "attendees": [
                            {
                                "emailAddress": {
                                    "address": "jane.manager@walmart.com",
                                    "name": "Jane Manager",
                                }
                            }
                        ],
                    }
                ]
            },
            # Past events (for last 1:1)
            {
                "value": [
                    {
                        "id": "event-old",
                        "subject": "1:1 with Trevor",
                        "start": {"dateTime": (now - timedelta(days=7)).isoformat()},
                        "attendees": [
                            {
                                "emailAddress": {
                                    "address": "jane.manager@walmart.com",
                                    "name": "Jane Manager",
                                }
                            }
                        ],
                    }
                ]
            },
            # Emails with manager
            {"value": []},
            # My meetings
            {"value": []},
            # To Do lists
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        assert result["manager"]["name"] == "Jane Manager"
        assert result["manager"]["email"] == "jane.manager@walmart.com"
        assert result["next_one_on_one"] is not None
        assert result["next_one_on_one"]["subject"] == "1:1 with Trevor"
        assert "talking_points" in result

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_prep_with_explicit_manager_email(self, mock_client_factory, mock_context):
        """Test 1:1 prep with explicitly provided manager email."""
        client = MagicMock()
        mock_client_factory.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # User lookup for manager
            {
                "displayName": "Bob Director",
                "mail": "bob@walmart.com",
                "jobTitle": "Director",
            },
            # Future events
            {"value": []},
            # Past events
            {"value": []},
            # Emails
            {
                "value": [
                    {
                        "subject": "Re: Project Update",
                        "from": {"emailAddress": {"name": "Bob Director"}},
                        "receivedDateTime": now.isoformat(),
                        "bodyPreview": "Thanks for the update...",
                    }
                ]
            },
            # Meetings
            {"value": []},
            # To Do lists
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context, manager_email="bob@walmart.com")

        assert result["success"] is True
        assert result["manager"]["name"] == "Bob Director"
        assert len(result["email_threads"]) == 1
        assert result["email_threads"][0]["subject"] == "Re: Project Update"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_prep_includes_extensibility_flags(self, mock_client_factory, mock_context):
        """Test that extensibility flags are present for future Jira/Confluence."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.side_effect = [
            {"displayName": "Manager", "mail": "mgr@walmart.com"},
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context)

        assert "extensibility" in result
        assert result["extensibility"]["jira_available"] is False
        assert result["extensibility"]["confluence_available"] is False
        assert result["extensibility"]["github_available"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_prep_no_manager_detected(self, mock_client_factory, mock_context):
        """Test graceful failure when manager cannot be detected."""
        client = MagicMock()
        mock_client_factory.return_value = client

        # Manager lookup fails
        client.get.side_effect = Exception("Not found")

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is False
        assert "manager_email" in result["error"]


class TestStandupPrep:
    """Tests for msgraph_standup_prep workflow."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_standup_prep_basic(self, mock_client_factory, mock_context):
        """Test basic standup prep generation."""
        client = MagicMock()
        mock_client_factory.return_value = client

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        client.get.side_effect = [
            # Yesterday's events
            {
                "value": [
                    {
                        "subject": "Team Sync",
                        "start": {"dateTime": "2024-01-15T10:00:00"},
                        "end": {"dateTime": "2024-01-15T11:00:00"},
                    },
                    {
                        "subject": "Design Review",
                        "start": {"dateTime": "2024-01-15T14:00:00"},
                        "end": {"dateTime": "2024-01-15T15:00:00"},
                    },
                ]
            },
            # Sent emails yesterday
            {"value": [{}, {}, {}], "@odata.count": 3},
            # To Do lists for completed tasks
            {"value": []},
            # Today's events
            {
                "value": [
                    {
                        "subject": "Sprint Planning",
                        "start": {
                            "dateTime": (today_start.replace(hour=9)).isoformat()
                        },
                        "end": {"dateTime": (today_start.replace(hour=11)).isoformat()},
                        "isAllDay": False,
                    }
                ]
            },
            # Tasks due today
            {"value": []},
            # Overdue tasks (blockers)
            {"value": []},
            # Urgent emails (blockers)
            {"value": []},
            # Pending meeting responses
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert len(result["yesterday"]["meetings"]) == 2
        assert "Team Sync" in result["yesterday"]["meetings"]
        assert result["yesterday"]["emails_sent"] == 3
        assert len(result["today"]["meetings"]) == 1
        assert result["today"]["meetings"][0]["subject"] == "Sprint Planning"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_standup_prep_with_blockers(self, mock_client_factory, mock_context):
        """Test standup prep identifies blockers."""
        client = MagicMock()
        mock_client_factory.return_value = client

        now = datetime.now(timezone.utc)
        overdue_date = (now - timedelta(days=2)).isoformat()

        client.get.side_effect = [
            # Yesterday's events
            {"value": []},
            # Sent emails
            {"value": []},
            # To Do lists for completed
            {"value": []},
            # Today's events
            {"value": []},
            # Tasks due today
            {"value": []},
            # To Do lists for overdue (blockers)
            {"value": [{"id": "list-1", "displayName": "Tasks"}]},
            # Tasks in that list
            {
                "value": [
                    {
                        "title": "Finish PRD",
                        "dueDateTime": {"dateTime": overdue_date},
                    }
                ]
            },
            # Urgent emails
            {
                "value": [
                    {
                        "subject": "URGENT: Need approval",
                        "from": {"emailAddress": {"name": "VP Finance"}},
                    }
                ]
            },
            # Pending RSVPs
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert len(result["blockers"]) >= 1
        # Should have overdue task and urgent email
        blocker_text = " ".join(result["blockers"])
        assert "Overdue" in blocker_text or "Urgent" in blocker_text

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_standup_prep_extensibility_flags(self, mock_client_factory, mock_context):
        """Test extensibility flags for Jira/GitHub."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.side_effect = [
            {"value": []},  # Yesterday events
            {"value": []},  # Sent emails
            {"value": []},  # To Do lists
            {"value": []},  # Today events
            {"value": []},  # Tasks due
            {"value": []},  # Overdue lists
            {"value": []},  # Urgent emails
            {"value": []},  # Pending RSVPs
        ]

        result = msgraph_standup_prep(mock_context)

        assert "extensibility" in result
        assert result["extensibility"]["jira_available"] is False
        assert result["extensibility"]["github_available"] is False


class TestPerformanceSummary:
    """Tests for msgraph_performance_summary workflow."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_performance_summary_basic(self, mock_client_factory, mock_context):
        """Test basic performance summary generation."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.side_effect = [
            # /me
            {
                "displayName": "Trevor Dodson",
                "jobTitle": "Staff Engineer",
                "department": "Platform Engineering",
                "mail": "trevor.dodson@walmart.com",
            },
            # Calendar view (meetings)
            {
                "value": [
                    {
                        "subject": "Team Sync",
                        "start": {"dateTime": "2024-01-15T10:00:00Z"},
                        "end": {"dateTime": "2024-01-15T11:00:00Z"},
                        "organizer": {
                            "emailAddress": {
                                "address": "trevor.dodson@walmart.com",
                                "name": "Trevor",
                            }
                        },
                        "isAllDay": False,
                    },
                    {
                        "subject": "Design Review",
                        "start": {"dateTime": "2024-01-16T14:00:00Z"},
                        "end": {"dateTime": "2024-01-16T15:00:00Z"},
                        "organizer": {
                            "emailAddress": {
                                "address": "colleague@walmart.com",
                                "name": "Colleague",
                            }
                        },
                        "isAllDay": False,
                    },
                ]
            },
            # Sent emails
            {
                "value": [
                    {"toRecipients": [{"emailAddress": {"name": "Alice"}}]},
                    {"toRecipients": [{"emailAddress": {"name": "Bob"}}]},
                    {"toRecipients": [{"emailAddress": {"name": "Alice"}}]},
                ]
            },
            # To Do lists
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context, days=30)

        assert result["success"] is True
        assert result["user"]["name"] == "Trevor Dodson"
        assert result["user"]["title"] == "Staff Engineer"
        assert result["meetings"]["total"] == 2
        assert result["meetings"]["organized"] == 1  # One meeting organized by Trevor
        assert result["email"]["sent"] == 3
        assert len(result["insights"]) > 0

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_performance_summary_with_collaborators(
        self, mock_client_factory, mock_context
    ):
        """Test performance summary identifies top collaborators."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.side_effect = [
            # /me
            {"displayName": "Test User", "mail": "test@walmart.com"},
            # Meetings with various organizers
            {
                "value": [
                    {
                        "subject": "Mtg 1",
                        "start": {"dateTime": "2024-01-15T10:00:00Z"},
                        "end": {"dateTime": "2024-01-15T11:00:00Z"},
                        "organizer": {
                            "emailAddress": {
                                "address": "alice@walmart.com",
                                "name": "Alice",
                            }
                        },
                        "isAllDay": False,
                    },
                    {
                        "subject": "Mtg 2",
                        "start": {"dateTime": "2024-01-16T10:00:00Z"},
                        "end": {"dateTime": "2024-01-16T11:00:00Z"},
                        "organizer": {
                            "emailAddress": {
                                "address": "alice@walmart.com",
                                "name": "Alice",
                            }
                        },
                        "isAllDay": False,
                    },
                    {
                        "subject": "Mtg 3",
                        "start": {"dateTime": "2024-01-17T10:00:00Z"},
                        "end": {"dateTime": "2024-01-17T11:00:00Z"},
                        "organizer": {
                            "emailAddress": {
                                "address": "bob@walmart.com",
                                "name": "Bob",
                            }
                        },
                        "isAllDay": False,
                    },
                ]
            },
            # Sent emails
            {"value": []},
            # To Do lists
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        assert len(result["collaborators"]) >= 1
        # Alice should be top collaborator (2 meetings)
        assert result["collaborators"][0]["name"] == "Alice"
        assert result["collaborators"][0]["meetings"] == 2

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_performance_summary_extensibility_flags(
        self, mock_client_factory, mock_context
    ):
        """Test extensibility flags for future integrations."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": []},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context)

        assert "extensibility" in result
        assert result["extensibility"]["jira_available"] is False
        assert result["extensibility"]["confluence_available"] is False
        assert result["extensibility"]["github_available"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_performance_summary_generates_insights(
        self, mock_client_factory, mock_context
    ):
        """Test that meaningful insights are generated."""
        client = MagicMock()
        mock_client_factory.return_value = client

        # Simulate 90 days with 45 meetings (0.5/day ~ 3.5/week)
        meetings = [
            {
                "subject": f"Meeting {i}",
                "start": {"dateTime": "2024-01-15T10:00:00Z"},
                "end": {"dateTime": "2024-01-15T11:00:00Z"},
                "organizer": {
                    "emailAddress": {
                        "address": "organizer@walmart.com",
                        "name": "Organizer",
                    }
                },
                "isAllDay": False,
            }
            for i in range(45)
        ]

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": meetings},
            {"value": [{"toRecipients": [{"emailAddress": {"name": "Bob"}}]}] * 50},
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context, days=90)

        assert result["success"] is True
        assert len(result["insights"]) > 0
        # Should mention meetings per week
        insight_text = " ".join(result["insights"])
        assert "meetings" in insight_text.lower() or "week" in insight_text.lower()


class TestEmailMeetingAttendees:
    """Tests for msgraph_email_meeting_attendees workflow."""

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_preview(self, mock_client_factory, mock_context):
        """Test emailing attendees in preview mode."""
        client = MagicMock()
        mock_client_factory.return_value = client

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        meeting_start = now + timedelta(days=5)

        client.get.return_value = {
            "value": [
                {
                    "id": "event-123",
                    "subject": "Trade Prep Meeting",
                    "start": {"dateTime": meeting_start.isoformat()},
                    "end": {
                        "dateTime": (meeting_start + timedelta(hours=1)).isoformat()
                    },
                    "location": {"displayName": "Conference Room A"},
                    "organizer": {
                        "emailAddress": {
                            "address": "organizer@walmart.com",
                            "name": "Organizer",
                        }
                    },
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "presenter1@walmart.com",
                                "name": "Presenter One",
                            }
                        },
                        {
                            "emailAddress": {
                                "address": "presenter2@walmart.com",
                                "name": "Presenter Two",
                            }
                        },
                    ],
                }
            ]
        }

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Trade Prep",
            email_subject="Please submit your slides",
            email_body="Hi, please send your materials by Friday.",
            preview_only=True,
        )

        assert result["success"] is True
        assert result["meeting"]["subject"] == "Trade Prep Meeting"
        assert len(result["recipients"]) == 2
        assert result["preview_only"] is True
        assert result["sent_count"] == 0
        assert result["email"]["subject"] == "Please submit your slides"
        assert result["email"]["body"] == "Hi, please send your materials by Friday."

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_no_meeting_found(self, mock_client_factory, mock_context):
        """Test error when meeting not found."""
        client = MagicMock()
        mock_client_factory.return_value = client

        client.get.return_value = {"value": []}

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Nonexistent Meeting",
            email_subject="Test",
            email_body="Test body",
        )

        assert result["success"] is False
        assert "No upcoming meeting found" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_attendees_with_cc(self, mock_client_factory, mock_context):
        """Test emailing attendees with CC recipients."""
        client = MagicMock()
        mock_client_factory.return_value = client

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        client.get.return_value = {
            "value": [
                {
                    "id": "event-123",
                    "subject": "Strategy Leadership",
                    "start": {"dateTime": (now + timedelta(days=5)).isoformat()},
                    "end": {"dateTime": (now + timedelta(days=5, hours=2)).isoformat()},
                    "location": {},
                    "organizer": {"emailAddress": {"address": "org@walmart.com"}},
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "presenter@walmart.com",
                                "name": "Presenter",
                            }
                        }
                    ],
                }
            ]
        }

        result = msgraph_email_meeting_attendees(
            mock_context,
            meeting_subject="Strategy Leadership",
            email_subject="Reminder",
            email_body="Please submit materials.",
            cc_emails=["support@walmart.com", "admin@walmart.com"],
            preview_only=True,
        )

        assert result["success"] is True
        assert result["cc_recipients"] == ["support@walmart.com", "admin@walmart.com"]
        assert len(result["recipients"]) == 1
        assert "Preview mode" in result["message"]
        assert "(CC: 2)" in result["message"]


class TestNudgeNonResponders:
    """Tests for msgraph_nudge_non_responders workflow."""

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_with_non_responders(self, mock_client_factory, mock_context):
        """Test nudging non-responders."""
        client = MagicMock()
        mock_client_factory.return_value = client

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        client.get.return_value = {
            "value": [
                {
                    "id": "event-456",
                    "subject": "Team Standup",
                    "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                    "end": {
                        "dateTime": (now + timedelta(days=1, minutes=30)).isoformat()
                    },
                    "organizer": {"emailAddress": {"address": "me@walmart.com"}},
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "alice@walmart.com",
                                "name": "Alice",
                            },
                            "status": {"response": "accepted"},
                        },
                        {
                            "emailAddress": {
                                "address": "bob@walmart.com",
                                "name": "Bob",
                            },
                            "status": {"response": "none"},
                        },
                        {
                            "emailAddress": {
                                "address": "charlie@walmart.com",
                                "name": "Charlie",
                            },
                            "status": {"response": "tentativelyAccepted"},
                        },
                    ],
                }
            ]
        }

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Standup",
            email_subject="Please RSVP: Team Standup",
            email_body="Hi, please respond to the calendar invite.",
            preview_only=True,
        )

        assert result["success"] is True
        assert len(result["attendee_status"]["accepted"]) == 1
        assert len(result["attendee_status"]["no_response"]) == 1
        assert len(result["attendee_status"]["tentative"]) == 1
        # Should send to no_response + tentative = 2 people
        assert len(result["will_send_to"]) == 2
        assert result["email"]["subject"] == "Please RSVP: Team Standup"

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_all_responded(self, mock_client_factory, mock_context):
        """Test when everyone has responded - no nudges needed."""
        client = MagicMock()
        mock_client_factory.return_value = client

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        client.get.return_value = {
            "value": [
                {
                    "id": "event-789",
                    "subject": "Design Review",
                    "start": {"dateTime": (now + timedelta(days=2)).isoformat()},
                    "end": {"dateTime": (now + timedelta(days=2, hours=1)).isoformat()},
                    "organizer": {"emailAddress": {"address": "me@walmart.com"}},
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "alice@walmart.com",
                                "name": "Alice",
                            },
                            "status": {"response": "accepted"},
                        },
                        {
                            "emailAddress": {
                                "address": "bob@walmart.com",
                                "name": "Bob",
                            },
                            "status": {"response": "accepted"},
                        },
                    ],
                }
            ]
        }

        result = msgraph_nudge_non_responders(
            mock_context,
            meeting_subject="Design Review",
            email_subject="Please RSVP",
            email_body="Please respond.",
            include_tentative=False,
            preview_only=True,
        )

        assert result["success"] is True
        assert len(result["will_send_to"]) == 0
        assert "Everyone has responded" in result.get("message", "")
