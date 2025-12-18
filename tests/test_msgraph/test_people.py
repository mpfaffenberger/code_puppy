"""Tests for MS Graph People API tools."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.people import (
    msgraph_get_relevant_people,
    msgraph_search_people_relevant,
    msgraph_check_sender_importance,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


@pytest.fixture
def sample_people():
    return [
        {
            "id": "person-1",
            "displayName": "Aaron Berg",
            "emailAddresses": [{"address": "aaron.berg@walmart.com"}],
            "jobTitle": "Director",
            "department": "Technology",
            "companyName": "Walmart",
            "personType": {"subclass": "OrganizationUser"},
        },
        {
            "id": "person-2",
            "displayName": "Brandon Gardner",
            "emailAddresses": [{"address": "brandon.gardner@walmart.com"}],
            "jobTitle": "Sr Manager",
            "department": "Technology",
            "companyName": "Walmart",
            "personType": {"subclass": "OrganizationUser"},
        },
    ]


class TestGetRelevantPeople:
    """Tests for msgraph_get_relevant_people."""

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_get_relevant_success(self, mock_client, mock_ctx, sample_people):
        """Test getting relevant people."""
        mock_client.return_value.get.return_value = {"value": sample_people}

        result = msgraph_get_relevant_people(mock_ctx, top=25)

        assert result["success"] is True
        assert result["count"] == 2
        assert result["people"][0]["name"] == "Aaron Berg"
        assert result["people"][0]["rank"] == 1
        assert result["people"][1]["rank"] == 2

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_get_relevant_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_get_relevant_people(mock_ctx)

        assert result["success"] is False


class TestSearchPeopleRelevant:
    """Tests for msgraph_search_people_relevant."""

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_search_success(self, mock_client, mock_ctx, sample_people):
        """Test searching for people."""
        mock_client.return_value.get.return_value = {"value": sample_people[:1]}

        result = msgraph_search_people_relevant(mock_ctx, query="Aaron")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["results"][0]["name"] == "Aaron Berg"


class TestCheckSenderImportance:
    """Tests for msgraph_check_sender_importance."""

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_vip_sender_rank_1(self, mock_client, mock_ctx, sample_people):
        """Test checking a top-ranked sender."""
        mock_client.return_value.get.return_value = {"value": sample_people}

        result = msgraph_check_sender_importance(
            mock_ctx, email_address="aaron.berg@walmart.com"
        )

        assert result["success"] is True
        assert result["found"] is True
        assert result["relevance_rank"] == 1
        assert result["importance"] == "critical"
        assert result["is_vip"] is True

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_vip_sender_rank_2(self, mock_client, mock_ctx, sample_people):
        """Test checking a second-ranked sender."""
        mock_client.return_value.get.return_value = {"value": sample_people}

        result = msgraph_check_sender_importance(
            mock_ctx, email_address="brandon.gardner@walmart.com"
        )

        assert result["success"] is True
        assert result["found"] is True
        assert result["relevance_rank"] == 2
        assert result["importance"] == "critical"
        assert result["is_vip"] is True

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_unknown_sender(self, mock_client, mock_ctx, sample_people):
        """Test checking an unknown sender."""
        mock_client.return_value.get.return_value = {"value": sample_people}

        result = msgraph_check_sender_importance(
            mock_ctx, email_address="random@external.com"
        )

        assert result["success"] is True
        assert result["found"] is False
        assert result["importance"] == "low"
        assert result["is_vip"] is False

    @patch("code_puppy.tools.msgraph.people.get_msgraph_client")
    def test_case_insensitive(self, mock_client, mock_ctx, sample_people):
        """Test that email matching is case-insensitive."""
        mock_client.return_value.get.return_value = {"value": sample_people}

        result = msgraph_check_sender_importance(
            mock_ctx, email_address="AARON.BERG@WALMART.COM"
        )

        assert result["success"] is True
        assert result["found"] is True
