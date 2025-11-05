"""Tests for agent tools functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

from code_puppy.tools.agent_tools import (
    _load_session_history,
    _save_session_history,
    _validate_session_id,
    register_invoke_agent,
    register_list_agents,
)


class TestAgentTools:
    """Test suite for agent tools."""

    def test_list_agents_tool(self):
        """Test that list_agents tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_list_agents(mock_agent)

    def test_invoke_agent_tool(self):
        """Test that invoke_agent tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_invoke_agent(mock_agent)

    def test_invoke_agent_includes_prompt_additions(self):
        """Test that invoke_agent includes prompt additions like file permission handling."""
        # Test that the fix properly adds prompt additions to temporary agents
        from unittest.mock import patch

        from code_puppy import callbacks
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            get_file_permission_prompt_additions,
        )

        # Mock yolo mode to be False so we can test prompt additions
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
            return_value=False,
        ):
            # Register the file permission callback (normally done at startup)
            callbacks.register_callback(
                "load_prompt", get_file_permission_prompt_additions
            )

            # Get prompt additions to verify they exist
            prompt_additions = callbacks.on_load_prompt()

            # Verify we have file permission prompt additions
            assert len(prompt_additions) > 0

            # Verify the content contains expected file permission instructions
            file_permission_text = "".join(prompt_additions)
            assert "FILE PERMISSION REJECTION" in file_permission_text
            assert "IMMEDIATE STOP" in file_permission_text


class TestSessionIdValidation:
    """Test suite for session ID validation."""

    def test_valid_single_word(self):
        """Test that single word session IDs are valid."""
        _validate_session_id("session")
        _validate_session_id("test")
        _validate_session_id("a")

    def test_valid_multiple_words(self):
        """Test that multi-word kebab-case session IDs are valid."""
        _validate_session_id("my-session")
        _validate_session_id("agent-session-1")
        _validate_session_id("discussion-about-code")
        _validate_session_id("very-long-session-name-with-many-words")

    def test_valid_with_numbers(self):
        """Test that session IDs with numbers are valid."""
        _validate_session_id("session1")
        _validate_session_id("session-123")
        _validate_session_id("test-2024-01-01")
        _validate_session_id("123-session")
        _validate_session_id("123")

    def test_invalid_uppercase(self):
        """Test that uppercase letters are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("MySession")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my-Session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("MY-SESSION")

    def test_invalid_underscores(self):
        """Test that underscores are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my_session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my-session_name")

    def test_invalid_spaces(self):
        """Test that spaces are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session name")

    def test_invalid_special_characters(self):
        """Test that special characters are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my@session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session!")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session.name")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session#1")

    def test_invalid_double_hyphens(self):
        """Test that double hyphens are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my--session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session--name")

    def test_invalid_leading_hyphen(self):
        """Test that leading hyphens are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("-session")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("-my-session")

    def test_invalid_trailing_hyphen(self):
        """Test that trailing hyphens are rejected."""
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("session-")
        with pytest.raises(ValueError, match="must be kebab-case"):
            _validate_session_id("my-session-")

    def test_invalid_empty_string(self):
        """Test that empty strings are rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_session_id("")

    def test_invalid_too_long(self):
        """Test that session IDs longer than 128 chars are rejected."""
        long_session_id = "a" * 129
        with pytest.raises(ValueError, match="must be 128 characters or less"):
            _validate_session_id(long_session_id)

    def test_valid_max_length(self):
        """Test that session IDs of exactly 128 chars are valid."""
        max_length_id = "a" * 128
        _validate_session_id(max_length_id)

    def test_edge_case_all_numbers(self):
        """Test that session IDs with only numbers are valid."""
        _validate_session_id("123456789")

    def test_edge_case_single_char(self):
        """Test that single character session IDs are valid."""
        _validate_session_id("a")
        _validate_session_id("1")


class TestSessionSaveLoad:
    """Test suite for session history save/load functionality."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_messages(self):
        """Create mock ModelMessage objects for testing."""
        return [
            ModelRequest(parts=[TextPart(content="Hello, can you help?")]),
            ModelResponse(parts=[TextPart(content="Sure, I can help!")]),
            ModelRequest(parts=[TextPart(content="What is 2+2?")]),
            ModelResponse(parts=[TextPart(content="2+2 equals 4.")]),
        ]

    def test_save_and_load_roundtrip(self, temp_session_dir, mock_messages):
        """Test successful save and load roundtrip of session history."""
        session_id = "test-session"
        agent_name = "test-agent"
        initial_prompt = "Hello, can you help?"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # Save the session
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=initial_prompt,
            )

            # Load it back
            loaded_messages = _load_session_history(session_id)

            # Verify the messages match
            assert len(loaded_messages) == len(mock_messages)
            for i, (loaded, original) in enumerate(zip(loaded_messages, mock_messages)):
                assert type(loaded) is type(original)
                assert loaded.parts == original.parts

    def test_load_nonexistent_session_returns_empty_list(self, temp_session_dir):
        """Test that loading a non-existent session returns an empty list."""
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            loaded_messages = _load_session_history("nonexistent-session")
            assert loaded_messages == []

    def test_save_with_invalid_session_id_raises_error(
        self, temp_session_dir, mock_messages
    ):
        """Test that saving with an invalid session ID raises ValueError."""
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            with pytest.raises(ValueError, match="must be kebab-case"):
                _save_session_history(
                    session_id="Invalid_Session",
                    message_history=mock_messages,
                    agent_name="test-agent",
                )

    def test_load_with_invalid_session_id_raises_error(self, temp_session_dir):
        """Test that loading with an invalid session ID raises ValueError."""
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            with pytest.raises(ValueError, match="must be kebab-case"):
                _load_session_history("Invalid_Session")

    def test_save_creates_pkl_and_txt_files(self, temp_session_dir, mock_messages):
        """Test that save creates both .pkl and .txt files."""
        session_id = "test-session"
        agent_name = "test-agent"
        initial_prompt = "Test prompt"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=initial_prompt,
            )

            # Check that both files exist
            pkl_file = temp_session_dir / f"{session_id}.pkl"
            txt_file = temp_session_dir / f"{session_id}.txt"
            assert pkl_file.exists()
            assert txt_file.exists()

    def test_txt_file_contains_readable_metadata(self, temp_session_dir, mock_messages):
        """Test that .txt file contains readable metadata."""
        session_id = "test-session"
        agent_name = "test-agent"
        initial_prompt = "Test prompt"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=initial_prompt,
            )

            # Read and verify metadata
            txt_file = temp_session_dir / f"{session_id}.txt"
            with open(txt_file, "r") as f:
                metadata = json.load(f)

            assert metadata["session_id"] == session_id
            assert metadata["agent_name"] == agent_name
            assert metadata["initial_prompt"] == initial_prompt
            assert metadata["message_count"] == len(mock_messages)
            assert "created_at" in metadata

    def test_txt_file_updates_on_subsequent_saves(
        self, temp_session_dir, mock_messages
    ):
        """Test that .txt file metadata updates on subsequent saves."""
        session_id = "test-session"
        agent_name = "test-agent"
        initial_prompt = "Test prompt"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # First save
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages[:2],
                agent_name=agent_name,
                initial_prompt=initial_prompt,
            )

            # Second save with more messages
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=None,  # Should not overwrite initial_prompt
            )

            # Read and verify metadata was updated
            txt_file = temp_session_dir / f"{session_id}.txt"
            with open(txt_file, "r") as f:
                metadata = json.load(f)

            # Initial prompt should still be there from first save
            assert metadata["initial_prompt"] == initial_prompt
            # Message count should be updated
            assert metadata["message_count"] == len(mock_messages)
            # last_updated should exist
            assert "last_updated" in metadata

    def test_load_handles_corrupted_pickle(self, temp_session_dir):
        """Test that loading a corrupted pickle file returns empty list."""
        session_id = "corrupted-session"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # Create a corrupted pickle file
            pkl_file = temp_session_dir / f"{session_id}.pkl"
            with open(pkl_file, "wb") as f:
                f.write(b"This is not a valid pickle file!")

            # Should return empty list instead of crashing
            loaded_messages = _load_session_history(session_id)
            assert loaded_messages == []

    def test_save_without_initial_prompt(self, temp_session_dir, mock_messages):
        """Test that save works without initial_prompt (subsequent saves)."""
        session_id = "test-session"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # First save WITH initial_prompt
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages[:2],
                agent_name=agent_name,
                initial_prompt="First prompt",
            )

            # Second save WITHOUT initial_prompt
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=None,
            )

            # Should still be able to load
            loaded_messages = _load_session_history(session_id)
            assert len(loaded_messages) == len(mock_messages)


class TestAutoGeneratedSessionIds:
    """Test suite for auto-generated session IDs."""

    def test_session_id_format(self):
        """Test that auto-generated session IDs follow the correct format."""
        # We can't directly test invoke_agent without a lot of mocking,
        # but we can test the format that would be generated
        agent_name = "qa-expert"
        counter = 1
        expected_format = f"{agent_name}-session-{counter}"

        # Verify it matches kebab-case pattern
        _validate_session_id(expected_format)

        # Verify the format matches expected pattern
        assert expected_format == "qa-expert-session-1"

    def test_session_id_with_different_agents(self):
        """Test that different agent names produce valid session IDs."""
        agent_names = [
            "code-reviewer",
            "qa-expert",
            "test-agent",
            "agent123",
            "my-custom-agent",
        ]

        for agent_name in agent_names:
            session_id = f"{agent_name}-session-1"
            # Should not raise ValueError
            _validate_session_id(session_id)

    def test_session_counter_format(self):
        """Test that session counter produces valid IDs."""
        agent_name = "test-agent"

        # Test various counter values
        for counter in [1, 10, 100, 9999]:
            session_id = f"{agent_name}-session-{counter}"
            _validate_session_id(session_id)

    def test_session_id_uniqueness_format(self):
        """Test that incrementing counter produces unique session IDs."""
        agent_name = "test-agent"
        session_ids = set()

        # Generate multiple session IDs
        for counter in range(1, 11):
            session_id = f"{agent_name}-session-{counter}"
            session_ids.add(session_id)

        # All session IDs should be unique
        assert len(session_ids) == 10

    def test_auto_generated_id_is_kebab_case(self):
        """Test that auto-generated session IDs are always kebab-case."""
        # Various agent names that are already kebab-case
        test_cases = [
            ("simple-agent", 1, "simple-agent-session-1"),
            ("code-reviewer", 5, "code-reviewer-session-5"),
            ("qa-expert", 100, "qa-expert-session-100"),
        ]

        for agent_name, counter, expected_id in test_cases:
            session_id = f"{agent_name}-session-{counter}"
            assert session_id == expected_id
            # Verify it's valid kebab-case
            _validate_session_id(session_id)


class TestSessionIntegration:
    """Integration tests for session functionality in invoke_agent."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_messages(self):
        """Create mock ModelMessage objects for testing."""
        return [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there!")]),
        ]

    def test_session_persistence_across_saves(self, temp_session_dir, mock_messages):
        """Test that sessions persist correctly across multiple saves."""
        session_id = "persistent-session"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # First interaction
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages[:1],
                agent_name=agent_name,
                initial_prompt="Hello",
            )

            # Load and verify
            loaded = _load_session_history(session_id)
            assert len(loaded) == 1

            # Second interaction - add more messages
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
            )

            # Load and verify both messages are there
            loaded = _load_session_history(session_id)
            assert len(loaded) == 2

    def test_multiple_sessions_dont_interfere(self, temp_session_dir, mock_messages):
        """Test that multiple sessions remain independent."""
        session1_id = "session-one"
        session2_id = "session-two"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # Save to session 1
            messages1 = mock_messages[:1]
            _save_session_history(
                session_id=session1_id,
                message_history=messages1,
                agent_name=agent_name,
                initial_prompt="First",
            )

            # Save to session 2
            messages2 = mock_messages
            _save_session_history(
                session_id=session2_id,
                message_history=messages2,
                agent_name=agent_name,
                initial_prompt="Second",
            )

            # Load both and verify they're independent
            loaded1 = _load_session_history(session1_id)
            loaded2 = _load_session_history(session2_id)

            assert len(loaded1) == 1
            assert len(loaded2) == 2
            assert loaded1 != loaded2

    def test_session_metadata_tracks_message_count(
        self, temp_session_dir, mock_messages
    ):
        """Test that session metadata correctly tracks message count."""
        session_id = "counted-session"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # Save with 1 message
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages[:1],
                agent_name=agent_name,
                initial_prompt="Test",
            )

            txt_file = temp_session_dir / f"{session_id}.txt"
            with open(txt_file, "r") as f:
                metadata = json.load(f)
            assert metadata["message_count"] == 1

            # Save with 2 messages
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
            )

            with open(txt_file, "r") as f:
                metadata = json.load(f)
            assert metadata["message_count"] == 2

    def test_invalid_session_id_in_integration(self, temp_session_dir):
        """Test that invalid session IDs are caught in the integration flow."""
        invalid_ids = [
            "Invalid_Session",
            "session with spaces",
            "session@special",
            "Session-With-Caps",
        ]

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            for invalid_id in invalid_ids:
                # Both save and load should raise ValueError
                with pytest.raises(ValueError, match="must be kebab-case"):
                    _save_session_history(
                        session_id=invalid_id,
                        message_history=[],
                        agent_name="test-agent",
                    )

                with pytest.raises(ValueError, match="must be kebab-case"):
                    _load_session_history(invalid_id)

    def test_empty_session_history_save_and_load(self, temp_session_dir):
        """Test that empty session histories can be saved and loaded."""
        session_id = "empty-session"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # Save empty history
            _save_session_history(
                session_id=session_id,
                message_history=[],
                agent_name=agent_name,
                initial_prompt="Test",
            )

            # Load it back
            loaded = _load_session_history(session_id)
            assert loaded == []

            # Verify metadata is still correct
            txt_file = temp_session_dir / f"{session_id}.txt"
            with open(txt_file, "r") as f:
                metadata = json.load(f)
            assert metadata["message_count"] == 0
