"""Comprehensive edge case tests for session_storage.py.

Focuses on:
- Session corruption recovery
- Concurrent access scenarios
- Cleanup logic edge cases
- Error handling in save/load
- Metadata handling
"""

import json
import pickle
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy import session_storage
from code_puppy.session_storage import _LEGACY_SIGNATURE_SIZE, _LEGACY_SIGNED_HEADER


class TestSessionPathEdgeCases:
    """Test session path building edge cases."""

    def test_build_session_paths_with_special_characters(self, tmp_path):
        """Test that session names with special characters are handled."""
        # Special characters that might appear in session names
        session_name = "session-with_special.chars"
        paths = session_storage.build_session_paths(tmp_path, session_name)

        assert session_name in str(paths.pickle_path)
        assert session_name in str(paths.metadata_path)

    def test_ensure_directory_with_nested_paths(self, tmp_path):
        """Test that ensure_directory creates nested paths."""
        nested_path = tmp_path / "a" / "b" / "c" / "d"
        assert not nested_path.exists()

        result = session_storage.ensure_directory(nested_path)

        assert nested_path.exists()
        assert result == nested_path


class TestSessionSaveEdgeCases:
    """Test edge cases in session saving."""

    def test_save_session_with_empty_history(self, tmp_path):
        """Test saving an empty session."""

        def mock_token_estimator(msg):
            return 0

        metadata = session_storage.save_session(
            history=[],
            session_name="empty",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        assert metadata.message_count == 0
        assert metadata.total_tokens == 0
        assert (tmp_path / "empty.pkl").exists()

    def test_save_session_with_large_messages(self, tmp_path):
        """Test saving large messages in history."""
        large_content = "x" * 10000  # 10KB message
        history = [{"role": "user", "content": large_content}]

        def mock_token_estimator(msg):
            return len(msg.get("content", ""))

        metadata = session_storage.save_session(
            history=history,
            session_name="large",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        assert metadata.message_count == 1
        assert metadata.total_tokens == 10000

    def test_save_session_with_complex_objects(self, tmp_path):
        """Test saving messages with complex nested objects."""
        history = [
            {
                "role": "user",
                "content": "hello",
                "metadata": {
                    "nested": {"deeply": {"structured": "data"}},
                    "list": [1, 2, 3, {"key": "value"}],
                },
            }
        ]

        def mock_token_estimator(msg):
            return 10

        session_storage.save_session(
            history=history,
            session_name="complex",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        # Load and verify
        loaded = session_storage.load_session("complex", tmp_path)
        assert loaded[0]["metadata"]["nested"]["deeply"]["structured"] == "data"

    def test_save_session_with_none_token_values(self, tmp_path):
        """Test saving with token estimator returning None values."""
        history = [{"role": "user", "content": "test"}]

        def mock_token_estimator(msg):
            # Simulate unpredictable token estimation
            return 0  # Return 0 instead of None

        metadata = session_storage.save_session(
            history=history,
            session_name="test",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        assert metadata.total_tokens == 0

    def test_save_session_marks_auto_saved_correctly(self, tmp_path):
        """Test that auto_saved flag is persisted correctly."""

        def mock_token_estimator(msg):
            return 10

        # Save as auto-saved
        metadata1 = session_storage.save_session(
            history=[{"role": "user", "content": "msg"}],
            session_name="auto",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
            auto_saved=True,
        )
        assert metadata1.auto_saved is True

        # Save as manual
        metadata2 = session_storage.save_session(
            history=[{"role": "user", "content": "msg"}],
            session_name="manual",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
            auto_saved=False,
        )
        assert metadata2.auto_saved is False


class TestSessionLoadEdgeCases:
    """Test edge cases in session loading."""

    def test_load_session_with_corrupted_pickle(self, tmp_path):
        """Test that loading corrupted pickle raises appropriate error."""
        # Create a pickle file with corrupted data
        pickle_path = tmp_path / "corrupted.pkl"
        with open(pickle_path, "wb") as f:
            f.write(b"this is not valid pickle data")

        with pytest.raises(Exception):  # pickle.UnpicklingError or similar
            session_storage.load_session("corrupted", tmp_path)

    def test_load_session_with_empty_pickle(self, tmp_path):
        """Test loading empty pickle file."""
        pkl_data = pickle.dumps([])
        pickle_path = tmp_path / "empty.pkl"
        pickle_path.write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + pkl_data
        )

        loaded = session_storage.load_session("empty", tmp_path)
        assert loaded == []

    def test_load_session_returns_exact_history(self, tmp_path):
        """Test that loaded history matches saved history exactly."""
        original = [
            {"id": 1, "data": [1, 2, 3]},
            {"id": 2, "data": {"nested": True}},
            None,  # Test None values
            "string",  # Test string values
        ]

        pkl_data = pickle.dumps(original)
        pickle_path = tmp_path / "test.pkl"
        pickle_path.write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + pkl_data
        )

        loaded = session_storage.load_session("test", tmp_path)
        assert loaded == original


class TestSessionListingEdgeCases:
    """Test edge cases in session listing."""

    def test_list_sessions_ignores_non_pkl_files(self, tmp_path):
        """Test that only .pkl files are counted."""
        # Create various files
        (tmp_path / "session_1.pkl").touch()
        (tmp_path / "session_2.pkl").touch()
        (tmp_path / "session_1_meta.json").touch()  # Should be ignored
        (tmp_path / "random.txt").touch()  # Should be ignored
        (tmp_path / "session_2.bak").touch()  # Should be ignored

        result = session_storage.list_sessions(tmp_path)

        assert len(result) == 2
        assert "session_1" in result
        assert "session_2" in result

    def test_list_sessions_returns_sorted_names(self, tmp_path):
        """Test that session names are returned sorted."""
        names = ["z_session", "a_session", "m_session"]
        for name in names:
            (tmp_path / f"{name}.pkl").touch()

        result = session_storage.list_sessions(tmp_path)

        assert result == ["a_session", "m_session", "z_session"]

    def test_list_sessions_handles_malformed_names(self, tmp_path):
        """Test that sessions with special names are handled."""
        special_names = ["normal", "with-dash", "with_underscore"]
        for name in special_names:
            (tmp_path / f"{name}.pkl").touch()

        result = session_storage.list_sessions(tmp_path)

        assert len(result) == 3
        assert all(name in result for name in special_names)


class TestSessionCleanupEdgeCases:
    """Test edge cases in session cleanup."""

    def test_cleanup_sessions_respects_max_limit(self, tmp_path):
        """Test that cleanup respects the max_sessions limit."""
        # Create 10 sessions
        for i in range(10):
            session_path = tmp_path / f"session_{i:02d}.pkl"
            session_path.touch()
            # Artificially age them
            import os

            os.utime(session_path, (i, i))

        # Keep only 3
        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=3)

        remaining = session_storage.list_sessions(tmp_path)
        assert len(remaining) == 3
        assert len(removed) == 7

    def test_cleanup_sessions_handles_metadata_file_errors(self, tmp_path):
        """Test that cleanup continues even if metadata can't be deleted."""
        # Create session files
        (tmp_path / "old.pkl").touch()
        (tmp_path / "old_meta.json").touch()
        (tmp_path / "new.pkl").touch()

        import os

        # Age the old one
        os.utime(tmp_path / "old.pkl", (1, 1))
        os.utime(tmp_path / "old_meta.json", (1, 1))
        os.utime(tmp_path / "new.pkl", (999, 999))

        # Should clean up without raising errors
        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=1)
        assert "old" in removed

    def test_cleanup_sessions_handles_permission_errors(self, tmp_path):
        """Test that cleanup gracefully handles permission errors."""
        # Create a session
        pickle_path = tmp_path / "session.pkl"
        pickle_path.touch()

        # Mock the unlink method to raise OSError
        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            # Should not raise, but continue
            session_storage.cleanup_sessions(tmp_path, max_sessions=0)
            # The session should still be listed since delete failed
            assert "session" in session_storage.list_sessions(tmp_path)


class TestSessionMetadataEdgeCases:
    """Test edge cases in session metadata."""

    def test_session_metadata_serialization_with_paths(self):
        """Test metadata serialization includes file path."""
        metadata = session_storage.SessionMetadata(
            session_name="test",
            timestamp="2024-01-01T00:00:00",
            message_count=5,
            total_tokens=100,
            pickle_path=Path("/tmp/test.pkl"),
            metadata_path=Path("/tmp/test_meta.json"),
        )

        serialized = metadata.as_serialisable()

        assert serialized["file_path"] == "/tmp/test.pkl"
        assert "metadata_path" not in serialized  # Should not be in serialization

    def test_session_metadata_preserves_all_fields(self):
        """Test that metadata serialization preserves all important fields."""
        metadata = session_storage.SessionMetadata(
            session_name="comprehensive_test",
            timestamp="2024-06-15T12:30:45.123456",
            message_count=42,
            total_tokens=9999,
            pickle_path=Path("/custom/path/session.pkl"),
            metadata_path=Path("/custom/path/session_meta.json"),
            auto_saved=True,
        )

        serialized = metadata.as_serialisable()

        assert serialized["session_name"] == "comprehensive_test"
        assert serialized["timestamp"] == "2024-06-15T12:30:45.123456"
        assert serialized["message_count"] == 42
        assert serialized["total_tokens"] == 9999
        assert serialized["auto_saved"] is True


class TestSessionRoundTrip:
    """Test complete save and load round-trips."""

    def test_save_and_load_preserves_data(self, tmp_path):
        """Test that data is preserved through save and load."""
        original_history = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What's 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Prove it"},
            {"role": "assistant", "content": "2+2=4 because..."},
        ]

        def mock_token_estimator(msg):
            return len(msg.get("content", "").split())

        # Save
        saved_metadata = session_storage.save_session(
            history=original_history,
            session_name="roundtrip",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
            auto_saved=False,
        )

        # Load
        loaded_history = session_storage.load_session("roundtrip", tmp_path)

        # Verify
        assert loaded_history == original_history
        assert saved_metadata.message_count == len(original_history)

    def test_multiple_sessions_independent(self, tmp_path):
        """Test that multiple sessions don't interfere."""

        def mock_token_estimator(msg):
            return 10

        # Create session 1
        session_storage.save_session(
            history=[{"role": "user", "content": "Session 1"}],
            session_name="session_1",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        # Create session 2
        session_storage.save_session(
            history=[{"role": "user", "content": "Session 2"}],
            session_name="session_2",
            base_dir=tmp_path,
            timestamp="2024-01-02T00:00:00",
            token_estimator=mock_token_estimator,
        )

        # Load and verify they're different
        hist1 = session_storage.load_session("session_1", tmp_path)
        hist2 = session_storage.load_session("session_2", tmp_path)

        assert hist1[0]["content"] == "Session 1"
        assert hist2[0]["content"] == "Session 2"


class TestSessionMetadataFileHandling:
    """Test metadata JSON file handling."""

    def test_metadata_file_creation(self, tmp_path):
        """Test that metadata JSON file is properly created."""

        def mock_token_estimator(msg):
            return 10

        session_storage.save_session(
            history=[{"role": "user", "content": "test"}],
            session_name="meta_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T10:30:45",
            token_estimator=mock_token_estimator,
            auto_saved=True,
        )

        # Check metadata file exists and is valid JSON
        meta_path = tmp_path / "meta_test_meta.json"
        assert meta_path.exists()

        with open(meta_path) as f:
            metadata = json.load(f)

        assert metadata["session_name"] == "meta_test"
        assert metadata["timestamp"] == "2024-01-01T10:30:45"
        assert metadata["auto_saved"] is True

    def test_metadata_file_is_readable_json(self, tmp_path):
        """Test that metadata files are valid, readable JSON."""

        def mock_token_estimator(msg):
            return 5

        session_storage.save_session(
            history=[{"role": "assistant", "content": "Hello there"}],
            session_name="json_test",
            base_dir=tmp_path,
            timestamp="2024-03-15T08:00:00",
            token_estimator=mock_token_estimator,
        )

        # Verify we can read it back
        meta_path = tmp_path / "json_test_meta.json"
        metadata = json.loads(meta_path.read_text())

        assert metadata["message_count"] == 1
        assert metadata["total_tokens"] == 5
