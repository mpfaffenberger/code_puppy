"""Comprehensive tests for workflows_ea.py to achieve 100% coverage.

These tests target specific branches and error paths that aren't covered
by the basic functional tests.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.msgraph.workflows_ea import (
    msgraph_prep_one_on_one,
    msgraph_standup_prep,
    msgraph_performance_summary,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return MagicMock()


# =============================================================================
# PREP ONE-ON-ONE COVERAGE TESTS
# =============================================================================


class TestPrepOneOnOneCoverage:
    """Coverage-focused tests for msgraph_prep_one_on_one."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when client returns None (not authenticated)."""
        mock_client_fn.return_value = None

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is False
        assert "error" in result

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_manager_lookup_fails_with_provided_email(
        self, mock_client_fn, mock_context
    ):
        """Test when manager lookup fails but email was provided."""
        client = MagicMock()
        mock_client_fn.return_value = client

        # First call: manager user lookup fails, then subsequent calls succeed
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # Manager lookup
                raise Exception("User not found")
            return {"value": []}  # Empty for other calls

        client.get.side_effect = side_effect

        result = msgraph_prep_one_on_one(
            mock_context, manager_email="unknown@walmart.com"
        )

        assert result["success"] is True
        # Manager info should be minimal
        assert result["manager"]["email"] == "unknown@walmart.com"
        assert result["manager"]["name"] == "Unknown"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_future_events_search_fails(self, mock_client_fn, mock_context):
        """Test graceful handling when future events search fails."""
        client = MagicMock()
        mock_client_fn.return_value = client

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me/manager" in path:
                return {"displayName": "Manager", "mail": "mgr@walmart.com"}
            if "calendarView" in path and call_count[0] == 2:
                raise Exception("Calendar API error")
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        # Should still complete without next_one_on_one
        assert result["next_one_on_one"] is None

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_one_on_one_detection_by_subject(self, mock_client_fn, mock_context):
        """Test 1:1 detection when subject contains '1-1'."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # Manager lookup
            {"displayName": "Manager", "mail": "mgr@walmart.com", "jobTitle": "VP"},
            # Future events with 1-1 in subject and many attendees
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Weekly 1-1 Sync",
                        "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                        "end": {
                            "dateTime": (now + timedelta(days=1, hours=1)).isoformat()
                        },
                        "attendees": [
                            {"emailAddress": {"address": "mgr@walmart.com"}},
                            {"emailAddress": {"address": "other1@walmart.com"}},
                            {"emailAddress": {"address": "other2@walmart.com"}},
                        ],
                    }
                ]
            },
            # Past events
            {"value": []},
            # Emails
            {"value": []},
            # Meetings
            {"value": []},
            # To Do
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        assert result["next_one_on_one"] is not None
        assert "1-1" in result["next_one_on_one"]["subject"]

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_past_one_on_one_found(self, mock_client_fn, mock_context):
        """Test finding the last 1:1 meeting."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # Manager lookup
            {"displayName": "Manager", "mail": "mgr@walmart.com"},
            # Future events
            {"value": []},
            # Past events with 1:1
            {
                "value": [
                    {
                        "id": "past-event",
                        "subject": "1:1 with Direct",
                        "start": {"dateTime": (now - timedelta(days=5)).isoformat()},
                        "end": {"dateTime": (now - timedelta(days=5)).isoformat()},
                        "attendees": [
                            {"emailAddress": {"address": "mgr@walmart.com"}},
                        ],
                    }
                ]
            },
            # Emails
            {"value": []},
            # Meetings - use last 1:1 date as since_date
            {"value": []},
            # To Do
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        assert result["last_one_on_one"] is not None
        assert result["last_one_on_one"]["subject"] == "1:1 with Direct"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_email_fetch_fails(self, mock_client_fn, mock_context):
        """Test graceful handling when email fetch fails."""
        client = MagicMock()
        mock_client_fn.return_value = client

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me/manager" in path:
                return {"displayName": "Manager", "mail": "mgr@walmart.com"}
            if "/me/messages" in path:
                raise Exception("Mail API error")
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        # Email threads should be empty
        assert result["email_threads"] == []

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_todo_with_completed_tasks(self, mock_client_fn, mock_context):
        """Test collecting completed tasks from To Do."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            {"displayName": "Manager", "mail": "mgr@walmart.com"},
            {"value": []},  # Future events
            {"value": []},  # Past events
            {"value": []},  # Emails
            {"value": []},  # My meetings
            # To Do lists
            {"value": [{"id": "list-1"}, {"id": "list-2"}]},
            # Tasks in list-1
            {
                "value": [
                    {
                        "title": "Task 1",
                        "completedDateTime": {"dateTime": now.isoformat()},
                    },
                    {
                        "title": "Task 2",
                        "completedDateTime": {"dateTime": now.isoformat()},
                    },
                ]
            },
            # Tasks in list-2
            {
                "value": [
                    {
                        "title": "Task 3",
                        "completedDateTime": {"dateTime": now.isoformat()},
                    },
                ]
            },
        ]

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is True
        assert len(result["completed_tasks"]) == 3

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_talking_points_with_data(self, mock_client_fn, mock_context):
        """Test talking points generation with meetings and emails."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            {"displayName": "Manager", "mail": "mgr@walmart.com"},
            {"value": []},  # Future
            {"value": []},  # Past
            # Emails with manager
            {
                "value": [
                    {
                        "subject": "Thread 1",
                        "from": {"emailAddress": {"name": "Manager"}},
                        "receivedDateTime": now.isoformat(),
                        "bodyPreview": "Preview 1",
                    },
                    {
                        "subject": "Thread 2",
                        "from": {"emailAddress": {"name": "Manager"}},
                        "receivedDateTime": now.isoformat(),
                        "bodyPreview": "Preview 2",
                    },
                ]
            },
            # My meetings
            {
                "value": [
                    {
                        "subject": "Team Sync",
                        "start": {"dateTime": now.isoformat()},
                        "organizer": {"emailAddress": {"name": "Org 1"}},
                    },
                    {
                        "subject": "Design Review",
                        "start": {"dateTime": now.isoformat()},
                        "organizer": {"emailAddress": {"name": "Org 2"}},
                    },
                ]
            },
            # To Do with completed tasks
            {"value": [{"id": "list-1"}]},
            {
                "value": [
                    {
                        "title": "Done task",
                        "completedDateTime": {"dateTime": now.isoformat()},
                    }
                ]
            },
        ]

        result = msgraph_prep_one_on_one(mock_context, include_talking_points=True)

        assert result["success"] is True
        assert len(result["talking_points"]) > 4  # Base points + dynamic ones
        # Check for dynamic talking points
        points_text = " ".join(result["talking_points"])
        assert "Completed" in points_text or "✅" in points_text
        assert "meetings" in points_text.lower() or "📅" in points_text
        assert "email" in points_text.lower() or "📧" in points_text

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_talking_points_disabled(self, mock_client_fn, mock_context):
        """Test disabling talking points generation."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.side_effect = [
            {"displayName": "Manager", "mail": "mgr@walmart.com"},
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_prep_one_on_one(mock_context, include_talking_points=False)

        assert result["success"] is True
        assert result["talking_points"] == []

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_general_exception_handling(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("Connection error")

        result = msgraph_prep_one_on_one(mock_context)

        assert result["success"] is False


# =============================================================================
# STANDUP PREP COVERAGE TESTS
# =============================================================================


class TestStandupPrepCoverage:
    """Coverage-focused tests for msgraph_standup_prep."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_include_yesterday_false(self, mock_client_fn, mock_context):
        """Test standup without yesterday's data."""
        client = MagicMock()
        mock_client_fn.return_value = client

        # Only today's data should be fetched
        client.get.side_effect = [
            # Today's events
            {
                "value": [
                    {
                        "subject": "Meeting",
                        "start": {"dateTime": "2025-01-15T09:00:00Z"},
                        "end": {"dateTime": "2025-01-15T10:00:00Z"},
                        "isAllDay": False,
                    }
                ]
            },
            # Tasks due today
            {"value": []},
            # Overdue tasks
            {"value": []},
            # Urgent emails
            {"value": []},
            # Pending RSVPs
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context, include_yesterday=False)

        assert result["success"] is True
        # Yesterday data should be empty/default
        assert result["yesterday"]["meetings"] == []
        assert result["yesterday"]["emails_sent"] == 0

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_yesterday_tasks_completed_with_dates(self, mock_client_fn, mock_context):
        """Test parsing completed tasks with date checking."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today_start - timedelta(hours=12)  # Noon yesterday

        client.get.side_effect = [
            # Yesterday events
            {"value": []},
            # Sent emails
            {"value": [], "@odata.count": 5},
            # To Do lists for completed tasks
            {"value": [{"id": "list-1"}]},
            # Completed tasks with various dates
            {
                "value": [
                    {
                        "title": "Yesterday task",
                        "completedDateTime": {"dateTime": yesterday.isoformat()},
                    },
                    {
                        "title": "Old task",
                        "completedDateTime": {
                            "dateTime": (yesterday - timedelta(days=10)).isoformat()
                        },
                    },
                    {
                        "title": "Invalid date",
                        "completedDateTime": {"dateTime": "invalid-date"},
                    },
                ]
            },
            # Today's events
            {"value": []},
            # Tasks due today
            {"value": []},
            # Overdue tasks
            {"value": []},
            # Urgent emails
            {"value": []},
            # Pending RSVPs
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        # Only yesterday's task should be counted
        assert len(result["yesterday"]["tasks_completed"]) == 1
        assert "Yesterday task" in result["yesterday"]["tasks_completed"]

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_today_meeting_duration_calculation(self, mock_client_fn, mock_context):
        """Test focus time calculation based on meeting durations."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 4 hours of meetings
        client.get.side_effect = [
            {"value": []},  # Yesterday events
            {"value": []},  # Sent emails
            {"value": []},  # To Do for completed
            # Today's events - 4 hours of meetings
            {
                "value": [
                    {
                        "subject": "Meeting 1",
                        "start": {
                            "dateTime": (today_start.replace(hour=9)).isoformat()
                        },
                        "end": {"dateTime": (today_start.replace(hour=11)).isoformat()},
                        "isAllDay": False,
                    },
                    {
                        "subject": "Meeting 2",
                        "start": {
                            "dateTime": (today_start.replace(hour=14)).isoformat()
                        },
                        "end": {"dateTime": (today_start.replace(hour=16)).isoformat()},
                        "isAllDay": False,
                    },
                    # All-day event should be skipped
                    {
                        "subject": "All Day Event",
                        "start": {"dateTime": today_start.isoformat()},
                        "end": {
                            "dateTime": (today_start + timedelta(days=1)).isoformat()
                        },
                        "isAllDay": True,
                    },
                ]
            },
            # Tasks due today
            {"value": []},
            # Overdue
            {"value": []},
            # Urgent
            {"value": []},
            # Pending
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        # 8 hours - 4 hours = 4 hours focus time
        assert result["today"]["focus_time_hours"] == 4.0
        # Should have 2 meetings (all-day excluded)
        assert len(result["today"]["meetings"]) == 2

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_tasks_due_today(self, mock_client_fn, mock_context):
        """Test finding tasks due today."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)

        client.get.side_effect = [
            {"value": []},  # Yesterday events
            {"value": []},  # Sent emails
            {"value": []},  # Completed tasks
            {"value": []},  # Today events
            # Tasks due today
            {"value": [{"id": "list-1"}]},
            {
                "value": [
                    {
                        "title": "Due today",
                        "dueDateTime": {"dateTime": today.isoformat()},
                        "importance": "high",
                    },
                    {
                        "title": "Due tomorrow",
                        "dueDateTime": {
                            "dateTime": (today + timedelta(days=1)).isoformat()
                        },
                    },
                    {"title": "Invalid due", "dueDateTime": {"dateTime": "not-a-date"}},
                ]
            },
            # Overdue
            {"value": []},
            # Urgent
            {"value": []},
            # Pending
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert len(result["today"]["tasks_due"]) == 1
        assert result["today"]["tasks_due"][0]["title"] == "Due today"
        assert result["today"]["tasks_due"][0]["importance"] == "high"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_blockers_overdue_tasks(self, mock_client_fn, mock_context):
        """Test detecting overdue tasks as blockers."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        overdue = (now - timedelta(days=3)).isoformat()

        client.get.side_effect = [
            {"value": []},  # Yesterday
            {"value": []},  # Sent
            {"value": []},  # Completed
            {"value": []},  # Today
            {"value": []},  # Due today
            # Overdue - list lookup
            {"value": [{"id": "list-1"}]},
            # Tasks in list
            {
                "value": [
                    {"title": "Overdue task", "dueDateTime": {"dateTime": overdue}},
                    {"title": "No due date"},  # No dueDateTime
                ]
            },
            # Urgent emails
            {"value": []},
            # Pending RSVPs
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert len(result["blockers"]) >= 1
        assert any("Overdue" in b for b in result["blockers"])

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_blockers_pending_rsvps(self, mock_client_fn, mock_context):
        """Test detecting pending meeting RSVPs as blockers."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            {"value": []},  # Yesterday
            {"value": []},  # Sent
            {"value": []},  # Completed
            {"value": []},  # Today
            {"value": []},  # Due
            {"value": []},  # Overdue lists
            {"value": []},  # Urgent
            # Pending RSVPs
            {
                "value": [
                    {
                        "subject": "Important Meeting",
                        "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                    },
                ]
            },
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert any("RSVP" in b for b in result["blockers"])

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_yesterday_summary_generation(self, mock_client_fn, mock_context):
        """Test summary generation with various data."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.side_effect = [
            # Yesterday events
            {"value": [{"subject": "M1"}, {"subject": "M2"}]},
            # Sent emails
            {"value": [{}], "@odata.count": 10},
            # Completed tasks
            {"value": [{"id": "l1"}]},
            {
                "value": [
                    {
                        "title": "T1",
                        "completedDateTime": {
                            "dateTime": datetime.now(timezone.utc).isoformat()
                        },
                    }
                ]
            },
            # Today
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        summary = result["yesterday"]["summary"]
        assert "2 meetings" in summary
        assert "10 emails" in summary

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_yesterday_summary_light_day(self, mock_client_fn, mock_context):
        """Test summary when no activity."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.side_effect = [
            {"value": []},  # Yesterday events
            {"value": []},  # Sent
            {"value": []},  # Completed
            {"value": []},  # Today
            {"value": []},
            {"value": []},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is True
        assert result["yesterday"]["summary"] == "Light day"

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_general_exception(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("Network error")

        result = msgraph_standup_prep(mock_context)

        assert result["success"] is False


# =============================================================================
# PERFORMANCE SUMMARY COVERAGE TESTS
# =============================================================================


class TestPerformanceSummaryCoverage:
    """Coverage-focused tests for msgraph_performance_summary."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_include_metrics_false(self, mock_client_fn, mock_context):
        """Test without metrics (summary only)."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.return_value = {
            "displayName": "Test User",
            "jobTitle": "Engineer",
            "department": "Platform",
            "mail": "test@walmart.com",
        }

        result = msgraph_performance_summary(mock_context, include_metrics=False)

        assert result["success"] is True
        # Metrics should be zeros
        assert result["meetings"]["total"] == 0
        assert result["email"]["sent"] == 0
        assert result["tasks"]["completed"] == 0

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_pagination_handling(self, mock_client_fn, mock_context):
        """Test handling of paginated calendar results."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        # Create meetings
        meetings_page1 = [
            {
                "subject": f"Meeting {i}",
                "start": {"dateTime": (now - timedelta(days=i)).isoformat()},
                "end": {
                    "dateTime": (
                        now - timedelta(days=i) + timedelta(hours=1)
                    ).isoformat()
                },
                "organizer": {
                    "emailAddress": {"address": "org@walmart.com", "name": "Organizer"}
                },
                "isAllDay": False,
            }
            for i in range(50)
        ]

        meetings_page2 = [
            {
                "subject": f"Meeting {i + 50}",
                "start": {"dateTime": (now - timedelta(days=i + 50)).isoformat()},
                "end": {
                    "dateTime": (
                        now - timedelta(days=i + 50) + timedelta(hours=1)
                    ).isoformat()
                },
                "organizer": {
                    "emailAddress": {"address": "org@walmart.com", "name": "Organizer"}
                },
                "isAllDay": False,
            }
            for i in range(20)
        ]

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me" == path:
                return {"displayName": "User", "mail": "user@walmart.com"}
            if "calendarView" in path:
                if call_count[0] == 2:
                    return {
                        "value": meetings_page1,
                        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?next",
                    }
                else:
                    return {"value": meetings_page2}
            if "sentItems" in path:
                return {"value": []}
            if "todo" in path:
                return {"value": []}
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_performance_summary(mock_context, days=90)

        assert result["success"] is True
        assert result["meetings"]["total"] == 70  # 50 + 20

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_meeting_organized_percentage_insight(self, mock_client_fn, mock_context):
        """Test insight for high meeting organization percentage."""
        client = MagicMock()
        mock_client_fn.return_value = client

        my_email = "me@walmart.com"

        # Create meetings where I organized 50%
        meetings = [
            {
                "subject": "I organized 1",
                "start": {"dateTime": "2025-01-15T10:00:00Z"},
                "end": {"dateTime": "2025-01-15T11:00:00Z"},
                "organizer": {"emailAddress": {"address": my_email, "name": "Me"}},
                "isAllDay": False,
            },
            {
                "subject": "I organized 2",
                "start": {"dateTime": "2025-01-16T10:00:00Z"},
                "end": {"dateTime": "2025-01-16T11:00:00Z"},
                "organizer": {"emailAddress": {"address": my_email, "name": "Me"}},
                "isAllDay": False,
            },
            {
                "subject": "Other organized",
                "start": {"dateTime": "2025-01-17T10:00:00Z"},
                "end": {"dateTime": "2025-01-17T11:00:00Z"},
                "organizer": {
                    "emailAddress": {"address": "other@walmart.com", "name": "Other"}
                },
                "isAllDay": False,
            },
        ]

        client.get.side_effect = [
            {
                "displayName": "Me",
                "mail": my_email,
                "jobTitle": "Eng",
                "department": "IT",
            },
            {"value": meetings},
            {"value": []},  # Emails
            {"value": []},  # Tasks
        ]

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        assert result["meetings"]["organized"] == 2
        # 66% organized should trigger insight
        insights_text = " ".join(result["insights"])
        assert "Organized" in insights_text or "initiative" in insights_text.lower()

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_email_recipient_tracking(self, mock_client_fn, mock_context):
        """Test tracking of top email recipients."""
        client = MagicMock()
        mock_client_fn.return_value = client

        emails = [
            {"toRecipients": [{"emailAddress": {"name": "Alice"}}]},
            {"toRecipients": [{"emailAddress": {"name": "Alice"}}]},
            {"toRecipients": [{"emailAddress": {"name": "Alice"}}]},
            {"toRecipients": [{"emailAddress": {"name": "Bob"}}]},
            {"toRecipients": [{"emailAddress": {"name": "Charlie"}}]},
        ]

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": []},  # Meetings
            {"value": emails},  # Emails
            {"value": []},  # Tasks
        ]

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        assert result["email"]["sent"] == 5
        assert len(result["email"]["top_recipients"]) >= 1
        # Alice should be top recipient
        assert result["email"]["top_recipients"][0]["name"] == "Alice"
        assert result["email"]["top_recipients"][0]["count"] == 3

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_tasks_completed_in_period(self, mock_client_fn, mock_context):
        """Test counting tasks completed in the analysis period."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=10)).isoformat()
        old = (now - timedelta(days=200)).isoformat()  # Outside 90-day window

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": []},  # Meetings
            {"value": []},  # Emails
            # To Do lists
            {"value": [{"id": "list-1"}]},
            {
                "value": [
                    {"completedDateTime": {"dateTime": recent}},
                    {"completedDateTime": {"dateTime": recent}},
                    {"completedDateTime": {"dateTime": old}},  # Should be excluded
                    {"completedDateTime": {"dateTime": "invalid"}},  # Invalid date
                ]
            },
        ]

        result = msgraph_performance_summary(mock_context, days=90)

        assert result["success"] is True
        assert result["tasks"]["completed"] == 2  # Only recent ones

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_meeting_analysis_error(self, mock_client_fn, mock_context):
        """Test graceful handling of meeting analysis error."""
        client = MagicMock()
        mock_client_fn.return_value = client

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me" == path:
                return {"displayName": "User", "mail": "user@walmart.com"}
            if "calendarView" in path:
                raise Exception("Calendar API error")
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        # Meetings should be zeros
        assert result["meetings"]["total"] == 0

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_email_analysis_error(self, mock_client_fn, mock_context):
        """Test graceful handling of email analysis error."""
        client = MagicMock()
        mock_client_fn.return_value = client

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me" == path:
                return {"displayName": "User", "mail": "user@walmart.com"}
            if "sentItems" in path:
                raise Exception("Mail API error")
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        assert result["email"]["sent"] == 0

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_insights_top_collaborator(self, mock_client_fn, mock_context):
        """Test insight for top collaborator."""
        client = MagicMock()
        mock_client_fn.return_value = client

        meetings = [
            {
                "subject": "Meeting with Alice",
                "start": {"dateTime": "2025-01-15T10:00:00Z"},
                "end": {"dateTime": "2025-01-15T11:00:00Z"},
                "organizer": {
                    "emailAddress": {"address": "alice@walmart.com", "name": "Alice"}
                },
                "isAllDay": False,
            },
        ]

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": meetings},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        insights_text = " ".join(result["insights"])
        assert "collaborator" in insights_text.lower() or "Alice" in insights_text

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_general_exception(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("Connection error")

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_all_day_events_skipped(self, mock_client_fn, mock_context):
        """Test that all-day events are skipped in analysis."""
        client = MagicMock()
        mock_client_fn.return_value = client

        meetings = [
            {
                "subject": "Regular Meeting",
                "start": {"dateTime": "2025-01-15T10:00:00Z"},
                "end": {"dateTime": "2025-01-15T11:00:00Z"},
                "organizer": {
                    "emailAddress": {"address": "other@walmart.com", "name": "Other"}
                },
                "isAllDay": False,
            },
            {
                "subject": "All Day Event",
                "start": {"dateTime": "2025-01-15T00:00:00Z"},
                "end": {"dateTime": "2025-01-16T00:00:00Z"},
                "organizer": {
                    "emailAddress": {"address": "other@walmart.com", "name": "Other"}
                },
                "isAllDay": True,
            },
        ]

        client.get.side_effect = [
            {"displayName": "User", "mail": "user@walmart.com"},
            {"value": meetings},
            {"value": []},
            {"value": []},
        ]

        result = msgraph_performance_summary(mock_context)

        assert result["success"] is True
        # Both meetings counted but only regular one for hours
        assert result["meetings"]["total"] == 2
        assert result["meetings"]["hours"] == 1.0  # Only 1 hour from regular meeting
