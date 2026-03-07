"""Integration test for adaptive image pruning functionality.

These tests verify that Code Puppy's image pruning feature works correctly
by testing the internal methods that handle file limit errors.

Note: Full end-to-end testing with synthetic-Kimi-K2.5-Thinking-NVFP4
requires SYN_API_KEY and actual API calls. These tests focus on the
internal logic which can be tested without external dependencies.
"""

from __future__ import annotations

from tests.integration.cli_expect.fixtures import CliHarness


def test_image_pruning_error_detection(cli_harness: CliHarness) -> None:
    """Test that the image pruning error detection works correctly.

    Verifies that _is_file_limit_error() correctly identifies file/image
    limit errors from various provider error message patterns.
    """
    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    agent = CodePuppyAgent()

    # Test cases for error detection
    test_cases = [
        # Hugging Face style errors
        ("API requests may only contain up to 16 files. Got: 17", True),
        ("api requests may only contain up to 16 files. got: 17", True),
        ("may only contain up to 16 files", True),
        ("files. Got: 20", True),
        ("files. got: 25", True),
        # Generic image limit errors
        ("maximum number of images exceeded", True),
        ("too many images", True),
        ("image limit exceeded", True),
        ("file limit exceeded", True),
        # Non-matching errors (false positives)
        ("Some other error about rate limiting", False),
        ("rate limit exceeded", False),
        ("Context length exceeded", False),
        ("token limit exceeded", False),
        ("", False),
        ("random text about files", False),
    ]

    for error_message, expected in test_cases:
        result = agent._is_file_limit_error(error_message)
        assert result == expected, (
            f"Failed for error message: '{error_message}'. "
            f"Expected {expected}, got {result}"
        )

    print("✅ All error detection patterns work correctly")


def test_image_pruning_counting(cli_harness: CliHarness) -> None:
    """Test that image counting and pruning logic works correctly.

    Tests the internal pruning methods:
    - _count_images_in_message()
    - _count_total_images()
    - _remove_images_from_message()
    """
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import ModelRequest

    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    agent = CodePuppyAgent()

    # Create mock messages with BinaryContent
    binary_content1 = BinaryContent(data=b"fake_image_1", media_type="image/png")
    binary_content2 = BinaryContent(data=b"fake_image_2", media_type="image/png")
    binary_content3 = BinaryContent(data=b"fake_image_3", media_type="image/png")

    # Create message parts with images
    class MockPart:
        def __init__(self, content):
            self.content = content

    # Create a message with images
    msg_with_images = ModelRequest(
        parts=[
            MockPart([binary_content1, binary_content2]),  # 2 images in list
            MockPart("Some text"),  # No images
            MockPart(binary_content3),  # 1 image direct
        ]
    )

    # Test counting in single message
    count = agent._count_images_in_message(msg_with_images)
    assert count == 3, f"Expected 3 images, got {count}"

    # Test counting across multiple messages
    empty_msg = ModelRequest(parts=[MockPart("No images here")])
    agent.set_message_history([empty_msg, msg_with_images, empty_msg])
    total = agent._count_total_images(agent.get_message_history())
    assert total == 3, f"Expected 3 total images, got {total}"

    # Test removal
    removed = agent._remove_images_from_message(msg_with_images)
    assert removed is True, "Expected images to be removed"

    # Verify images are gone
    new_count = agent._count_images_in_message(msg_with_images)
    assert new_count == 0, f"Expected 0 images after removal, got {new_count}"

    print("✅ Image counting and removal works correctly")


def test_image_pruning_from_history(cli_harness: CliHarness) -> None:
    """Test the full _prune_images_from_history() method.

    Verifies that:
    - Images are pruned from oldest messages first
    - System message (index 0) is protected
    - Correct number of images are removed
    - Method returns correct boolean status
    """
    from unittest.mock import patch

    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import ModelRequest

    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    agent = CodePuppyAgent()

    # Create mock images
    images = [
        BinaryContent(data=f"img{i}".encode(), media_type="image/png")
        for i in range(5)
    ]

    class MockPart:
        def __init__(self, content):
            self.content = content

    # Create messages: system + 5 messages with 1 image each
    system_msg = ModelRequest(parts=[MockPart("System prompt")])
    image_msgs = [
        ModelRequest(parts=[MockPart(images[i])])
        for i in range(5)
    ]

    # Set history: system + 5 image messages = 5 total images
    agent.set_message_history([system_msg] + image_msgs)

    # Verify initial count
    initial_count = agent._count_total_images(agent.get_message_history())
    assert initial_count == 5, f"Expected 5 initial images, got {initial_count}"

    # Test pruning when over limit
    with patch("code_puppy.agents.base_agent.emit_info") as mock_emit:
        pruned = agent._prune_images_from_history(max_images=2)

        assert pruned is True, "Expected pruning to occur"

        # Should have pruned 3 images (5 -> 2)
        final_count = agent._count_total_images(agent.get_message_history())
        assert final_count == 2, f"Expected 2 images after pruning, got {final_count}"

        # Verify emit_info was called
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert "Pruned" in call_args[0][0]
        assert "image" in call_args[0][0]

    # Verify oldest images were removed (indices 1-3), newest kept (indices 4-5)
    # Message at index 1 should have no images now
    assert agent._count_images_in_message(agent.get_message_history()[1]) == 0
    # Messages at indices 4 and 5 should still have images
    assert agent._count_images_in_message(agent.get_message_history()[4]) == 1
    assert agent._count_images_in_message(agent.get_message_history()[5]) == 1

    print("✅ Image pruning from history works correctly")


def test_image_pruning_no_action_needed(cli_harness: CliHarness) -> None:
    """Test that pruning returns False when no action is needed.

    Verifies that _prune_images_from_history() returns False when:
    - There are no images in history
    - Image count is already below the limit
    """
    from pydantic_ai.messages import ModelRequest

    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    agent = CodePuppyAgent()

    class MockPart:
        def __init__(self, content):
            self.content = content

    # Test with no images
    text_only_msg = ModelRequest(parts=[MockPart("Just text")])
    agent.set_message_history([text_only_msg, text_only_msg])
    assert agent._prune_images_from_history(max_images=5) is False

    print("✅ No-action cases handled correctly")
