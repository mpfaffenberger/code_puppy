"""Unit tests for MS Graph OneDrive module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.onedrive import (
    msgraph_list_drive_items,
    msgraph_get_drive_item,
    msgraph_download_file,
    msgraph_upload_file,
    msgraph_create_folder,
    msgraph_share_file,
    msgraph_search_files,
    msgraph_delete_drive_item,
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
def mock_drive_items_data():
    """Create mock drive items list from MS Graph API."""
    return {
        "value": [
            {
                "id": "folder-123-abc",
                "name": "Documents",
                "size": 0,
                "lastModifiedDateTime": "2025-01-15T10:30:00Z",
                "createdDateTime": "2025-01-01T08:00:00Z",
                "webUrl": "https://walmart-my.sharepoint.com/Documents",
                "folder": {"childCount": 5},
            },
            {
                "id": "file-456-def",
                "name": "report.xlsx",
                "size": 25600,
                "lastModifiedDateTime": "2025-01-14T15:45:00Z",
                "createdDateTime": "2025-01-10T09:00:00Z",
                "webUrl": "https://walmart-my.sharepoint.com/report.xlsx",
                "file": {
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
            },
            {
                "id": "file-789-ghi",
                "name": "notes.txt",
                "size": 1024,
                "lastModifiedDateTime": "2025-01-13T12:00:00Z",
                "createdDateTime": "2025-01-12T11:00:00Z",
                "webUrl": "https://walmart-my.sharepoint.com/notes.txt",
                "file": {"mimeType": "text/plain"},
            },
        ]
    }


@pytest.fixture
def mock_file_item_data():
    """Create mock file item data from MS Graph API."""
    return {
        "id": "file-456-def",
        "name": "report.xlsx",
        "size": 25600,
        "lastModifiedDateTime": "2025-01-14T15:45:00Z",
        "createdDateTime": "2025-01-10T09:00:00Z",
        "webUrl": "https://walmart-my.sharepoint.com/report.xlsx",
        "file": {
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
        "parentReference": {"path": "/drive/root:/Documents"},
    }


@pytest.fixture
def mock_folder_item_data():
    """Create mock folder item data from MS Graph API."""
    return {
        "id": "folder-123-abc",
        "name": "Documents",
        "size": 0,
        "lastModifiedDateTime": "2025-01-15T10:30:00Z",
        "createdDateTime": "2025-01-01T08:00:00Z",
        "webUrl": "https://walmart-my.sharepoint.com/Documents",
        "folder": {"childCount": 5},
        "parentReference": {"path": "/drive/root:"},
    }


@pytest.fixture
def mock_text_file_data():
    """Create mock text file metadata for download tests."""
    return {
        "id": "text-file-123",
        "name": "notes.txt",
        "size": 100,
        "lastModifiedDateTime": "2025-01-15T10:00:00Z",
        "file": {"mimeType": "text/plain"},
    }


@pytest.fixture
def mock_share_link_response():
    """Create mock sharing link response."""
    return {
        "link": {
            "webUrl": "https://walmart-my.sharepoint.com/:x:/g/personal/user/Eabc123",
            "type": "view",
            "scope": "organization",
        }
    }


class TestMSGraphListDriveItems:
    """Test suite for msgraph_list_drive_items tool."""

    def test_msgraph_list_drive_items(self, mock_context, mock_drive_items_data):
        """Test listing items from root."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_drive_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context)

            assert result["success"] is True
            assert "items" in result
            assert result["total_count"] == 3
            assert result["path"] == "/"
            assert len(result["items"]) == 3

            # Check folder item
            folder = result["items"][0]
            assert folder["id"] == "folder-123-abc"
            assert folder["name"] == "Documents"
            assert folder["type"] == "folder"
            assert folder["child_count"] == 5
            assert folder["mime_type"] is None

            # Check file item
            file_item = result["items"][1]
            assert file_item["id"] == "file-456-def"
            assert file_item["name"] == "report.xlsx"
            assert file_item["type"] == "file"
            assert file_item["size"] == 25600
            assert file_item["child_count"] is None

            # Verify API call for root
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/drive/root/children"

    def test_msgraph_list_drive_items_with_path(
        self, mock_context, mock_drive_items_data
    ):
        """Test listing items in a specific folder."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_drive_items_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context, path="/Documents/Reports")

            assert result["success"] is True
            assert result["path"] == "/Documents/Reports"

            # Verify API call uses path-based endpoint
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/drive/root:/Documents/Reports:/children"

    def test_msgraph_list_drive_items_with_limit(self, mock_context):
        """Test listing items with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context, limit=50)

            assert result["success"] is True

            # Verify limit parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 50

    def test_msgraph_list_drive_items_empty(self, mock_context):
        """Test listing an empty folder."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context, path="/EmptyFolder")

            assert result["success"] is True
            assert result["items"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_drive_items_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]


class TestMSGraphGetDriveItem:
    """Test suite for msgraph_get_drive_item tool."""

    def test_msgraph_get_drive_item_by_id(self, mock_context, mock_file_item_data):
        """Test getting item by ID."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_file_item_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_drive_item(mock_context, item_id="file-456-def")

            assert result["success"] is True
            assert "item" in result

            item = result["item"]
            assert item["id"] == "file-456-def"
            assert item["name"] == "report.xlsx"
            assert item["type"] == "file"
            assert item["size"] == 25600
            assert item["parent_path"] == "/Documents"

            # Verify API call uses item ID
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/me/drive/items/file-456-def" in call_args[0][0]

    def test_msgraph_get_drive_item_by_path(self, mock_context, mock_file_item_data):
        """Test getting item by path."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_file_item_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_drive_item(mock_context, path="/Documents/report.xlsx")

            assert result["success"] is True
            assert result["item"]["name"] == "report.xlsx"

            # Verify API call uses path-based endpoint
            call_args = mock_client.get.call_args
            assert "/me/drive/root:/Documents/report.xlsx" in call_args[0][0]

    def test_msgraph_get_drive_item_folder(self, mock_context, mock_folder_item_data):
        """Test getting a folder item."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_folder_item_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_drive_item(mock_context, item_id="folder-123-abc")

            assert result["success"] is True
            assert result["item"]["type"] == "folder"
            assert result["item"]["child_count"] == 5

    def test_msgraph_get_drive_item_no_identifier(self, mock_context):
        """Test validation error when neither item_id nor path is provided."""
        result = msgraph_get_drive_item(mock_context)

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "Either item_id or path must be provided" in result["error"]

    def test_msgraph_get_drive_item_not_found(self, mock_context):
        """Test handling of item not found error."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Item not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_drive_item(mock_context, item_id="nonexistent-id")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphDownloadFile:
    """Test suite for msgraph_download_file tool."""

    def test_msgraph_download_file(self, mock_context, mock_text_file_data):
        """Test downloading a text file."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_text_file_data
            mock_client.get_raw.return_value = b"Hello, World!\nThis is a test file."
            mock_get_client.return_value = mock_client

            result = msgraph_download_file(mock_context, item_id="text-file-123")

            assert result["success"] is True
            assert "content" in result
            assert result["content"] == "Hello, World!\nThis is a test file."
            assert result["encoding"] == "text"
            assert "metadata" in result
            assert result["metadata"]["name"] == "notes.txt"
            assert result["metadata"]["size"] == 100
            assert result["metadata"]["mime_type"] == "text/plain"

    def test_msgraph_download_file_by_path(self, mock_context, mock_text_file_data):
        """Test downloading a file by path."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_text_file_data
            mock_client.get_raw.return_value = b"File content here"
            mock_get_client.return_value = mock_client

            result = msgraph_download_file(mock_context, path="/Documents/notes.txt")

            assert result["success"] is True
            assert result["content"] == "File content here"

            # Verify path-based endpoint was used for metadata
            call_args = mock_client.get.call_args
            assert "/me/drive/root:/Documents/notes.txt" in call_args[0][0]

    def test_msgraph_download_file_binary(self, mock_context):
        """Test downloading a binary file (returns base64)."""
        binary_file_data = {
            "id": "binary-file-123",
            "name": "image.png",
            "size": 500,
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "file": {"mimeType": "image/png"},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = binary_file_data
            # Binary content
            mock_client.get_raw.return_value = b"\x89PNG\r\n\x1a\n\x00\x00"
            mock_get_client.return_value = mock_client

            result = msgraph_download_file(mock_context, item_id="binary-file-123")

            assert result["success"] is True
            assert result["encoding"] == "base64"
            # Content should be base64 encoded
            assert result["content"] == "iVBORw0KGgoAAA=="

    def test_msgraph_download_file_size_limit(self, mock_context):
        """Test max size enforcement when file is too large."""
        large_file_data = {
            "id": "large-file-123",
            "name": "huge_video.mp4",
            "size": 50 * 1024 * 1024,  # 50 MB
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "file": {"mimeType": "video/mp4"},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = large_file_data
            mock_get_client.return_value = mock_client

            # Default max_size_mb is 10
            result = msgraph_download_file(mock_context, item_id="large-file-123")

            assert result["success"] is False
            assert result["error_type"] == "file_too_large"
            assert "50.00 MB" in result["error"]
            assert "exceeds maximum" in result["error"]
            assert result["file_size_mb"] == 50.0

    def test_msgraph_download_file_custom_size_limit(self, mock_context):
        """Test custom max size parameter."""
        medium_file_data = {
            "id": "medium-file-123",
            "name": "video.mp4",
            "size": 15 * 1024 * 1024,  # 15 MB
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "file": {"mimeType": "video/mp4"},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = medium_file_data
            mock_client.get_raw.return_value = b"video content"
            mock_get_client.return_value = mock_client

            # Increase the limit to 20 MB
            result = msgraph_download_file(
                mock_context, item_id="medium-file-123", max_size_mb=20
            )

            assert result["success"] is True

    def test_msgraph_download_file_folder_error(self, mock_context):
        """Test error when trying to download a folder."""
        folder_data = {
            "id": "folder-123",
            "name": "MyFolder",
            "size": 0,
            "folder": {"childCount": 10},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = folder_data
            mock_get_client.return_value = mock_client

            result = msgraph_download_file(mock_context, item_id="folder-123")

            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert "Cannot download a folder" in result["error"]

    def test_msgraph_download_file_no_identifier(self, mock_context):
        """Test validation error when neither item_id nor path is provided."""
        result = msgraph_download_file(mock_context)

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "Either item_id or path must be provided" in result["error"]

    def test_msgraph_download_file_not_found(self, mock_context):
        """Test handling of file not found error."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("File not found")
            mock_get_client.return_value = mock_client

            result = msgraph_download_file(mock_context, path="/nonexistent.txt")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphUploadFile:
    """Test suite for msgraph_upload_file tool."""

    def test_msgraph_upload_file(self, mock_context):
        """Test uploading a file."""
        uploaded_item_response = {
            "id": "new-file-123",
            "name": "readme.txt",
            "size": 42,
            "lastModifiedDateTime": "2025-01-15T12:00:00Z",
            "createdDateTime": "2025-01-15T12:00:00Z",
            "webUrl": "https://walmart-my.sharepoint.com/readme.txt",
            "file": {"mimeType": "text/plain"},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.put.return_value = uploaded_item_response
            mock_get_client.return_value = mock_client

            result = msgraph_upload_file(
                mock_context,
                path="/Documents/readme.txt",
                content="This is the README content.",
            )

            assert result["success"] is True
            assert "item" in result
            assert result["item"]["id"] == "new-file-123"
            assert result["item"]["name"] == "readme.txt"
            assert result["item"]["size"] == 42

            # Verify API call
            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args
            assert call_args[0][0] == "/me/drive/root:/Documents/readme.txt:/content"
            assert call_args[1]["data"] == b"This is the README content."
            assert call_args[1]["headers"]["Content-Type"] == "text/plain"

    def test_msgraph_upload_file_custom_content_type(self, mock_context):
        """Test uploading with a custom content type."""
        uploaded_item_response = {
            "id": "json-file-123",
            "name": "data.json",
            "size": 100,
            "webUrl": "https://walmart-my.sharepoint.com/data.json",
            "file": {"mimeType": "application/json"},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.put.return_value = uploaded_item_response
            mock_get_client.return_value = mock_client

            result = msgraph_upload_file(
                mock_context,
                path="/data.json",
                content='{"key": "value"}',
                content_type="application/json",
            )

            assert result["success"] is True

            # Verify content type
            call_args = mock_client.put.call_args
            assert call_args[1]["headers"]["Content-Type"] == "application/json"

    def test_msgraph_upload_file_too_large(self, mock_context):
        """Test rejection of files over 4MB limit."""
        # Create content larger than 4MB
        large_content = "x" * (5 * 1024 * 1024)  # 5MB

        result = msgraph_upload_file(
            mock_context,
            path="/large_file.txt",
            content=large_content,
        )

        assert result["success"] is False
        assert result["error_type"] == "file_too_large"
        assert "exceeds simple upload limit" in result["error"]

    def test_msgraph_upload_file_auth_error(self, mock_context):
        """Test handling of authentication error during upload."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.put.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_upload_file(
                mock_context,
                path="/test.txt",
                content="test content",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphCreateFolder:
    """Test suite for msgraph_create_folder tool."""

    def test_msgraph_create_folder(self, mock_context):
        """Test creating a folder."""
        created_folder_response = {
            "id": "new-folder-123",
            "name": "NewFolder",
            "size": 0,
            "lastModifiedDateTime": "2025-01-15T12:00:00Z",
            "createdDateTime": "2025-01-15T12:00:00Z",
            "webUrl": "https://walmart-my.sharepoint.com/NewFolder",
            "folder": {"childCount": 0},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_folder_response
            mock_get_client.return_value = mock_client

            result = msgraph_create_folder(
                mock_context,
                path="/",
                name="NewFolder",
            )

            assert result["success"] is True
            assert "folder" in result
            assert result["folder"]["id"] == "new-folder-123"
            assert result["folder"]["name"] == "NewFolder"

            # Verify API call for root
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/drive/root/children"

            payload = call_args[1]["json"]
            assert payload["name"] == "NewFolder"
            assert "folder" in payload
            assert payload["@microsoft.graph.conflictBehavior"] == "fail"

    def test_msgraph_create_folder_in_path(self, mock_context):
        """Test creating a folder in a specific path."""
        created_folder_response = {
            "id": "subfolder-456",
            "name": "SubFolder",
            "size": 0,
            "webUrl": "https://walmart-my.sharepoint.com/Documents/SubFolder",
            "folder": {"childCount": 0},
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_folder_response
            mock_get_client.return_value = mock_client

            result = msgraph_create_folder(
                mock_context,
                path="/Documents",
                name="SubFolder",
            )

            assert result["success"] is True
            assert result["folder"]["name"] == "SubFolder"

            # Verify path-based endpoint
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/drive/root:/Documents:/children"

    def test_msgraph_create_folder_auth_error(self, mock_context):
        """Test handling of authentication error when creating folder."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_create_folder(
                mock_context,
                path="/",
                name="TestFolder",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphShareFile:
    """Test suite for msgraph_share_file tool."""

    def test_msgraph_share_file(self, mock_context, mock_share_link_response):
        """Test creating a sharing link."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_share_link_response
            mock_get_client.return_value = mock_client

            result = msgraph_share_file(
                mock_context,
                item_id="file-123-abc",
            )

            assert result["success"] is True
            assert "link" in result
            assert (
                result["link"]["url"]
                == "https://walmart-my.sharepoint.com/:x:/g/personal/user/Eabc123"
            )
            assert result["link"]["type"] == "view"
            assert result["link"]["scope"] == "organization"
            assert result["item_id"] == "file-123-abc"

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/drive/items/file-123-abc/createLink"

            payload = call_args[1]["json"]
            assert payload["type"] == "view"
            assert payload["scope"] == "organization"

    def test_msgraph_share_file_edit_link(self, mock_context):
        """Test creating an edit sharing link."""
        edit_link_response = {
            "link": {
                "webUrl": "https://walmart-my.sharepoint.com/:x:/g/personal/user/Eedit123",
                "type": "edit",
                "scope": "organization",
            }
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = edit_link_response
            mock_get_client.return_value = mock_client

            result = msgraph_share_file(
                mock_context,
                item_id="file-123-abc",
                share_type="edit",
            )

            assert result["success"] is True
            assert result["link"]["type"] == "edit"

            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["type"] == "edit"

    def test_msgraph_share_file_anonymous_scope(self, mock_context):
        """Test creating an anonymous sharing link."""
        anon_link_response = {
            "link": {
                "webUrl": "https://walmart-my.sharepoint.com/:x:/g/personal/user/Eanon123",
                "type": "view",
                "scope": "anonymous",
            }
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = anon_link_response
            mock_get_client.return_value = mock_client

            result = msgraph_share_file(
                mock_context,
                item_id="file-123-abc",
                scope="anonymous",
            )

            assert result["success"] is True
            assert result["link"]["scope"] == "anonymous"

    def test_msgraph_share_file_invalid_share_type(self, mock_context):
        """Test validation error for invalid share_type."""
        result = msgraph_share_file(
            mock_context,
            item_id="file-123-abc",
            share_type="invalid",
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "Invalid share_type" in result["error"]

    def test_msgraph_share_file_invalid_scope(self, mock_context):
        """Test validation error for invalid scope."""
        result = msgraph_share_file(
            mock_context,
            item_id="file-123-abc",
            scope="invalid_scope",
        )

        assert result["success"] is False
        assert result["error_type"] == "validation"
        assert "Invalid scope" in result["error"]

    def test_msgraph_share_file_auth_error(self, mock_context):
        """Test handling of authentication error when sharing."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_share_file(
                mock_context,
                item_id="file-123-abc",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphSearchFiles:
    """Test suite for msgraph_search_files tool."""

    def test_msgraph_search_files(self, mock_context, mock_drive_items_data):
        """Test searching files."""
        # Add parent reference to items for search results
        search_results = {
            "value": [
                {
                    **mock_drive_items_data["value"][1],
                    "parentReference": {"path": "/drive/root:/Documents"},
                },
                {
                    **mock_drive_items_data["value"][2],
                    "parentReference": {"path": "/drive/root:"},
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = search_results
            mock_get_client.return_value = mock_client

            result = msgraph_search_files(mock_context, query="report")

            assert result["success"] is True
            assert "items" in result
            assert result["total_count"] == 2
            assert result["query"] == "report"

            # Check items have parent_path
            assert result["items"][0]["parent_path"] == "/Documents"
            assert result["items"][1]["parent_path"] == ""

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/drive/root/search(q='report')"

    def test_msgraph_search_files_with_limit(self, mock_context):
        """Test searching files with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_search_files(mock_context, query="test", limit=25)

            assert result["success"] is True

            # Verify limit parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 25

    def test_msgraph_search_files_empty_results(self, mock_context):
        """Test search with no matching results."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_search_files(mock_context, query="xyznonexistent123")

            assert result["success"] is True
            assert result["items"] == []
            assert result["total_count"] == 0

    def test_msgraph_search_files_auth_error(self, mock_context):
        """Test handling of authentication error during search."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_search_files(mock_context, query="test")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphDeleteDriveItem:
    """Test suite for msgraph_delete_drive_item tool."""

    def test_msgraph_delete_drive_item(self, mock_context):
        """Test deleting an item."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.return_value = None  # DELETE returns no content
            mock_get_client.return_value = mock_client

            result = msgraph_delete_drive_item(mock_context, item_id="file-123-abc")

            assert result["success"] is True
            assert result["message"] == "Item deleted successfully"
            assert result["item_id"] == "file-123-abc"

            # Verify API call
            mock_client.delete.assert_called_once()
            call_args = mock_client.delete.call_args
            assert call_args[0][0] == "/me/drive/items/file-123-abc"

    def test_msgraph_delete_drive_item_not_found(self, mock_context):
        """Test handling of item not found error during deletion."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.side_effect = MSGraphNotFoundError("Item not found")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_drive_item(mock_context, item_id="nonexistent-id")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_delete_drive_item_auth_error(self, mock_context):
        """Test handling of authentication error during deletion."""
        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_drive_item(mock_context, item_id="file-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphOneDriveFormatting:
    """Test suite for drive item data formatting."""

    def test_file_item_formatting(self, mock_context):
        """Verify file item fields are properly mapped."""
        file_data = {
            "value": [
                {
                    "id": "file-id-123",
                    "name": "document.docx",
                    "size": 50000,
                    "lastModifiedDateTime": "2025-01-15T10:00:00Z",
                    "createdDateTime": "2025-01-10T08:00:00Z",
                    "webUrl": "https://sharepoint.com/document.docx",
                    "file": {
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    },
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = file_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context)

            item = result["items"][0]
            assert item["id"] == "file-id-123"
            assert item["name"] == "document.docx"
            assert item["type"] == "file"
            assert item["size"] == 50000
            assert item["last_modified"] == "2025-01-15T10:00:00Z"
            assert item["created"] == "2025-01-10T08:00:00Z"
            assert item["web_url"] == "https://sharepoint.com/document.docx"
            assert (
                item["mime_type"]
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            assert item["child_count"] is None

    def test_folder_item_formatting(self, mock_context):
        """Verify folder item fields are properly mapped."""
        folder_data = {
            "value": [
                {
                    "id": "folder-id-456",
                    "name": "Projects",
                    "size": 0,
                    "lastModifiedDateTime": "2025-01-14T09:00:00Z",
                    "createdDateTime": "2025-01-01T12:00:00Z",
                    "webUrl": "https://sharepoint.com/Projects",
                    "folder": {"childCount": 15},
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = folder_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context)

            item = result["items"][0]
            assert item["id"] == "folder-id-456"
            assert item["name"] == "Projects"
            assert item["type"] == "folder"
            assert item["child_count"] == 15
            assert item["mime_type"] is None

    def test_unknown_item_type_formatting(self, mock_context):
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
            "code_puppy.tools.msgraph.onedrive.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = unknown_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_drive_items(mock_context)

            item = result["items"][0]
            assert item["type"] == "unknown"
            assert item["child_count"] is None
            assert item["mime_type"] is None
