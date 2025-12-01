"""Unit tests for confluence_tools module, focusing on pagination."""

import pytest
from unittest.mock import Mock, patch
from code_puppy.tools.confluence_tools import (
    confluence_read_page,
    MAX_CHARACTER_LIMIT,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_page_data():
    """Create mock page data with known content length."""
    # Create content that's exactly 50000 characters when converted
    # Use a pattern that differs at different positions for offset testing
    # Pattern: "0000...1111...2222..." etc, each digit repeated 5000 times
    content_chars = "".join(str(i % 10) * 5000 for i in range(10))
    return {
        "title": "Test Page",
        "space": {"key": "TEST"},
        "version": {"number": 1},
        "_links": {"webui": "/pages/123"},
        "body": {
            "storage": {
                "value": f"<p>{content_chars}</p>"
            }
        }
    }


@pytest.fixture
def mock_small_page_data():
    """Create mock page data with small content."""
    return {
        "title": "Small Page",
        "space": {"key": "TEST"},
        "version": {"number": 1},
        "_links": {"webui": "/pages/456"},
        "body": {
            "storage": {
                "value": "<p>Hello World</p>"
            }
        }
    }


class TestConfluenceReadPagePagination:
    """Test suite for confluence_read_page pagination functionality."""

    def test_default_limit_applied(self, mock_context, mock_page_data):
        """Test that default character limit is applied for large pages."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(mock_context, "123")

            assert result["success"] is True
            assert result["content_truncated"] is True
            assert len(result["content"]) <= MAX_CHARACTER_LIMIT
            assert result["total_content_length"] > MAX_CHARACTER_LIMIT
            assert result["remaining_content_length"] > 0
            assert result["character_offset"] == 0
            assert result["character_limit"] == MAX_CHARACTER_LIMIT

    def test_custom_limit_applied(self, mock_context, mock_page_data):
        """Test that custom character limit is applied."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(
                mock_context, "123", character_limit=10000
            )

            assert result["success"] is True
            assert result["content_truncated"] is True
            assert len(result["content"]) <= 10000
            assert result["character_limit"] == 10000

    def test_limit_clamped_to_max(self, mock_context, mock_page_data):
        """Test that character limit is clamped to MAX_CHARACTER_LIMIT."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_page_data
            MockClient.return_value = mock_client

            # Try to set limit higher than max
            result = confluence_read_page(
                mock_context, "123", character_limit=100000
            )

            assert result["success"] is True
            assert result["character_limit"] == MAX_CHARACTER_LIMIT

    def test_offset_pagination(self, mock_context, mock_page_data):
        """Test reading with character offset for pagination."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_page_data
            MockClient.return_value = mock_client

            # Read first chunk
            result1 = confluence_read_page(
                mock_context, "123", character_limit=20000
            )

            assert result1["success"] is True
            assert result1["character_offset"] == 0
            assert result1["content_truncated"] is True

            # Read second chunk using offset
            result2 = confluence_read_page(
                mock_context, "123", character_limit=20000, character_offset=20000
            )

            assert result2["success"] is True
            assert result2["character_offset"] == 20000
            # Content should be different
            assert result1["content"] != result2["content"]

    def test_small_page_not_truncated(self, mock_context, mock_small_page_data):
        """Test that small pages are not marked as truncated."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_small_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(mock_context, "456")

            assert result["success"] is True
            assert result["content_truncated"] is False
            assert result["remaining_content_length"] == 0
            assert "Hello World" in result["content"]

    def test_negative_offset_normalized(self, mock_context, mock_small_page_data):
        """Test that negative offset is normalized to 0."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_small_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(
                mock_context, "456", character_offset=-100
            )

            assert result["success"] is True
            assert result["character_offset"] == 0

    def test_offset_beyond_content_returns_empty(self, mock_context, mock_small_page_data):
        """Test that offset beyond content length returns empty content."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_small_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(
                mock_context, "456", character_offset=100000
            )

            assert result["success"] is True
            assert result["content"] == ""
            assert result["content_truncated"] is False
            assert result["remaining_content_length"] == 0

    def test_zero_limit_uses_default(self, mock_context, mock_page_data):
        """Test that character_limit=0 uses the default max."""
        with patch(
            "code_puppy.tools.confluence_tools.ConfluenceClient"
        ) as MockClient:
            mock_client = Mock()
            mock_client.get_page_content.return_value = mock_page_data
            MockClient.return_value = mock_client

            result = confluence_read_page(
                mock_context, "123", character_limit=0
            )

            assert result["success"] is True
            assert result["character_limit"] == MAX_CHARACTER_LIMIT


class TestMaxCharacterLimitConstant:
    """Test the MAX_CHARACTER_LIMIT constant."""

    def test_max_limit_is_reasonable(self):
        """Ensure MAX_CHARACTER_LIMIT is set to a reasonable value."""
        # Should be large enough to be useful but not blow context
        assert MAX_CHARACTER_LIMIT >= 10000
        assert MAX_CHARACTER_LIMIT <= 50000
        # Current expected value
        assert MAX_CHARACTER_LIMIT == 30000


class TestConfluenceAuthHelpFormat:
    """Test that confluence_auth help returns correct format for autocomplete."""

    def test_help_returns_list_of_tuples(self):
        """Ensure get_confluence_auth_help returns List[Tuple[str, str]]."""
        from code_puppy.plugins.walmart_specific.confluence_auth import (
            get_confluence_auth_help,
        )

        result = get_confluence_auth_help()

        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)  # command name
            assert isinstance(item[1], str)  # description

    def test_help_contains_confluence_auth_command(self):
        """Ensure the help includes the confluence_auth command."""
        from code_puppy.plugins.walmart_specific.confluence_auth import (
            get_confluence_auth_help,
        )

        result = get_confluence_auth_help()
        command_names = [item[0] for item in result]

        assert "confluence_auth" in command_names
