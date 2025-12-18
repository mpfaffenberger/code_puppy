"""Tests for MS Graph Relationships and Org Context."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.relationships import (
    msgraph_get_org_context,
    msgraph_get_relationship_context,
    msgraph_relationship_health,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestGetOrgContext:
    """Tests for msgraph_get_org_context."""

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_full_org_context(self, mock_client, mock_ctx):
        """Test getting complete org context."""
        mock_client.return_value.get.side_effect = [
            # Current user
            {
                "id": "user-1",
                "displayName": "Trevor Dodson",
                "mail": "trevor@test.com",
                "jobTitle": "Sr. Software Engineer",
                "department": "Technology",
            },
            # Manager
            {
                "id": "mgr-1",
                "displayName": "Brandon Gardner",
                "mail": "brandon@test.com",
                "jobTitle": "Sr. Director",
            },
            # Skip-level
            {
                "id": "skip-1",
                "displayName": "Aaron Berg",
                "mail": "aaron@test.com",
                "jobTitle": "VP",
            },
            # Direct reports
            {"value": []},
            # Collaborators
            {
                "value": [
                    {
                        "id": "collab-1",
                        "displayName": "Chris Brown",
                        "emailAddresses": [{"address": "chris@test.com"}],
                        "jobTitle": "Sr. Manager",
                    }
                ]
            },
        ]

        result = msgraph_get_org_context(mock_ctx)

        assert result["success"] is True
        assert result["user"]["name"] == "Trevor Dodson"
        assert result["manager"]["name"] == "Brandon Gardner"
        assert result["skip_level"]["name"] == "Aaron Berg"
        assert len(result["relationship_tiers"]["critical"]) == 2  # Manager + skip

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_no_manager(self, mock_client, mock_ctx):
        """Test when user has no manager."""
        mock_client.return_value.get.side_effect = [
            # Current user
            {"id": "user-1", "displayName": "CEO"},
            # Manager - 404
            Exception("404 Not Found"),
            # Direct reports
            {"value": []},
            # Collaborators
            {"value": []},
        ]

        result = msgraph_get_org_context(mock_ctx)

        assert result["success"] is True
        assert result["manager"] is None

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_get_org_context(mock_ctx)

        assert result["success"] is False


class TestGetRelationshipContext:
    """Tests for msgraph_get_relationship_context."""

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_manager_relationship(self, mock_client, mock_ctx):
        """Test identifying manager relationship."""
        # Need to mock ALL get calls in order
        mock_client.return_value.get.side_effect = [
            # 1. Manager check - email matches (BOSS@test.com will be lowercased)
            {"mail": "boss@test.com", "displayName": "Boss", "jobTitle": "Director"},
            # 2. Direct reports NOT called since relationship_type is now "manager"
            # 3. People API for relevance ranking
            {"value": []},
            # 4. Recent emails
            {"value": []},
            # 5. Recent meetings
            {"value": []},
        ]

        result = msgraph_get_relationship_context(
            mock_ctx, email_address="BOSS@test.com"  # Test case-insensitivity
        )

        assert result["success"] is True
        assert result["relationship_type"] == "manager"
        assert result["suggested_response_style"]["urgency"] == "high"

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_peer_relationship(self, mock_client, mock_ctx):
        """Test identifying peer relationship."""
        mock_client.return_value.get.side_effect = [
            # Manager check - not a match
            {"mail": "other@test.com"},
            # Direct reports - not a match
            {"value": []},
            # People API - found in top 10
            {
                "value": [
                    {
                        "displayName": "Colleague",
                        "emailAddresses": [{"address": "colleague@test.com"}],
                        "jobTitle": "Engineer",
                        "personType": {"subclass": "OrganizationUser"},
                    }
                ]
            },
            # Recent emails
            {"value": [{"subject": "Test", "receivedDateTime": "2024-12-17T10:00:00Z", "from": {"emailAddress": {"address": "colleague@test.com"}}}]},
            # Recent meetings
            {"value": []},
        ]

        result = msgraph_get_relationship_context(
            mock_ctx, email_address="colleague@test.com"
        )

        assert result["success"] is True
        assert result["relationship_type"] == "peer"
        assert result["relevance_rank"] == 1
        assert result["is_internal"] is True

    def test_empty_email(self, mock_ctx):
        """Test that empty email is rejected."""
        result = msgraph_get_relationship_context(mock_ctx, email_address="")

        assert result["success"] is False
        assert "empty" in result["error"].lower()


class TestRelationshipHealth:
    """Tests for msgraph_relationship_health."""

    @patch("code_puppy.tools.msgraph.relationships.get_msgraph_client")
    def test_identifies_stale_relationships(self, mock_client, mock_ctx):
        """Test identifying relationships needing attention."""
        mock_client.return_value.get.side_effect = [
            # People
            {
                "value": [
                    {
                        "displayName": "Active Contact",
                        "emailAddresses": [{"address": "active@test.com"}],
                        "jobTitle": "Manager",
                    },
                    {
                        "displayName": "Stale Contact",
                        "emailAddresses": [{"address": "stale@test.com"}],
                        "jobTitle": "Director",
                    },
                ]
            },
            # Active contact - recent email
            {
                "value": [
                    {"receivedDateTime": "2024-12-17T10:00:00Z"}
                ]
            },
            # Stale contact - no recent email
            {"value": []},
        ]

        result = msgraph_relationship_health(
            mock_ctx, days_threshold=14, top_contacts=2
        )

        assert result["success"] is True
        assert len(result["needs_attention"]) >= 1
        assert any(s["contact"] == "Stale Contact" for s in result["suggestions"])
