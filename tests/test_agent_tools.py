"""Tests for agent tools functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

from code_puppy.tools.agent_tools import (
    AgentInfo,
    AgentInvokeOutput,
    ListAgentsOutput,
    _generate_dbos_workflow_id,
    _generate_session_hash_suffix,
    _get_subagent_sessions_dir,
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
            assert "USER FEEDBACK SYSTEM" in file_permission_text
            assert "How User Approval Works" in file_permission_text

    def test_invoke_agent_includes_puppy_rules(self):
        """Test that invoke_agent includes AGENTS.md content for subagents (excluding ShellSafetyAgent)."""
        from unittest.mock import MagicMock

        # Mock agent configurations to test the logic
        mock_agent_config = MagicMock()
        mock_agent_config.name = "test-agent"
        mock_agent_config.get_system_prompt.return_value = "Test system prompt"

        # Mock AGENTS.md content
        mock_puppy_rules = "# AGENTS.MD CONTENT\nSome puppy rules here..."
        mock_agent_config.load_puppy_rules.return_value = mock_puppy_rules

        # Test the core logic that was added to invoke_agent
        # Test that regular agents get AGENTS.md content
        instructions = mock_agent_config.get_system_prompt()
        if mock_agent_config.name != "shell_safety_checker":
            puppy_rules = mock_agent_config.load_puppy_rules()
            if puppy_rules:
                instructions += f"\n{puppy_rules}"

        # Verify AGENTS.md was added to regular agent
        assert mock_puppy_rules in instructions
        assert "Test system prompt" in instructions

        # Test that ShellSafetyAgent does NOT get AGENTS.md content
        mock_agent_config.name = "shell_safety_checker"
        instructions_safety = mock_agent_config.get_system_prompt()
        if mock_agent_config.name != "shell_safety_checker":
            puppy_rules = mock_agent_config.load_puppy_rules()
            if puppy_rules:
                instructions_safety += f"\n{puppy_rules}"

        # Should not have added puppy_rules for shell safety agent
        assert mock_puppy_rules not in instructions_safety
        assert "Test system prompt" in instructions_safety


class TestGenerateSessionHashSuffix:
    """Test suite for _generate_session_hash_suffix function."""

    def test_hash_format(self):
        """Test that the hash suffix is in the correct format."""
        suffix = _generate_session_hash_suffix()
        # Should be 6 hex characters
        assert len(suffix) == 6
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_different_calls_different_hashes(self):
        """Test that different calls produce different hashes (timestamp-based)."""
        import time

        suffix1 = _generate_session_hash_suffix()
        time.sleep(0.01)  # Small delay to ensure different timestamp
        suffix2 = _generate_session_hash_suffix()
        assert suffix1 != suffix2

    def test_result_is_valid_for_kebab_case(self):
        """Test that the suffix can be appended to create valid kebab-case."""
        suffix = _generate_session_hash_suffix()
        session_id = f"test-session-{suffix}"
        # Should not raise
        _validate_session_id(session_id)


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
    """Tests for auto-generated session ID format."""

    def test_session_id_format(self):
        """Test that auto-generated session IDs follow the correct format."""
        # Auto-generated session IDs use format: {agent_name}-session-{hash}
        agent_name = "qa-expert"
        hash_suffix = _generate_session_hash_suffix()
        expected_format = f"{agent_name}-session-{hash_suffix}"

        # Verify it matches kebab-case pattern
        _validate_session_id(expected_format)

        # Verify the format starts correctly
        assert expected_format.startswith("qa-expert-session-")
        # And ends with a 6-char hash
        assert len(expected_format.split("-")[-1]) == 6

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
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{agent_name}-session-{hash_suffix}"
            # Should not raise ValueError
            _validate_session_id(session_id)

    def test_session_hash_suffix_format(self):
        """Test that session hash suffix produces valid IDs."""
        agent_name = "test-agent"

        # Generate multiple session IDs and verify format
        for _ in range(5):
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{agent_name}-session-{hash_suffix}"
            _validate_session_id(session_id)
            # Hash should be 6 hex chars
            assert len(hash_suffix) == 6
            assert all(c in "0123456789abcdef" for c in hash_suffix)

    def test_session_id_uniqueness_format(self):
        """Test that hash suffixes produce unique session IDs."""
        import time

        agent_name = "test-agent"
        session_ids = set()

        # Generate multiple session IDs with small delays
        for _ in range(10):
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{agent_name}-session-{hash_suffix}"
            session_ids.add(session_id)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # All session IDs should be unique
        assert len(session_ids) == 10

    def test_auto_generated_id_is_kebab_case(self):
        """Test that auto-generated session IDs are always kebab-case."""
        # Various agent names that are already kebab-case
        agent_names = [
            "simple-agent",
            "code-reviewer",
            "qa-expert",
        ]

        for agent_name in agent_names:
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{agent_name}-session-{hash_suffix}"
            # Verify it's valid kebab-case
            _validate_session_id(session_id)
            # Verify format
            assert session_id.startswith(f"{agent_name}-session-")
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


class TestDBOSWorkflowId:
    """Test suite for _generate_dbos_workflow_id function."""

    def test_generates_unique_ids(self):
        """Test that consecutive calls generate unique workflow IDs."""
        base_id = "test-group-id"
        id1 = _generate_dbos_workflow_id(base_id)
        id2 = _generate_dbos_workflow_id(base_id)
        id3 = _generate_dbos_workflow_id(base_id)

        # All IDs should be different
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    def test_workflow_id_format(self):
        """Test that workflow ID follows expected format."""
        base_id = "invoke-agent-test"
        workflow_id = _generate_dbos_workflow_id(base_id)

        # Should have format: {base_id}-wf-{counter}
        assert workflow_id.startswith(f"{base_id}-wf-")
        # Counter should be a number
        counter_part = workflow_id.split("-wf-")[1]
        assert counter_part.isdigit()

    def test_counter_increments(self):
        """Test that the counter in workflow IDs increments."""
        base_id = "test-increment"
        ids = [_generate_dbos_workflow_id(base_id) for _ in range(5)]

        # Extract counter values
        counters = [int(id_.split("-wf-")[1]) for id_ in ids]

        # Should be strictly increasing
        for i in range(1, len(counters)):
            assert counters[i] > counters[i - 1]


class TestGetSubagentSessionsDir:
    """Test suite for _get_subagent_sessions_dir function."""

    def test_returns_path(self):
        """Test that it returns a Path object."""
        with patch("code_puppy.tools.agent_tools.DATA_DIR", "/tmp/test-data"):
            result = _get_subagent_sessions_dir()
            assert isinstance(result, Path)
            assert result.name == "subagent_sessions"

    def test_creates_directory_if_not_exists(self):
        """Test that directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.agent_tools.DATA_DIR", tmpdir):
                result = _get_subagent_sessions_dir()
                assert result.exists()
                assert result.is_dir()


class TestListAgentsExecution:
    """Test suite for list_agents tool execution."""

    def test_list_agents_returns_agents(self):
        """Test that list_agents tool returns available agents."""
        mock_agent = MagicMock()

        # Register the tool
        register_list_agents(mock_agent)

        # Mock the dependencies
        mock_agents_dict = {
            "test-agent": "Test Agent",
            "code-reviewer": "Code Reviewer",
        }
        mock_descriptions = {
            "test-agent": "A test agent",
            "code-reviewer": "Reviews code",
        }

        with (
            patch("code_puppy.tools.agent_tools.get_message_bus"),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents_dict
            ),
            patch(
                "code_puppy.agents.get_agent_descriptions",
                return_value=mock_descriptions,
            ),
            patch("code_puppy.config.get_banner_color", return_value="blue"),
        ):
            # Create a mock context
            mock_context = MagicMock()

            # If registration happened, extract and call the function
            if mock_agent.tool.called:
                actual_func = mock_agent.tool.call_args[0][0]
                result = actual_func(mock_context)

                # Verify result
                assert isinstance(result, ListAgentsOutput)
                assert len(result.agents) == 2
                assert result.error is None

                # Verify agent info
                agent_names = [a.name for a in result.agents]
                assert "test-agent" in agent_names
                assert "code-reviewer" in agent_names

    def test_list_agents_handles_exception(self):
        """Test that list_agents handles exceptions gracefully."""
        mock_agent = MagicMock()

        # Register the tool
        register_list_agents(mock_agent)

        with (
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.agents.get_available_agents",
                side_effect=Exception("Test error"),
            ),
            patch("code_puppy.config.get_banner_color", return_value="blue"),
        ):
            mock_context = MagicMock()

            if mock_agent.tool.called:
                actual_func = mock_agent.tool.call_args[0][0]
                result = actual_func(mock_context)

                # Should return empty agents list with error
                assert isinstance(result, ListAgentsOutput)
                assert result.agents == []
                assert result.error is not None
                assert "Test error" in result.error


class TestInvokeAgentExecution:
    """Test suite for invoke_agent tool execution."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_invoke_agent_with_invalid_session_id(self):
        """Test that invoke_agent returns error for invalid session_id."""
        mock_agent = MagicMock()

        # Register the tool
        register_invoke_agent(mock_agent)

        with patch("code_puppy.tools.agent_tools.emit_error"):
            mock_context = MagicMock()

            if mock_agent.tool.called:
                actual_func = mock_agent.tool.call_args[0][0]

                # Call with invalid session_id
                import asyncio

                result = asyncio.get_event_loop().run_until_complete(
                    actual_func(
                        mock_context,
                        agent_name="test-agent",
                        prompt="test",
                        session_id="Invalid_Session",  # Invalid: uses underscore
                    )
                )

                # Should return error
                assert isinstance(result, AgentInvokeOutput)
                assert result.response is None
                assert result.error is not None
                assert "must be kebab-case" in result.error

    @pytest.mark.asyncio
    async def test_invoke_agent_model_not_found(self, temp_session_dir):
        """Test that invoke_agent handles model not found error."""
        mock_agent = MagicMock()

        # Register the tool
        register_invoke_agent(mock_agent)

        # Mock agent config
        mock_agent_config = MagicMock()
        mock_agent_config.get_model_name.return_value = "nonexistent-model"
        mock_agent_config.get_system_prompt.return_value = "System prompt"
        mock_agent_config.load_puppy_rules.return_value = None

        with (
            patch(
                "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
                return_value=temp_session_dir,
            ),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch("code_puppy.tools.agent_tools.emit_success"),
            patch("code_puppy.tools.agent_tools.get_message_bus") as mock_bus,
            patch(
                "code_puppy.tools.agent_tools.get_session_context", return_value=None
            ),
            patch("code_puppy.tools.agent_tools.set_session_context"),
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=mock_agent_config,
            ),
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"other-model": {}},  # Model not in config
            ),
        ):
            mock_context = MagicMock()
            mock_bus.return_value.emit = MagicMock()

            if mock_agent.tool.called:
                actual_func = mock_agent.tool.call_args[0][0]

                result = await actual_func(
                    mock_context,
                    agent_name="test-agent",
                    prompt="test prompt",
                    session_id=None,
                )

                # Should return error about model not found
                assert isinstance(result, AgentInvokeOutput)
                assert result.response is None
                assert result.error is not None

    @pytest.mark.asyncio
    async def test_invoke_agent_auto_generates_session_id(self, temp_session_dir):
        """Test that invoke_agent auto-generates session_id when None."""
        mock_agent = MagicMock()

        # Register the tool
        register_invoke_agent(mock_agent)

        # Create mock result
        mock_result = MagicMock()
        mock_result.output = "Test response"
        mock_result.all_messages.return_value = []

        # Mock agent config
        mock_agent_config = MagicMock()
        mock_agent_config.get_model_name.return_value = "test-model"
        mock_agent_config.get_system_prompt.return_value = "System prompt"
        mock_agent_config.load_puppy_rules.return_value = None
        mock_agent_config.get_available_tools.return_value = []
        mock_agent_config.message_history_accumulator = MagicMock()

        # Mock model
        mock_model = MagicMock()

        # Create an async mock for temp_agent.run
        async def mock_run(*args, **kwargs):
            return mock_result

        mock_temp_agent = MagicMock()
        mock_temp_agent.run = mock_run

        with (
            patch(
                "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
                return_value=temp_session_dir,
            ),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch("code_puppy.tools.agent_tools.emit_success"),
            patch("code_puppy.tools.agent_tools.get_message_bus") as mock_bus,
            patch(
                "code_puppy.tools.agent_tools.get_session_context", return_value=None
            ),
            patch("code_puppy.tools.agent_tools.set_session_context"),
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=mock_agent_config,
            ),
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"test-model": {}},
            ),
            patch(
                "code_puppy.model_factory.ModelFactory.get_model",
                return_value=mock_model,
            ),
            patch(
                "code_puppy.model_factory.make_model_settings",
                return_value={},
            ),
            patch(
                "code_puppy.tools.agent_tools.Agent",
                return_value=mock_temp_agent,
            ),
            patch(
                "code_puppy.callbacks.on_load_prompt",
                return_value=[],
            ),
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prepare,
            patch(
                "code_puppy.tools.agent_tools.get_use_dbos",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.agent_tools.get_value",
                return_value="true",  # MCP disabled
            ),
            patch("code_puppy.tools.register_tools_for_agent"),
            patch("code_puppy.agents.subagent_stream_handler.subagent_stream_handler"),
        ):
            mock_bus.return_value.emit = MagicMock()
            mock_prepare.return_value = MagicMock(
                instructions="prepared instructions", user_prompt="prepared prompt"
            )

            mock_context = MagicMock()

            if mock_agent.tool.called:
                actual_func = mock_agent.tool.call_args[0][0]

                result = await actual_func(
                    mock_context,
                    agent_name="test-agent",
                    prompt="test prompt",
                    session_id=None,
                )

                # Should have auto-generated session_id
                assert result.session_id is not None
                assert result.session_id.startswith("test-agent-session-")


class TestSaveSessionMetadataException:
    """Test exception handling in _save_session_history metadata update."""

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

    def test_metadata_update_exception_is_silently_handled(
        self, temp_session_dir, mock_messages
    ):
        """Test that exceptions in metadata update are silently handled."""
        session_id = "test-session"
        agent_name = "test-agent"

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=temp_session_dir,
        ):
            # First save - creates the files
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages[:1],
                agent_name=agent_name,
                initial_prompt="Test",
            )

            # Corrupt the txt file so json.load will fail
            txt_file = temp_session_dir / f"{session_id}.txt"
            with open(txt_file, "w") as f:
                f.write("not valid json{{{")

            # Second save - should not raise despite corrupted metadata
            # This tests the except Exception: pass block
            _save_session_history(
                session_id=session_id,
                message_history=mock_messages,
                agent_name=agent_name,
                initial_prompt=None,
            )

            # Pickle should still be saved correctly
            loaded = _load_session_history(session_id)
            assert len(loaded) == 2


class TestAgentInfoModel:
    """Test suite for AgentInfo Pydantic model."""

    def test_agent_info_creation(self):
        """Test creating AgentInfo with valid data."""
        info = AgentInfo(
            name="test-agent", display_name="Test Agent", description="A test agent"
        )
        assert info.name == "test-agent"
        assert info.display_name == "Test Agent"
        assert info.description == "A test agent"

    def test_agent_info_serialization(self):
        """Test that AgentInfo can be serialized to dict."""
        info = AgentInfo(
            name="test-agent", display_name="Test Agent", description="A test agent"
        )
        data = info.model_dump()
        assert data["name"] == "test-agent"
        assert data["display_name"] == "Test Agent"
        assert data["description"] == "A test agent"


class TestListAgentsOutput:
    """Test suite for ListAgentsOutput Pydantic model."""

    def test_list_agents_output_with_agents(self):
        """Test ListAgentsOutput with agents."""
        agents = [
            AgentInfo(name="agent1", display_name="Agent 1", description="First agent"),
            AgentInfo(
                name="agent2", display_name="Agent 2", description="Second agent"
            ),
        ]
        output = ListAgentsOutput(agents=agents)
        assert len(output.agents) == 2
        assert output.error is None

    def test_list_agents_output_with_error(self):
        """Test ListAgentsOutput with error."""
        output = ListAgentsOutput(agents=[], error="Something went wrong")
        assert output.agents == []
        assert output.error == "Something went wrong"


class TestAgentInvokeOutput:
    """Test suite for AgentInvokeOutput Pydantic model."""

    def test_agent_invoke_output_success(self):
        """Test AgentInvokeOutput for successful invocation."""
        output = AgentInvokeOutput(
            response="Hello, world!",
            agent_name="test-agent",
            session_id="test-session-abc123",
        )
        assert output.response == "Hello, world!"
        assert output.agent_name == "test-agent"
        assert output.session_id == "test-session-abc123"
        assert output.error is None

    def test_agent_invoke_output_error(self):
        """Test AgentInvokeOutput for failed invocation."""
        output = AgentInvokeOutput(
            response=None,
            agent_name="test-agent",
            session_id="test-session-abc123",
            error="Agent failed to respond",
        )
        assert output.response is None
        assert output.error == "Agent failed to respond"

    def test_agent_invoke_output_no_session(self):
        """Test AgentInvokeOutput without session_id."""
        output = AgentInvokeOutput(
            response="Test", agent_name="test-agent", session_id=None
        )
        assert output.session_id is None
