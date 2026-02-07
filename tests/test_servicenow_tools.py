"""Tests for ServiceNow Knowledge Base tools."""

import json
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.walmart_specific.servicenow_client import (
    ServiceNowAuthError,
    ServiceNowClient,
    ServiceNowError,
    ServiceNowNotFoundError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session_file(tmp_path):
    """Create a mock session file for testing."""
    session_data = {
        "cookies": {
            "glide_session_store": "test_session_value",
            "JSESSIONID": "test_jsessionid",
        },
        "all_cookies": {
            "glide_session_store": "test_session_value",
            "JSESSIONID": "test_jsessionid",
        },
        "url": "https://walmartglobal.service-now.com/",
        "timestamp": "2025-01-15T10:00:00",
    }
    session_file = tmp_path / "servicenow.json"
    session_file.write_text(json.dumps(session_data))
    return session_file


@pytest.fixture
def mock_kb_search_response():
    """Mock response for KB article search."""
    return {
        "result": [
            {
                "sys_id": "abc123",
                "number": "KB0012345",
                "short_description": "How to reset your password",
                "text": "<p>Follow these steps to reset your password...</p>",
                "category": "IT Support",
                "kb_knowledge_base": "IT Knowledge Base",
                "workflow_state": "published",
                "sys_updated_on": "2025-01-10 12:00:00",
            },
            {
                "sys_id": "def456",
                "number": "KB0012346",
                "short_description": "Password policy guidelines",
                "text": "<p>Password must be at least 12 characters...</p>",
                "category": "Security",
                "kb_knowledge_base": "Security Knowledge Base",
                "workflow_state": "published",
                "sys_updated_on": "2025-01-09 10:00:00",
            },
        ]
    }


@pytest.fixture
def mock_kb_article_response():
    """Mock response for single KB article."""
    return {
        "result": {
            "sys_id": "abc123",
            "number": "KB0012345",
            "short_description": "How to reset your password",
            "text": "<h2>Password Reset Guide</h2><p>Follow these steps to reset your password:</p><ol><li>Go to the login page</li><li>Click 'Forgot Password'</li><li>Enter your email</li><li>Check your inbox</li></ol>",
            "category": "IT Support",
            "kb_knowledge_base": "IT Knowledge Base",
            "workflow_state": "published",
        }
    }


# =============================================================================
# ServiceNow Client Tests
# =============================================================================


class TestServiceNowClient:
    """Tests for ServiceNowClient class."""

    def test_client_init_missing_session_file(self, tmp_path):
        """Test that client raises error when session file is missing."""
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(tmp_path / "nonexistent.json"))
        assert "Session file not found" in str(exc_info.value)

    def test_client_init_invalid_json(self, tmp_path):
        """Test that client raises error for invalid JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(bad_file))
        assert "Invalid JSON" in str(exc_info.value)

    def test_client_init_missing_cookies(self, tmp_path):
        """Test that client raises error when cookies field is missing."""
        no_cookies_file = tmp_path / "no_cookies.json"
        no_cookies_file.write_text(json.dumps({"url": "https://example.com"}))
        with pytest.raises(ServiceNowError) as exc_info:
            ServiceNowClient(session_file_path=str(no_cookies_file))
        assert "missing 'cookies' field" in str(exc_info.value)

    def test_client_init_success(self, mock_session_file):
        """Test successful client initialization."""
        with patch.object(ServiceNowClient, "_check_staleness"):
            client = ServiceNowClient(session_file_path=str(mock_session_file))
            assert client.base_url == "https://walmartglobal.service-now.com"
            assert "glide_session_store" in client.cookies
            client.close()


# =============================================================================
# ServiceNow Tools Tests
# =============================================================================


class TestServiceNowKBSearch:
    """Tests for servicenow_kb_search tool."""

    def test_search_success(self, mock_session_file, mock_kb_search_response):
        """Test successful KB article search."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_articles.return_value = mock_kb_search_response
            MockClient.return_value = mock_client

            result = servicenow_kb_search(mock_ctx, "password reset", limit=10)

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["articles"]) == 2
            assert result["articles"][0]["number"] == "KB0012345"
            assert result["articles"][0]["title"] == "How to reset your password"

    def test_search_auth_error(self, mock_session_file):
        """Test search handling of authentication error."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_articles.side_effect = ServiceNowAuthError(
                "Authentication failed"
            )
            MockClient.return_value = mock_client

            result = servicenow_kb_search(mock_ctx, "password")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestServiceNowKBReadArticle:
    """Tests for servicenow_kb_read_article tool."""

    def test_read_article_by_number(self, mock_session_file, mock_kb_article_response):
        """Test reading article by KB number."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        # Wrap the result in a list since get_kb_article_by_number returns list
        mock_response = {"result": [mock_kb_article_response["result"]]}

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_number.return_value = mock_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "KB0012345")

            assert result["success"] is True
            assert result["number"] == "KB0012345"
            assert result["title"] == "How to reset your password"
            assert "Password Reset Guide" in result["content"]

    def test_read_article_by_sys_id(self, mock_session_file, mock_kb_article_response):
        """Test reading article by sys_id."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_id.return_value = mock_kb_article_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "abc123")

            assert result["success"] is True
            assert result["sys_id"] == "abc123"

    def test_read_article_not_found(self, mock_session_file):
        """Test handling of article not found."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_number.return_value = {"result": []}
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(mock_ctx, "KB9999999")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_read_article_with_character_limit(self, mock_session_file):
        """Test reading article with character limit."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_read_article

        mock_ctx = MagicMock()
        long_content = "<p>" + "A" * 50000 + "</p>"
        mock_response = {
            "result": {
                "sys_id": "abc123",
                "number": "KB0012345",
                "short_description": "Long article",
                "text": long_content,
                "category": "Test",
                "workflow_state": "published",
            }
        }

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.get_kb_article_by_id.return_value = mock_response
            MockClient.return_value = mock_client

            result = servicenow_kb_read_article(
                mock_ctx, "abc123", character_limit=1000
            )

            assert result["success"] is True
            assert result["content_truncated"] is True
            assert len(result["content"]) <= 1000
            assert result["remaining_content_length"] > 0


class TestServiceNowKBSearchByCategory:
    """Tests for servicenow_kb_search_by_category tool."""

    def test_search_by_category_success(
        self, mock_session_file, mock_kb_search_response
    ):
        """Test successful category search."""
        from code_puppy.tools.servicenow_tools import servicenow_kb_search_by_category

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools._common.ServiceNowClient"
        ) as MockClient:
            mock_client = MagicMock()
            mock_client.search_kb_by_category.return_value = mock_kb_search_response
            MockClient.return_value = mock_client

            result = servicenow_kb_search_by_category(
                mock_ctx, category="IT Support", query="password"
            )

            assert result["success"] is True
            assert result["category"] == "IT Support"
            assert len(result["articles"]) == 2


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_convert_html_to_markdown(self):
        """Test HTML to markdown conversion."""
        from code_puppy.tools.servicenow_tools._common import (
            convert_html_to_markdown as _convert_html_to_markdown,
        )

        html = (
            "<h2>Title</h2><p>Paragraph text</p><ul><li>Item 1</li><li>Item 2</li></ul>"
        )
        markdown = _convert_html_to_markdown(html)

        assert "## Title" in markdown
        assert "Paragraph text" in markdown
        assert "Item 1" in markdown

    def test_convert_empty_html(self):
        """Test conversion of empty HTML."""
        from code_puppy.tools.servicenow_tools._common import (
            convert_html_to_markdown as _convert_html_to_markdown,
        )

        assert _convert_html_to_markdown("") == ""
        assert _convert_html_to_markdown(None) == ""

    # Note: _format_search_result helper tests removed as functionality is now internal to kb.py


# =============================================================================
# Incident Management Tests
# =============================================================================


@pytest.fixture
def mock_incident_response():
    """Mock response for incident creation/retrieval."""
    return {
        "result": {
            "sys_id": "inc123456",
            "number": "INC0012345",
            "short_description": "Test incident",
            "description": "Detailed description of the issue",
            "state": "1",
            "priority": "3",
            "urgency": "3",
            "impact": "3",
            "assigned_to": {"display_value": "John Doe", "link": "..."},
            "assignment_group": {"display_value": "IT Support", "link": "..."},
            "sys_created_on": "2025-01-15 10:00:00",
            "sys_updated_on": "2025-01-15 10:30:00",
        }
    }


@pytest.fixture
def mock_incident_list_response():
    """Mock response for incident list."""
    return {
        "result": [
            {
                "sys_id": "inc123456",
                "number": "INC0012345",
                "short_description": "First incident",
                "state": "1",
                "priority": "3",
                "assigned_to": {"display_value": "John Doe"},
                "assignment_group": {"display_value": "IT Support"},
                "sys_created_on": "2025-01-15 10:00:00",
            },
            {
                "sys_id": "inc789012",
                "number": "INC0012346",
                "short_description": "Second incident",
                "state": "2",
                "priority": "2",
                "assigned_to": {"display_value": "Jane Smith"},
                "assignment_group": {"display_value": "Network Team"},
                "sys_created_on": "2025-01-14 09:00:00",
            },
        ]
    }


class TestServiceNowCreateIncident:
    """Tests for servicenow_create_incident tool."""

    def test_create_incident_dry_run(self):
        """Test incident creation in dry run mode."""
        from code_puppy.tools.servicenow_tools import servicenow_create_incident

        mock_ctx = MagicMock()

        result = servicenow_create_incident(
            mock_ctx,
            short_description="Test incident - VPN not working",
            description="I can't connect to the VPN since this morning.",
            urgency=2,
            impact=3,
            category="Network",
            dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert "preview" in result
        assert (
            result["preview"]["short_description"] == "Test incident - VPN not working"
        )
        assert "2 (Medium)" in result["preview"]["urgency"]
        assert "3 (Low)" in result["preview"]["impact"]
        assert result["preview"]["category"] == "Network"

    def test_create_incident_success(self, mock_incident_response):
        """Test successful incident creation."""
        from code_puppy.tools.servicenow_tools import servicenow_create_incident

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.create_incident.return_value = mock_incident_response
            mock_get_client.return_value = mock_client

            result = servicenow_create_incident(
                mock_ctx,
                short_description="Test incident",
                description="Test description",
                urgency=3,
                impact=3,
                dry_run=False,
            )

            assert result["success"] is True
            assert result["dry_run"] is False
            assert result["incident_number"] == "INC0012345"
            assert result["sys_id"] == "inc123456"
            assert "incident.do" in result["url"]

    def test_create_incident_auth_error(self):
        """Test incident creation with auth error."""
        from code_puppy.tools.servicenow_tools import servicenow_create_incident

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.create_incident.side_effect = ServiceNowAuthError(
                "Authentication failed"
            )
            mock_get_client.return_value = mock_client

            result = servicenow_create_incident(
                mock_ctx,
                short_description="Test incident",
                dry_run=False,
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestServiceNowGetIncident:
    """Tests for servicenow_get_incident tool."""

    def test_get_incident_by_number(self, mock_incident_response):
        """Test getting incident by number."""
        from code_puppy.tools.servicenow_tools import servicenow_get_incident

        mock_ctx = MagicMock()
        # Wrap in list since searching by number returns list
        list_response = {"result": [mock_incident_response["result"]]}

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_incident.return_value = list_response
            mock_get_client.return_value = mock_client

            result = servicenow_get_incident(mock_ctx, "INC0012345")

            assert result["success"] is True
            assert result["number"] == "INC0012345"
            assert result["assigned_to"] == "John Doe"
            assert result["assignment_group"] == "IT Support"

    def test_get_incident_not_found(self):
        """Test getting non-existent incident."""
        from code_puppy.tools.servicenow_tools import servicenow_get_incident

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_incident.side_effect = ServiceNowNotFoundError(
                "Incident not found"
            )
            mock_get_client.return_value = mock_client

            result = servicenow_get_incident(mock_ctx, "INC9999999")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestServiceNowListMyIncidents:
    """Tests for servicenow_list_my_incidents tool."""

    def test_list_my_incidents_success(self, mock_incident_list_response):
        """Test listing user's incidents."""
        from code_puppy.tools.servicenow_tools import servicenow_list_my_incidents

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_my_incidents.return_value = mock_incident_list_response
            mock_get_client.return_value = mock_client

            result = servicenow_list_my_incidents(mock_ctx)

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["incidents"]) == 2
            assert result["incidents"][0]["number"] == "INC0012345"

    def test_list_my_incidents_with_state_filter(self, mock_incident_list_response):
        """Test listing incidents filtered by state."""
        from code_puppy.tools.servicenow_tools import servicenow_list_my_incidents

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.incidents.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_my_incidents.return_value = mock_incident_list_response
            mock_get_client.return_value = mock_client

            result = servicenow_list_my_incidents(mock_ctx, state="in_progress")

            assert result["success"] is True
            # Verify the state was passed correctly
            mock_client.list_my_incidents.assert_called_once_with(
                state="in_progress", limit=25
            )


class TestServiceNowAddIncidentComment:
    """Tests for servicenow_add_incident_comment tool."""

    def test_add_comment_dry_run(self):
        """Test adding comment in dry run mode."""
        from code_puppy.tools.servicenow_tools import servicenow_add_incident_comment

        mock_ctx = MagicMock()

        result = servicenow_add_incident_comment(
            mock_ctx,
            incident_id="INC0012345",
            comment="This is a test comment",
            is_work_note=False,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert "preview" in result
        assert result["preview"]["incident_id"] == "INC0012345"
        assert result["preview"]["type"] == "comment"

    def test_add_work_note_dry_run(self):
        """Test adding work note in dry run mode."""
        from code_puppy.tools.servicenow_tools import servicenow_add_incident_comment

        mock_ctx = MagicMock()

        result = servicenow_add_incident_comment(
            mock_ctx,
            incident_id="INC0012345",
            comment="Internal work note",
            is_work_note=True,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["preview"]["type"] == "work note"


# =============================================================================
# Service Catalog Tests
# =============================================================================


@pytest.fixture
def mock_catalog_items_response():
    """Mock response for catalog items list."""
    return {
        "result": [
            {
                "sys_id": "cat001",
                "name": "Software Request",
                "short_description": "Request new software installation",
                "category": {"title": "Software"},
                "price": "$0.00",
                "delivery_time": "3 business days",
            },
            {
                "sys_id": "cat002",
                "name": "Hardware Request",
                "short_description": "Request new hardware",
                "category": {"title": "Hardware"},
                "price": "Varies",
                "delivery_time": "5-7 business days",
            },
        ]
    }


@pytest.fixture
def mock_catalog_request_response():
    """Mock response for catalog request submission."""
    return {
        "result": {
            "sys_id": "req123456",
            "number": "REQ0012345",
            "request_number": "REQ0012345",
            "request_id": "req123456",
        }
    }


class TestServiceNowListCatalogItems:
    """Tests for servicenow_list_catalog_items tool."""

    def test_list_catalog_items_success(self, mock_catalog_items_response):
        """Test listing catalog items."""
        from code_puppy.tools.servicenow_tools import servicenow_list_catalog_items

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.catalog.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_catalog_items.return_value = mock_catalog_items_response
            mock_get_client.return_value = mock_client

            result = servicenow_list_catalog_items(mock_ctx, query="software")

            assert result["success"] is True
            assert result["total_count"] == 2
            assert result["items"][0]["name"] == "Software Request"
            assert result["items"][0]["category"] == "Software"


class TestServiceNowGetCatalogItemDetails:
    """Tests for servicenow_get_catalog_item_details tool."""

    def test_get_catalog_item_details_success(self):
        """Test getting catalog item details with variables."""
        from code_puppy.tools.servicenow_tools import (
            servicenow_get_catalog_item_details,
        )

        mock_ctx = MagicMock()
        mock_response = {
            "result": {
                "sys_id": "cat001",
                "name": "Software Request",
                "short_description": "Request new software",
                "description": "<p>Use this form to request software installation.</p>",
                "category": {"name": "Software"},
                "price": "$0.00",
                "delivery_time": "3 days",
                "variables": [
                    {
                        "name": "software_name",
                        "label": "Software Name",
                        "type": "string",
                        "mandatory": True,
                        "help_text": "Enter the name of the software",
                    },
                    {
                        "name": "justification",
                        "label": "Business Justification",
                        "type": "string",
                        "mandatory": True,
                        "help_text": "Why do you need this software?",
                    },
                    {
                        "name": "urgency",
                        "label": "Urgency",
                        "type": "5",
                        "mandatory": False,
                        "choices": [
                            {"value": "low", "label": "Low"},
                            {"value": "medium", "label": "Medium"},
                            {"value": "high", "label": "High"},
                        ],
                    },
                ],
            }
        }

        with patch(
            "code_puppy.tools.servicenow_tools.catalog.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_catalog_item.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = servicenow_get_catalog_item_details(mock_ctx, "cat001")

            assert result["success"] is True
            assert result["name"] == "Software Request"

    def test_get_catalog_item_not_found(self):
        """Test handling of catalog item not found."""
        from code_puppy.tools.servicenow_tools import (
            servicenow_get_catalog_item_details,
        )

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.catalog.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_catalog_item.side_effect = ServiceNowNotFoundError(
                "Catalog item not found"
            )
            mock_get_client.return_value = mock_client

            result = servicenow_get_catalog_item_details(mock_ctx, "nonexistent")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestServiceNowSubmitCatalogRequest:
    """Tests for servicenow_submit_catalog_request tool."""

    def test_submit_catalog_request_dry_run(self):
        """Test catalog request in dry run mode."""
        from code_puppy.tools.servicenow_tools import servicenow_submit_catalog_request

        mock_ctx = MagicMock()

        result = servicenow_submit_catalog_request(
            mock_ctx,
            item_id="cat001",
            variables={"software_name": "VS Code", "justification": "Development"},
            quantity=1,
            special_instructions="Please install latest version",
            dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert "preview" in result
        assert result["preview"]["item_id"] == "cat001"
        assert result["preview"]["variables"]["software_name"] == "VS Code"
        assert result["preview"]["quantity"] == 1

    def test_submit_catalog_request_success(self, mock_catalog_request_response):
        """Test successful catalog request submission."""
        from code_puppy.tools.servicenow_tools import servicenow_submit_catalog_request

        mock_ctx = MagicMock()

        with patch(
            "code_puppy.tools.servicenow_tools.catalog.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.submit_catalog_request.return_value = (
                mock_catalog_request_response
            )
            mock_get_client.return_value = mock_client

            result = servicenow_submit_catalog_request(
                mock_ctx,
                item_id="cat001",
                variables={"software_name": "VS Code"},
                dry_run=False,
            )

            assert result["success"] is True
            assert result["dry_run"] is False
            assert result["request_number"] == "REQ0012345"


class TestServiceNowGetRequestStatus:
    """Tests for servicenow_get_request_status tool."""

    def test_get_request_status_by_number(self):
        """Test getting request status by number."""
        from code_puppy.tools.servicenow_tools import servicenow_get_request_status

        mock_ctx = MagicMock()
        mock_response = {
            "result": [
                {
                    "sys_id": "req123456",
                    "number": "REQ0012345",
                    "request_state": "Approved",
                    "stage": "Fulfillment",
                    "requested_for": {"display_value": "Bill User"},
                    "opened_at": "2025-01-15 10:00:00",
                    "short_description": "Software request",
                }
            ]
        }

        with patch(
            "code_puppy.tools.servicenow_tools.catalog.get_servicenow_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_request_status.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = servicenow_get_request_status(mock_ctx, "REQ0012345")

            assert result["success"] is True
            assert result["number"] == "REQ0012345"
