"""Tests for BaseAgent adaptive image pruning functionality.

This module tests the image pruning methods added to BaseAgent for handling
file limit errors from model providers like Hugging Face.
"""

from unittest.mock import patch

import pytest
from pydantic_ai import BinaryContent

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class MockPart:
    """Mock message part for testing."""

    def __init__(self, content=None):
        self.content = content


class MockMessage:
    """Mock message for testing."""

    def __init__(self, parts=None):
        self.parts = parts or []


class TestIsFileLimitError:
    """Test suite for _is_file_limit_error method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    @pytest.mark.parametrize(
        "error_message,expected",
        [
            # Hugging Face style errors
            ("API requests may only contain up to 16 files. Got: 17", True),
            ("api requests may only contain up to 16 files. got: 17", True),
            ("May only contain up to 16 files", True),
            ("files. Got: 17", True),
            # Generic image limit errors
            ("maximum number of images exceeded", True),
            ("too many images", True),
            ("image limit exceeded", True),
            ("file limit exceeded", True),
            # Non-matching errors
            ("some other error", False),
            ("rate limit exceeded", False),
            ("context length exceeded", False),
            ("", False),
            ("random text about files", False),
        ],
    )
    def test_file_limit_error_detection(self, agent, error_message, expected):
        """Test detection of various file limit error patterns.

        Verifies that _is_file_limit_error correctly identifies file/image
        limit errors from different providers while avoiding false positives.
        """
        result = agent._is_file_limit_error(error_message)
        assert result == expected


class TestCountImagesInMessage:
    """Test suite for _count_images_in_message method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    def test_empty_message_no_images(self, agent):
        """Test counting images in a message with no parts."""
        msg = MockMessage(parts=[])
        assert agent._count_images_in_message(msg) == 0

    def test_message_with_text_only(self, agent):
        """Test counting images in a message with only text parts."""
        msg = MockMessage(parts=[MockPart(content="Hello world"), MockPart(content="More text")])
        assert agent._count_images_in_message(msg) == 0

    def test_message_with_single_image(self, agent):
        """Test counting images in a message with one BinaryContent."""
        binary_content = BinaryContent(data=b"fake_image_data", media_type="image/png")
        msg = MockMessage(parts=[MockPart(content=binary_content)])
        assert agent._count_images_in_message(msg) == 1

    def test_message_with_multiple_images_in_list(self, agent):
        """Test counting images in a message with multiple BinaryContents in a list."""
        binary_content1 = BinaryContent(data=b"fake_image_data1", media_type="image/png")
        binary_content2 = BinaryContent(data=b"fake_image_data2", media_type="image/png")
        text_part = MockPart(content="Some text")
        msg = MockMessage(
            parts=[MockPart(content=[binary_content1, text_part, binary_content2])]
        )
        assert agent._count_images_in_message(msg) == 2

    def test_message_with_mixed_content(self, agent):
        """Test counting images in a message with mixed content types."""
        binary_content = BinaryContent(data=b"fake_image_data", media_type="image/png")
        msg = MockMessage(
            parts=[
                MockPart(content="Text content"),
                MockPart(content=binary_content),
                MockPart(content=["list", "of", "strings"]),
            ]
        )
        assert agent._count_images_in_message(msg) == 1


class TestCountTotalImages:
    """Test suite for _count_total_images method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    def test_empty_history(self, agent):
        """Test counting images in empty message history."""
        assert agent._count_total_images([]) == 0

    def test_single_message_no_images(self, agent):
        """Test counting images with a single message containing no images."""
        msg = MockMessage(parts=[MockPart(content="No images here")])
        assert agent._count_total_images([msg]) == 0

    def test_multiple_messages_with_images(self, agent):
        """Test counting images across multiple messages."""
        binary_content1 = BinaryContent(data=b"img1", media_type="image/png")
        binary_content2 = BinaryContent(data=b"img2", media_type="image/png")
        binary_content3 = BinaryContent(data=b"img3", media_type="image/png")

        msg1 = MockMessage(parts=[MockPart(content=binary_content1)])
        msg2 = MockMessage(parts=[MockPart(content="Text only")])
        msg3 = MockMessage(
            parts=[MockPart(content=[binary_content2, binary_content3])]
        )

        assert agent._count_total_images([msg1, msg2, msg3]) == 3


class TestRemoveImagesFromMessage:
    """Test suite for _remove_images_from_message method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    def test_remove_no_images(self, agent):
        """Test removing images from a message with no images."""
        part = MockPart(content="Just text")
        msg = MockMessage(parts=[part])
        result = agent._remove_images_from_message(msg)
        assert result is False
        assert part.content == "Just text"

    def test_remove_single_image(self, agent):
        """Test removing a single BinaryContent from a message."""
        binary_content = BinaryContent(data=b"img", media_type="image/png")
        part = MockPart(content=binary_content)
        msg = MockMessage(parts=[part])
        result = agent._remove_images_from_message(msg)
        assert result is True
        assert part.content is None

    def test_remove_images_from_list(self, agent):
        """Test removing BinaryContents from a list while preserving other items."""
        binary_content = BinaryContent(data=b"img", media_type="image/png")
        text_item = "preserve this"
        part = MockPart(content=[binary_content, text_item])
        msg = MockMessage(parts=[part])
        result = agent._remove_images_from_message(msg)
        assert result is True
        assert part.content == [text_item]

    def test_remove_multiple_images(self, agent):
        """Test removing multiple BinaryContents from a message."""
        binary_content1 = BinaryContent(data=b"img1", media_type="image/png")
        binary_content2 = BinaryContent(data=b"img2", media_type="image/png")
        text_item = "text"
        part = MockPart(content=[binary_content1, text_item, binary_content2])
        msg = MockMessage(parts=[part])
        result = agent._remove_images_from_message(msg)
        assert result is True
        assert part.content == [text_item]


class TestPruneImagesFromHistory:
    """Test suite for _prune_images_from_history method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    def test_no_images_in_history(self, agent):
        """Test pruning when there are no images in history."""
        agent.set_message_history(
            [MockMessage(parts=[MockPart(content="No images")])]
        )
        result = agent._prune_images_from_history(max_images=5)
        assert result is False

    def test_images_below_limit(self, agent):
        """Test pruning when images are below the limit."""
        binary_content = BinaryContent(data=b"img", media_type="image/png")
        agent.set_message_history(
            [
                MockMessage(parts=[MockPart(content="System")]),  # Index 0 - protected
                MockMessage(parts=[MockPart(content=binary_content)]),
            ]
        )
        result = agent._prune_images_from_history(max_images=5)
        assert result is False

    @patch("code_puppy.agents.base_agent.emit_info")
    def test_prunes_oldest_images_first(self, mock_emit_info, agent):
        """Test that pruning removes images from oldest messages first."""
        # Create messages with images
        img1 = BinaryContent(data=b"img1", media_type="image/png")
        img2 = BinaryContent(data=b"img2", media_type="image/png")
        img3 = BinaryContent(data=b"img3", media_type="image/png")

        # System message (index 0, protected)
        system_msg = MockMessage(parts=[MockPart(content="System")])

        # Old message with image (should be pruned)
        old_msg = MockMessage(parts=[MockPart(content=img1)])

        # Middle message with image (should be pruned)
        middle_msg = MockMessage(parts=[MockPart(content=img2)])

        # Recent message with image (should be kept)
        recent_msg = MockMessage(parts=[MockPart(content=img3)])

        agent.set_message_history([system_msg, old_msg, middle_msg, recent_msg])

        # Prune to max 1 image
        result = agent._prune_images_from_history(max_images=1)

        assert result is True
        # Verify older images were removed
        assert old_msg.parts[0].content is None  # Pruned
        assert middle_msg.parts[0].content is None  # Pruned
        assert recent_msg.parts[0].content == img3  # Kept

    @patch("code_puppy.agents.base_agent.emit_info")
    def test_emits_info_message(self, mock_emit_info, agent):
        """Test that pruning emits an informative message."""
        img = BinaryContent(data=b"img", media_type="image/png")

        agent.set_message_history(
            [
                MockMessage(parts=[MockPart(content="System")]),
                MockMessage(parts=[MockPart(content=img)]),
                MockMessage(parts=[MockPart(content=img)]),
            ]
        )

        agent._prune_images_from_history(max_images=1)

        # Verify emit_info was called with the right message
        mock_emit_info.assert_called_once()
        call_args = mock_emit_info.call_args
        assert "Pruned" in call_args[0][0]
        assert "image_pruning" == call_args[1].get("message_group")


class TestRetryWithPrunedImages:
    """Test suite for _RetryWithPrunedImages exception."""

    def test_exception_is_raised(self):
        """Test that _RetryWithPrunedImages can be raised and caught."""
        from code_puppy.agents.base_agent import BaseAgent

        with pytest.raises(BaseAgent._RetryWithPrunedImages):
            raise BaseAgent._RetryWithPrunedImages()

    def test_exception_message(self):
        """Test that the exception can have a custom message."""
        from code_puppy.agents.base_agent import BaseAgent

        try:
            raise BaseAgent._RetryWithPrunedImages("Custom message")
        except BaseAgent._RetryWithPrunedImages as e:
            assert str(e) == "Custom message"
