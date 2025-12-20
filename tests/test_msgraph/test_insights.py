"""Tests for MS Graph Insights API tools."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.insights import (
    msgraph_get_trending_docs,
    msgraph_get_recent_docs,
    msgraph_get_shared_with_me,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestGetTrendingDocs:
    """Tests for msgraph_get_trending_docs."""

    @patch("code_puppy.tools.msgraph.insights.get_msgraph_client")
    def test_get_trending_success(self, mock_client, mock_ctx):
        """Test getting trending documents."""
        mock_client.return_value.get.return_value = {
            "value": [
                {
                    "resourceReference": {
                        "id": "doc-1",
                        "webUrl": "https://example.com/doc1",
                    },
                    "resourceVisualization": {
                        "title": "Q4 Planning",
                        "type": "pptx",
                        "previewText": "Quarterly planning deck",
                        "containerDisplayName": "Team Files",
                    },
                    "lastUsed": {"lastAccessedDateTime": "2024-12-17T10:00:00Z"},
                }
            ]
        }

        result = msgraph_get_trending_docs(mock_ctx, top=10)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["documents"][0]["title"] == "Q4 Planning"

    @patch("code_puppy.tools.msgraph.insights.get_msgraph_client")
    def test_get_trending_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_get_trending_docs(mock_ctx)

        assert result["success"] is False


class TestGetRecentDocs:
    """Tests for msgraph_get_recent_docs."""

    @patch("code_puppy.tools.msgraph.insights.get_msgraph_client")
    def test_get_recent_success(self, mock_client, mock_ctx):
        """Test getting recently used documents."""
        mock_client.return_value.get.return_value = {
            "value": [
                {
                    "resourceReference": {
                        "id": "doc-2",
                        "webUrl": "https://example.com/doc2",
                    },
                    "resourceVisualization": {
                        "title": "Meeting Notes",
                        "type": "docx",
                        "containerDisplayName": "My Documents",
                    },
                    "lastUsed": {
                        "lastAccessedDateTime": "2024-12-18T09:00:00Z",
                        "lastModifiedDateTime": "2024-12-18T09:30:00Z",
                    },
                }
            ]
        }

        result = msgraph_get_recent_docs(mock_ctx, top=5)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["documents"][0]["title"] == "Meeting Notes"


class TestGetSharedWithMe:
    """Tests for msgraph_get_shared_with_me."""

    @patch("code_puppy.tools.msgraph.insights.get_msgraph_client")
    def test_get_shared_success(self, mock_client, mock_ctx):
        """Test getting shared documents."""
        mock_client.return_value.get.return_value = {
            "value": [
                {
                    "resourceReference": {
                        "id": "doc-3",
                        "webUrl": "https://example.com/doc3",
                    },
                    "resourceVisualization": {
                        "title": "Budget Proposal",
                        "type": "xlsx",
                        "containerDisplayName": "Finance",
                    },
                    "lastShared": {
                        "sharedDateTime": "2024-12-17T14:00:00Z",
                        "sharedBy": {
                            "displayName": "Jane Doe",
                            "address": "jane.doe@walmart.com",
                        },
                    },
                }
            ]
        }

        result = msgraph_get_shared_with_me(mock_ctx)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["documents"][0]["shared_by"] == "Jane Doe"
