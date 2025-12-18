"""Unit tests for MS Graph SharePoint module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.sharepoint import (
    msgraph_list_sites,
    msgraph_get_site,
    msgraph_list_site_drives,
    msgraph_list_site_items,
    msgraph_search_sharepoint,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphNotFoundError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_sites_data():
    """Create mock sites list from MS Graph API."""
    return {
        "value": [
            {
                "id": "site-123-abc",
                "displayName": "Marketing Team",
                "name": "marketing",
                "description": "Marketing team collaboration site",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing",
                "createdDateTime": "2024-06-15T08:00:00Z",
                "lastModifiedDateTime": "2025-01-15T10:30:00Z",
            },
            {
                "id": "site-456-def",
                "displayName": "Engineering Hub",
                "name": "engineering",
                "description": "Engineering documentation and resources",
                "webUrl": "https://walmart.sharepoint.com/sites/engineering",
                "createdDateTime": "2024-03-10T12:00:00Z",
                "lastModifiedDateTime": "2025-01-14T16:45:00Z",
            },
            {
                "id": "site-789-ghi",
                "displayName": "HR Portal",
                "name": "hr-portal",
                "description": "Human resources information",
                "webUrl": "https://walmart.sharepoint.com/sites/hr-portal",
                "createdDateTime": "2024-01-20T09:00:00Z",
                "lastModifiedDateTime": "2025-01-10T11:00:00Z",
            },
        ]
    }


@pytest.fixture
def mock_site_detail_data():
    """Create mock site detail data from MS Graph API."""
    return {
        "id": "site-123-abc",
        "displayName": "Marketing Team",
        "name": "marketing",
        "description": "Marketing team collaboration site",
        "webUrl": "https://walmart.sharepoint.com/sites/marketing",
        "createdDateTime": "2024-06-15T08:00:00Z",
        "lastModifiedDateTime": "2025-01-15T10:30:00Z",
        "siteCollection": {
            "hostname": "walmart.sharepoint.com",
            "root": {},
        },
    }


@pytest.fixture
def mock_drives_data():
    """Create mock document libraries list from MS Graph API."""
    return {
        "value": [
            {
                "id": "drive-123-abc",
                "name": "Documents",
                "description": "Main document library",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing/Documents",
                "driveType": "documentLibrary",
                "quota": {
                    "total": 27487790694400,
                    "remaining": 27487790694000,
                    "used": 400,
                },
            },
            {
                "id": "drive-456-def",
                "name": "Shared Assets",
                "description": "Shared marketing assets and templates",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing/SharedAssets",
                "driveType": "documentLibrary",
                "quota": {
                    "total": 27487790694400,
                    "remaining": 27487790600000,
                    "used": 94400,
                },
            },
        ]
    }


@pytest.fixture
def mock_site_items_data():
    """Create mock site items list from MS Graph API."""
    return {
        "value": [
            {
                "id": "folder-123-abc",
                "name": "Projects",
                "size": 0,
                "lastModifiedDateTime": "2025-01-15T10:30:00Z",
                "createdDateTime": "2024-12-01T08:00:00Z",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing/Documents/Projects",
                "folder": {"childCount": 12},
            },
            {
                "id": "file-456-def",
                "name": "Q4_Report.pptx",
                "size": 5242880,
                "lastModifiedDateTime": "2025-01-14T15:45:00Z",
                "createdDateTime": "2025-01-10T09:00:00Z",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing/Documents/Q4_Report.pptx",
                "file": {
                    "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                },
            },
            {
                "id": "file-789-ghi",
                "name": "brand_guidelines.pdf",
                "size": 1048576,
                "lastModifiedDateTime": "2025-01-13T12:00:00Z",
                "createdDateTime": "2024-11-15T14:30:00Z",
                "webUrl": "https://walmart.sharepoint.com/sites/marketing/Documents/brand_guidelines.pdf",
                "file": {"mimeType": "application/pdf"},
            },
        ]
    }


@pytest.fixture
def mock_search_results_data():
    """Create mock SharePoint search results from MS Graph API."""
    return {
        "value": [
            {
                "hitsContainers": [
                    {
                        "hits": [
                            {
                                "resource": {
                                    "id": "result-001",
                                    "name": "Marketing Strategy 2025.docx",
                                    "webUrl": "https://walmart.sharepoint.com/sites/marketing/Documents/Marketing%20Strategy%202025.docx",
                                    "lastModifiedDateTime": "2025-01-14T09:00:00Z",
                                    "size": 256000,
                                },
                                "summary": "...comprehensive <em>marketing strategy</em> for 2025...",
                            },
                            {
                                "resource": {
                                    "id": "result-002",
                                    "name": "Campaign Analysis.xlsx",
                                    "webUrl": "https://walmart.sharepoint.com/sites/marketing/Shared%20Assets/Campaign%20Analysis.xlsx",
                                    "lastModifiedDateTime": "2025-01-12T14:30:00Z",
                                    "size": 128000,
                                },
                                "summary": "...Q4 campaign performance <em>analysis</em>...",
                            },
                        ]
                    }
                ]
            }
        ]
    }


class TestMSGraphListSites:
    """Test suite for msgraph_list_sites tool."""

    def test_msgraph_list_sites(self, mock_context, mock_sites_data):
        """Test listing followed sites (no query)."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_sites_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context)

            assert result["success"] is True
            assert "sites" in result
            assert result["total_count"] == 3
            assert result["query"] is None
            assert len(result["sites"]) == 3

            # Check first site
            site = result["sites"][0]
            assert site["id"] == "site-123-abc"
            assert site["name"] == "Marketing Team"
            assert site["description"] == "Marketing team collaboration site"
            assert site["web_url"] == "https://walmart.sharepoint.com/sites/marketing"
            assert site["created"] == "2024-06-15T08:00:00Z"
            assert site["last_modified"] == "2025-01-15T10:30:00Z"

            # Verify API call for followed sites
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/followedSites"

    def test_msgraph_list_sites_with_query(self, mock_context, mock_sites_data):
        """Test searching sites with a query."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_sites_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context, query="marketing")

            assert result["success"] is True
            assert result["query"] == "marketing"
            assert result["total_count"] == 3

            # Verify API call uses search endpoint
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/sites"
            assert call_args[1]["params"]["search"] == "marketing"

    def test_msgraph_list_sites_with_limit(self, mock_context, mock_sites_data):
        """Test listing sites with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": mock_sites_data["value"][:1]}
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context, limit=5)

            assert result["success"] is True

            # Verify limit parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 5

    def test_msgraph_list_sites_empty(self, mock_context):
        """Test listing sites when none are followed."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context)

            assert result["success"] is True
            assert result["sites"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_sites_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]

    def test_msgraph_list_sites_search_no_results(self, mock_context):
        """Test search returning no results."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context, query="nonexistent_site_xyz123")

            assert result["success"] is True
            assert result["sites"] == []
            assert result["total_count"] == 0
            assert result["query"] == "nonexistent_site_xyz123"


class TestMSGraphGetSite:
    """Test suite for msgraph_get_site tool."""

    def test_msgraph_get_site(self, mock_context, mock_site_detail_data):
        """Test getting site details by ID."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_detail_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_site(mock_context, site_id="site-123-abc")

            assert result["success"] is True
            assert "site" in result

            site = result["site"]
            assert site["id"] == "site-123-abc"
            assert site["name"] == "Marketing Team"
            assert site["description"] == "Marketing team collaboration site"
            assert site["web_url"] == "https://walmart.sharepoint.com/sites/marketing"
            assert site["hostname"] == "walmart.sharepoint.com"
            assert "root" in site

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/sites/site-123-abc"

    def test_msgraph_get_site_by_path(self, mock_context, mock_site_detail_data):
        """Test getting site by hostname path notation."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_detail_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_site(
                mock_context, site_id="walmart.sharepoint.com:/sites/marketing"
            )

            assert result["success"] is True
            assert result["site"]["name"] == "Marketing Team"

            # Verify path-based endpoint
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/sites/walmart.sharepoint.com:/sites/marketing"

    def test_msgraph_get_site_not_found(self, mock_context):
        """Test handling of site not found error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Site not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_site(mock_context, site_id="nonexistent-site")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_get_site_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_site(mock_context, site_id="site-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_get_site_without_site_collection(self, mock_context):
        """Test getting site that has no siteCollection info."""
        site_data = {
            "id": "site-simple",
            "displayName": "Simple Site",
            "name": "simple",
            "description": "A simple site",
            "webUrl": "https://walmart.sharepoint.com/sites/simple",
            "createdDateTime": "2024-01-01T00:00:00Z",
            "lastModifiedDateTime": "2025-01-01T00:00:00Z",
            # No siteCollection field
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = site_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_site(mock_context, site_id="site-simple")

            assert result["success"] is True
            assert result["site"]["name"] == "Simple Site"
            # hostname and root should not be present
            assert "hostname" not in result["site"]
            assert "root" not in result["site"]


class TestMSGraphListSiteDrives:
    """Test suite for msgraph_list_site_drives tool."""

    def test_msgraph_list_site_drives(self, mock_context, mock_drives_data):
        """Test listing document libraries in a site."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_drives_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_drives(mock_context, site_id="site-123-abc")

            assert result["success"] is True
            assert "drives" in result
            assert result["total_count"] == 2
            assert result["site_id"] == "site-123-abc"
            assert len(result["drives"]) == 2

            # Check first drive
            drive = result["drives"][0]
            assert drive["id"] == "drive-123-abc"
            assert drive["name"] == "Documents"
            assert drive["description"] == "Main document library"
            assert (
                drive["web_url"]
                == "https://walmart.sharepoint.com/sites/marketing/Documents"
            )
            assert drive["drive_type"] == "documentLibrary"
            assert "quota" in drive

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/sites/site-123-abc/drives"

    def test_msgraph_list_site_drives_empty(self, mock_context):
        """Test listing drives when site has none."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_drives(mock_context, site_id="site-empty")

            assert result["success"] is True
            assert result["drives"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_site_drives_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_drives(mock_context, site_id="site-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_list_site_drives_not_found(self, mock_context):
        """Test handling of site not found error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Site not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_drives(mock_context, site_id="nonexistent")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphListSiteItems:
    """Test suite for msgraph_list_site_items tool."""

    def test_msgraph_list_site_items(self, mock_context, mock_site_items_data):
        """Test listing items from site root."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(mock_context, site_id="site-123-abc")

            assert result["success"] is True
            assert "items" in result
            assert result["total_count"] == 3
            assert result["site_id"] == "site-123-abc"
            assert result["drive_id"] is None
            assert result["path"] == "/"
            assert len(result["items"]) == 3

            # Check folder item
            folder = result["items"][0]
            assert folder["id"] == "folder-123-abc"
            assert folder["name"] == "Projects"
            assert folder["type"] == "folder"
            assert folder["child_count"] == 12
            assert folder["mime_type"] is None

            # Check file item
            file_item = result["items"][1]
            assert file_item["id"] == "file-456-def"
            assert file_item["name"] == "Q4_Report.pptx"
            assert file_item["type"] == "file"
            assert file_item["size"] == 5242880
            assert file_item["child_count"] is None
            assert "presentationml" in file_item["mime_type"]

            # Verify API call for root using default drive
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/sites/site-123-abc/drive/root/children"

    def test_msgraph_list_site_items_with_path(
        self, mock_context, mock_site_items_data
    ):
        """Test listing items in a specific folder path."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context, site_id="site-123-abc", path="/Projects/2025"
            )

            assert result["success"] is True
            assert result["path"] == "/Projects/2025"

            # Verify API call uses path-based endpoint
            call_args = mock_client.get.call_args
            assert (
                call_args[0][0]
                == "/sites/site-123-abc/drive/root:/Projects/2025:/children"
            )

    def test_msgraph_list_site_items_with_drive_id(
        self, mock_context, mock_site_items_data
    ):
        """Test listing items using a specific drive ID."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context, site_id="site-123-abc", drive_id="drive-456-def"
            )

            assert result["success"] is True
            assert result["drive_id"] == "drive-456-def"

            # Verify API call uses specific drive
            call_args = mock_client.get.call_args
            assert (
                call_args[0][0]
                == "/sites/site-123-abc/drives/drive-456-def/root/children"
            )

    def test_msgraph_list_site_items_with_drive_id_and_path(
        self, mock_context, mock_site_items_data
    ):
        """Test listing items with both drive ID and path."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_site_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context,
                site_id="site-123-abc",
                drive_id="drive-456-def",
                path="/Assets/Images",
            )

            assert result["success"] is True
            assert result["drive_id"] == "drive-456-def"
            assert result["path"] == "/Assets/Images"

            # Verify API call uses both drive ID and path
            call_args = mock_client.get.call_args
            assert (
                call_args[0][0]
                == "/sites/site-123-abc/drives/drive-456-def/root:/Assets/Images:/children"
            )

    def test_msgraph_list_site_items_with_limit(self, mock_context):
        """Test listing items with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context, site_id="site-123-abc", limit=50
            )

            assert result["success"] is True

            # Verify limit parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 50

    def test_msgraph_list_site_items_empty(self, mock_context):
        """Test listing an empty folder."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context, site_id="site-123-abc", path="/EmptyFolder"
            )

            assert result["success"] is True
            assert result["items"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_site_items_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(mock_context, site_id="site-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_list_site_items_not_found(self, mock_context):
        """Test handling of path not found error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Path not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(
                mock_context, site_id="site-123-abc", path="/NonexistentFolder"
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphSearchSharePoint:
    """Test suite for msgraph_search_sharepoint tool."""

    def test_msgraph_search_sharepoint(self, mock_context, mock_search_results_data):
        """Test searching across SharePoint."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_search_results_data
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="marketing strategy")

            assert result["success"] is True
            assert "results" in result
            assert result["total_count"] == 2
            assert result["query"] == "marketing strategy"
            assert len(result["results"]) == 2

            # Check first result
            first_result = result["results"][0]
            assert first_result["id"] == "result-001"
            assert first_result["name"] == "Marketing Strategy 2025.docx"
            assert "marketing" in first_result["web_url"].lower()
            assert first_result["size"] == 256000
            assert "marketing strategy" in first_result["summary"]

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/search/query"

            payload = call_args[1]["json"]
            assert "requests" in payload
            assert (
                payload["requests"][0]["query"]["queryString"] == "marketing strategy"
            )
            assert "driveItem" in payload["requests"][0]["entityTypes"]
            assert "listItem" in payload["requests"][0]["entityTypes"]
            assert "site" in payload["requests"][0]["entityTypes"]

    def test_msgraph_search_sharepoint_with_limit(self, mock_context):
        """Test searching with custom limit."""
        empty_results = {"value": []}

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = empty_results
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="test", limit=25)

            assert result["success"] is True

            # Verify limit parameter in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["requests"][0]["size"] == 25

    def test_msgraph_search_sharepoint_no_results(self, mock_context):
        """Test search returning no results."""
        empty_results = {"value": [{"hitsContainers": [{"hits": []}]}]}

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = empty_results
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(
                mock_context, query="xyznonexistent123abc"
            )

            assert result["success"] is True
            assert result["results"] == []
            assert result["total_count"] == 0
            assert result["query"] == "xyznonexistent123abc"

    def test_msgraph_search_sharepoint_empty_response(self, mock_context):
        """Test search with completely empty response."""
        empty_results = {"value": []}

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = empty_results
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="test")

            assert result["success"] is True
            assert result["results"] == []
            assert result["total_count"] == 0

    def test_msgraph_search_sharepoint_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="test")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_search_sharepoint_multiple_containers(self, mock_context):
        """Test search results from multiple hit containers."""
        multi_container_results = {
            "value": [
                {
                    "hitsContainers": [
                        {
                            "hits": [
                                {
                                    "resource": {
                                        "id": "doc-1",
                                        "name": "Document 1.docx",
                                        "webUrl": "https://example.com/doc1",
                                        "lastModifiedDateTime": "2025-01-15T10:00:00Z",
                                        "size": 1000,
                                    },
                                    "summary": "First document summary",
                                }
                            ]
                        },
                        {
                            "hits": [
                                {
                                    "resource": {
                                        "id": "site-1",
                                        "name": "Team Site",
                                        "webUrl": "https://example.com/site1",
                                        "lastModifiedDateTime": "2025-01-14T09:00:00Z",
                                        "size": None,
                                    },
                                    "summary": "Site description",
                                }
                            ]
                        },
                    ]
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = multi_container_results
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="team")

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["results"]) == 2

            # Verify both results are included
            names = [r["name"] for r in result["results"]]
            assert "Document 1.docx" in names
            assert "Team Site" in names


class TestMSGraphSharePointFormatting:
    """Test suite for SharePoint data formatting."""

    def test_site_formatting_with_display_name(self, mock_context):
        """Verify site uses displayName when available."""
        site_data = {
            "value": [
                {
                    "id": "site-id-123",
                    "displayName": "Displayed Name",
                    "name": "internal-name",
                    "description": "Test site",
                    "webUrl": "https://example.com/site",
                    "createdDateTime": "2025-01-01T00:00:00Z",
                    "lastModifiedDateTime": "2025-01-15T00:00:00Z",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = site_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context)

            # Should use displayName
            assert result["sites"][0]["name"] == "Displayed Name"

    def test_site_formatting_fallback_to_name(self, mock_context):
        """Verify site falls back to name when displayName is missing."""
        site_data = {
            "value": [
                {
                    "id": "site-id-123",
                    # No displayName
                    "name": "fallback-name",
                    "description": "Test site",
                    "webUrl": "https://example.com/site",
                    "createdDateTime": "2025-01-01T00:00:00Z",
                    "lastModifiedDateTime": "2025-01-15T00:00:00Z",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = site_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_sites(mock_context)

            # Should fall back to name
            assert result["sites"][0]["name"] == "fallback-name"

    def test_drive_item_unknown_type(self, mock_context):
        """Test handling of items that are neither file nor folder."""
        unknown_data = {
            "value": [
                {
                    "id": "unknown-id",
                    "name": "weird_item",
                    "size": 100,
                    "lastModifiedDateTime": "2025-01-15T10:00:00Z",
                    "createdDateTime": "2025-01-15T10:00:00Z",
                    "webUrl": "https://sharepoint.com/weird_item",
                    # No "file" or "folder" key
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = unknown_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_site_items(mock_context, site_id="site-123")

            item = result["items"][0]
            assert item["type"] == "unknown"
            assert item["child_count"] is None
            assert item["mime_type"] is None

    def test_search_hit_formatting(self, mock_context):
        """Verify search hit fields are properly mapped."""
        search_data = {
            "value": [
                {
                    "hitsContainers": [
                        {
                            "hits": [
                                {
                                    "resource": {
                                        "id": "hit-id-123",
                                        "name": "Important.pdf",
                                        "webUrl": "https://sp.com/Important.pdf",
                                        "lastModifiedDateTime": "2025-01-15T12:00:00Z",
                                        "size": 999999,
                                    },
                                    "summary": "This is the <em>highlight</em> text",
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.sharepoint.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = search_data
            mock_get_client.return_value = mock_client

            result = msgraph_search_sharepoint(mock_context, query="important")

            hit = result["results"][0]
            assert hit["id"] == "hit-id-123"
            assert hit["name"] == "Important.pdf"
            assert hit["web_url"] == "https://sp.com/Important.pdf"
            assert hit["last_modified"] == "2025-01-15T12:00:00Z"
            assert hit["size"] == 999999
            assert hit["summary"] == "This is the <em>highlight</em> text"
