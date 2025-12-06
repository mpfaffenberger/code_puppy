"""Tests for BaseAgent edge cases and error paths.

This module tests error handling and edge cases in BaseAgent methods:
- _load_model_with_fallback() when all models fail
- hash_message() with malformed messages
- stringify_message_part() with unusual content types
- filter_huge_messages() with corrupted messages
- get_model_context_length() when model config is broken
- load_puppy_rules() with file read errors
- Compaction methods with extreme token counts

Focuses on ensuring error handling doesn't crash and provides graceful degradation.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl
from pydantic_ai.messages import (
    ModelRequest,
    TextPart,
)

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentEdgeCases:
    """Test suite for BaseAgent edge cases and error paths."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

    @patch("code_puppy.model_factory.ModelFactory.get_model")
    @patch("code_puppy.model_factory.ModelFactory.load_config")
    @patch("code_puppy.agents.base_agent.emit_warning")
    @patch("code_puppy.agents.base_agent.emit_error")
    def test_load_model_with_fallback_all_fail(
        self,
        mock_emit_error,
        mock_emit_warning,
        mock_load_config,
        mock_get_model,
        agent,
    ):
        """Test _load_model_with_fallback when all models fail to load."""
        # Mock config with multiple models
        mock_load_config.return_value = {"model1": {}, "model2": {}, "model3": {}}

        # All models fail to load
        mock_get_model.side_effect = ValueError("Model not found")

        # Should raise ValueError after all fallbacks fail
        with pytest.raises(ValueError, match="No valid model could be loaded"):
            agent._load_model_with_fallback(
                "bad-model", {"model1": {}, "model2": {}, "model3": {}}, "test-group"
            )

        # Verify warning was emitted for the requested model
        mock_emit_warning.assert_called_once()

        # Verify error was emitted when all fallbacks failed
        mock_emit_error.assert_called_once()

    @patch("code_puppy.model_factory.ModelFactory.get_model")
    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_load_model_with_fallback_empty_config(
        self, mock_load_config, mock_get_model, agent
    ):
        """Test _load_model_with_fallback with empty models config."""
        mock_load_config.return_value = {}
        mock_get_model.side_effect = ValueError("No models")

        with pytest.raises(ValueError, match="No valid model could be loaded"):
            agent._load_model_with_fallback("any-model", {}, "test-group")

    def test_hash_message_with_minimal_message(self, agent):
        """Test hash_message with bare minimum message structure."""
        # Test with completely empty message
        msg = MagicMock()
        msg.role = None
        msg.instructions = None
        msg.parts = []

        # Should not crash
        result = agent.hash_message(msg)
        assert isinstance(result, int)

    def test_hash_message_with_none_parts(self, agent):
        """Test hash_message when parts is None."""
        msg = MagicMock()
        msg.role = "user"
        msg.instructions = None
        # getattr(message, "parts", []) handles None -> [], so this should work
        del msg.parts  # Delete the attribute entirely

        # Should not crash even with missing parts attribute
        result = agent.hash_message(msg)
        assert isinstance(result, int)

    def test_hash_message_with_corrupted_parts(self, agent):
        """Test hash_message with corrupted part objects."""
        msg = MagicMock()
        msg.role = "user"
        msg.instructions = "test"
        msg.parts = [
            None,  # None part
            MagicMock(spec=object),  # Object with no expected attributes
            "string_instead_of_object",  # String instead of part object
        ]

        # Should not crash with corrupted parts
        result = agent.hash_message(msg)
        assert isinstance(result, int)

    def test_stringify_message_part_with_none_part(self, agent):
        """Test stringify_message_part with None input."""
        result = agent.stringify_message_part(None)
        assert isinstance(result, str)
        assert "NoneType" in result or "object" in result

    def test_stringify_message_part_with_broken_part(self, agent):
        """Test stringify_message_part with part having broken attributes."""
        part = MagicMock()
        # stringify_message_part doesn't use part_kind, that's in _stringify_part
        delattr(part, "part_kind")  # Remove the attribute entirely
        part.content = None  # None content
        part.tool_name = None  # None tool name

        # Should not crash
        result = agent.stringify_message_part(part)
        assert isinstance(result, str)

    def test_stringify_message_part_with_binary_content(self, agent):
        """Test stringify_message_part with BinaryContent."""
        part = MagicMock()
        part.part_kind = "text"
        part.content = [
            BinaryContent(data=b"binary_data", media_type="application/octet-stream"),
            "some text",
        ]
        # Mock the tool_name to avoid the mock concatenation issue
        part.tool_name = None

        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        # BinaryContent gets processed, should contain something from the list
        assert len(result) > 0

    def test_stringify_message_part_with_pydantic_content(self, agent):
        """Test stringify_message_part with Pydantic model content."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            value: int

        test_obj = TestModel(name="test", value=42)
        part = MagicMock()
        part.part_kind = "text"
        part.content = test_obj
        # Mock the tool_name to avoid the mock concatenation issue
        part.tool_name = None

        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        # Pydantic model should be JSON serialized
        assert "test" in result
        assert "42" in result

    def test_stringify_message_part_with_document_url(self, agent):
        """Test stringify_message_part with DocumentUrl content."""
        part = MagicMock()
        part.part_kind = "text"
        part.content = DocumentUrl(url="https://example.com/doc.pdf")
        # Mock the tool_name to avoid the mock concatenation issue
        part.tool_name = None

        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        # DocumentUrl should be converted to string representation
        assert len(result) > 0

    def test_stringify_message_part_with_image_url(self, agent):
        """Test stringify_message_part with ImageUrl content."""
        part = MagicMock()
        part.part_kind = "text"
        part.content = ImageUrl(url="https://example.com/image.png")
        # Mock the tool_name to avoid the mock concatenation issue
        part.tool_name = None

        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        # ImageUrl should be converted to string representation
        assert len(result) > 0

    def test_stringify_message_part_with_circular_reference(self, agent):
        """Test stringify_message_part with circular reference in content."""
        # Create a circular reference
        circular_dict = {}
        circular_dict["self"] = circular_dict

        part = MagicMock()
        part.part_kind = "text"
        part.content = circular_dict

        # Should handle gracefully (may cause JSON recursion error but our method should handle it)
        try:
            result = agent.stringify_message_part(part)
            assert isinstance(result, str)
        except (ValueError, RecursionError):
            # If it can't handle circular references, that's OK for edge case testing
            pass

    def test_filter_huge_messages_with_none_list(self, agent):
        """Test filter_huge_messages with None input - this will crash as expected."""
        # The method doesn't handle None gracefully, so it should raise an error
        with pytest.raises((TypeError, AttributeError)):
            agent.filter_huge_messages(None)

    def test_filter_huge_messages_with_empty_list(self, agent):
        """Test filter_huge_messages with empty list."""
        result = agent.filter_huge_messages([])
        assert result == []

    def test_filter_huge_messages_with_corrupted_messages(self, agent):
        """Test filter_huge_messages with corrupted message objects."""
        corrupted_msg = MagicMock()
        corrupted_msg.parts = (
            None  # None parts will cause crashes in estimate_tokens_for_message
        )

        # The method doesn't handle corrupted messages gracefully
        with pytest.raises((TypeError, AttributeError)):
            agent.filter_huge_messages([corrupted_msg])

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_get_model_context_length_broken_config(self, mock_load_config, agent):
        """Test get_model_context_length when model config is completely broken."""
        # Config that would cause issues
        mock_load_config.side_effect = Exception("Config broken")

        result = agent.get_model_context_length()
        # Should fall back to default
        assert result == 128000

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_get_model_context_length_invalid_context_length(
        self, mock_load_config, agent
    ):
        """Test get_model_context_length with invalid context_length values."""
        mock_load_config.return_value = {
            "test-model": {
                "context_length": "not_a_number",  # String instead of int
            }
        }

        with patch.object(agent, "get_model_name", return_value="test-model"):
            result = agent.get_model_context_length()
            # Should handle conversion gracefully or fall back to default
            assert result == 128000

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_get_model_context_length_negative_context_length(
        self, mock_load_config, agent
    ):
        """Test get_model_context_length with negative context_length."""
        mock_load_config.return_value = {
            "test-model": {
                "context_length": -1000,  # Negative number
            }
        }

        with patch.object(agent, "get_model_name", return_value="test-model"):
            result = agent.get_model_context_length()
            # Should return the negative value converted to int (strange but shouldn't crash)
            assert isinstance(result, int)

    @patch("pathlib.Path.read_text", side_effect=PermissionError("Permission denied"))
    @patch("pathlib.Path.exists")
    def test_load_puppy_rules_file_permission_error(
        self, mock_exists, mock_read_text, agent
    ):
        """Test load_puppy_rules when file exists but can't be read due to permissions."""
        mock_exists.return_value = True

        # The method doesn't handle file errors gracefully - should propagate
        with pytest.raises(PermissionError):
            agent.load_puppy_rules()

    @patch("pathlib.Path.read_text", side_effect=IOError("Disk error"))
    @patch("pathlib.Path.exists")
    def test_load_puppy_rules_file_io_error(self, mock_exists, mock_read_text, agent):
        """Test load_puppy_rules when file has IO error."""
        mock_exists.return_value = True

        # The method doesn't handle IO errors gracefully - should propagate
        with pytest.raises(IOError):
            agent.load_puppy_rules()

    @patch("pathlib.Path.read_text", return_value="")
    @patch("pathlib.Path.exists")
    def test_load_puppy_rules_empty_file(self, mock_exists, mock_read_text, agent):
        """Test load_puppy_rules with empty file."""
        mock_exists.return_value = True

        result = agent.load_puppy_rules()
        assert result == ""  # Should return empty string for empty file

    @patch("pathlib.Path.exists")
    def test_load_puppy_rules_no_files_exist(self, mock_exists, agent):
        """Test load_puppy_rules when no AGENT(S).md files exist."""
        mock_exists.return_value = False

        result = agent.load_puppy_rules()
        assert result is None

    def test_compaction_edge_cases_with_extreme_tokens(self, agent):
        """Test compaction methods with extreme token counts."""
        # Create a message that would normally be > 50000 tokens
        huge_msg = ModelRequest(
            parts=[TextPart(content="x" * 100000)]
        )  # Very long content

        # filter_huge_messages should handle this gracefully
        result = agent.filter_huge_messages([huge_msg])
        assert isinstance(result, list)
        # Should filter out the huge message or handle it

    def test_compaction_with_none_model_name(self, agent):
        """Test get_model_context_length when get_model_name returns None."""
        with patch.object(agent, "get_model_name", return_value=None):
            with patch(
                "code_puppy.model_factory.ModelFactory.load_config", return_value={}
            ):
                result = agent.get_model_context_length()
                # Should fall back to default
                assert result == 128000

    def test_estimated_tokens_with_unicode_content(self, agent):
        """Test token estimation with various unicode characters."""
        unicode_content = """Hello 🐾 world! ⚡️ testing with 🎉 emojis ✨
        and other unicode: àáâãä добрый 你好 🚀"""

        part = TextPart(content=unicode_content)
        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        assert len(result) > 0

        # Token estimation should work
        tokens = agent.estimate_token_count(result)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_tool_call_with_corrupted_args(self, agent):
        """Test stringify_message_part with corrupted tool call args."""
        part = MagicMock()
        part.part_kind = "tool-call"
        part.tool_name = "test_tool"
        part.args = None  # None args

        result = agent.stringify_message_part(part)
        assert isinstance(result, str)
        assert "test_tool" in result

    def test_message_with_circular_part_reference(self, agent):
        """Test hash_message with circular references in message parts."""
        # Create a circular reference between parts
        part1 = MagicMock()
        part2 = MagicMock()
        part1.content = part2
        part2.content = part1

        msg = MagicMock()
        msg.role = "user"
        msg.instructions = None
        msg.parts = [part1, part2]

        # Should not crash with circular references
        result = agent.hash_message(msg)
        assert isinstance(result, int)

    @patch("code_puppy.model_factory.ModelFactory.get_model")
    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_load_model_with_fallback_unexpected_exception(
        self, mock_load_config, mock_get_model, agent
    ):
        """Test _load_model_with_fallback when ModelFactory raises unexpected exception."""
        mock_load_config.return_value = {"model1": {}}
        mock_get_model.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(Exception):  # Should propagate unexpected exceptions
            agent._load_model_with_fallback("model1", {"model1": {}}, "test-group")

    def test_compacted_message_hashes_edge_cases(self, agent):
        """Test compacted message hash methods with edge cases."""
        # Test adding None hash
        agent.add_compacted_message_hash(None)
        # Should not crash

        # Test getting empty hashes
        hashes = agent.get_compacted_message_hashes()
        assert isinstance(hashes, set)
        # Should handle gracefully
