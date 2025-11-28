from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Callable, List

import pytest

from code_puppy.session_storage import (
    cleanup_sessions,
    list_sessions,
    load_session,
    save_session,
)


class TestSessionStorageExtended:
    """Extended tests for session storage functionality."""

    @pytest.fixture
    def sample_history(self) -> List[Any]:
        """Sample session history for testing."""
        return [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

    @pytest.fixture
    def token_estimator(self) -> Callable[[Any], int]:
        """Simple token estimator for testing."""
        return lambda message: len(str(message))

    def test_save_and_load_session(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test round-trip save/load functionality."""
        session_name = "test_session"
        timestamp = "2024-01-01T12:00:00"

        # Save session
        metadata = save_session(
            history=sample_history,
            session_name=session_name,
            base_dir=tmp_path,
            timestamp=timestamp,
            token_estimator=token_estimator,
        )

        # Verify metadata
        assert metadata.session_name == session_name
        assert metadata.message_count == len(sample_history)
        assert metadata.total_tokens == sum(
            token_estimator(msg) for msg in sample_history
        )
        assert metadata.auto_saved is False

        # Verify files exist
        assert metadata.pickle_path.exists()
        assert metadata.metadata_path.exists()

        # Load and verify content
        loaded_history = load_session(session_name, tmp_path)
        assert loaded_history == sample_history

    def test_save_autosave_session(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test autosave functionality."""
        metadata = save_session(
            history=sample_history,
            session_name="autosave_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
            auto_saved=True,
        )

        assert metadata.auto_saved is True

        # Check metadata file contains auto_saved flag
        with metadata.metadata_path.open("r") as f:
            stored_data = json.load(f)
        assert stored_data["auto_saved"] is True

    def test_save_empty_session(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test saving and loading empty session."""
        metadata = save_session(
            history=[],
            session_name="empty_session",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        assert metadata.message_count == 0
        assert metadata.total_tokens == 0

        # Should be able to load empty history
        loaded = load_session("empty_session", tmp_path)
        assert loaded == []

    def test_overwrite_existing_session(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test overwriting an existing session."""
        # Save initial session
        save_session(
            history=["initial"],
            session_name="overwrite_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T10:00:00",
            token_estimator=token_estimator,
        )

        # Overwrite with new data
        new_metadata = save_session(
            history=sample_history,
            session_name="overwrite_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        # Should load the new data
        loaded_history = load_session("overwrite_test", tmp_path)
        assert loaded_history == sample_history
        assert new_metadata.timestamp == "2024-01-01T12:00:00"

    def test_list_sessions(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test session listing functionality."""
        # Empty directory
        assert list_sessions(tmp_path) == []

        # Non-existent directory
        assert list_sessions(tmp_path / "nonexistent") == []

        # Create sessions
        session_names = ["session1", "session2", "session3"]
        for name in session_names:
            save_session(
                history=[f"{name}_data"],
                session_name=name,
                base_dir=tmp_path,
                timestamp="2024-01-01T12:00:00",
                token_estimator=token_estimator,
            )

        # Should list sessions in sorted order
        sessions = list_sessions(tmp_path)
        assert sessions == sorted(session_names)

        # Should ignore non-pkl files
        (tmp_path / "orphaned_meta.json").touch()
        (tmp_path / "other_file.txt").touch()
        assert list_sessions(tmp_path) == sorted(session_names)

    def test_cleanup_sessions(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test session cleanup functionality."""
        # Create sessions with different timestamps
        sessions = [
            ("early_session", 0),
            ("middle_session", 1),
            ("late_session", 2),
            ("latest_session", 3),
        ]

        for name, mtime in sessions:
            metadata = save_session(
                history=[f"data_{name}"],
                session_name=name,
                base_dir=tmp_path,
                timestamp="2024-01-01T12:00:00",
                token_estimator=token_estimator,
            )
            # Set modification time for sorting
            os.utime(metadata.pickle_path, (mtime, mtime))

        # Keep only 2 most recent
        removed = cleanup_sessions(tmp_path, 2)

        # Should remove the 2 oldest
        assert set(removed) == {"early_session", "middle_session"}

        # Should keep the 2 newest
        remaining = list_sessions(tmp_path)
        assert set(remaining) == {"late_session", "latest_session"}

        # Zero or negative limits should not remove anything
        removed = cleanup_sessions(tmp_path, 0)
        assert removed == []

        removed = cleanup_sessions(tmp_path, -1)
        assert removed == []

    def test_corrupted_session_file(self, tmp_path: Path):
        """Test error handling for corrupted session files."""
        # Create corrupted pickle file
        session_name = "corrupted_session"
        pickle_path = tmp_path / f"{session_name}.pkl"

        with pickle_path.open("wb") as f:
            f.write(b"not valid pickle data")

        # Should raise an error when trying to load
        with pytest.raises((pickle.UnpicklingError, EOFError, TypeError)):
            load_session(session_name, tmp_path)

    def test_missing_session_file(self, tmp_path: Path):
        """Test error handling for missing session files."""
        # Try to load non-existent session
        with pytest.raises(FileNotFoundError):
            load_session("nonexistent_session", tmp_path)

    def test_permission_error_handling(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test handling permission errors."""
        # Create read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        try:
            # Should fail when trying to save
            with pytest.raises((PermissionError, OSError)):
                save_session(
                    history=sample_history,
                    session_name="perm_test",
                    base_dir=readonly_dir,
                    timestamp="2024-01-01T12:00:00",
                    token_estimator=token_estimator,
                )
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)

    def test_unicode_content(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test handling unicode and special characters."""
        unicode_history = [
            "Hello 🐕",  # Dog emoji
            "Café crème",  # Accented characters
            "Привет мир",  # Cyrillic
            "🎉 Emoji test",  # More emojis
        ]

        metadata = save_session(
            history=unicode_history,
            session_name="unicode_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        # Should load with same content
        loaded_history = load_session("unicode_test", tmp_path)
        assert loaded_history == unicode_history

        # Metadata should be properly UTF-8 encoded
        with metadata.metadata_path.open("r", encoding="utf-8") as f:
            stored_data = json.load(f)
        assert stored_data["session_name"] == "unicode_test"

    def test_complex_data_types(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test saving and loading complex data structures."""
        complex_history = [
            {
                "role": "user",
                "content": "test",
                "metadata": {"timestamp": "2024-01-01"},
            },
            ["list", "of", "items"],
            42,
            None,
            ("tuple", "data"),
        ]

        save_session(
            history=complex_history,
            session_name="complex_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        loaded_history = load_session("complex_test", tmp_path)
        assert loaded_history == complex_history

    def test_large_session_data(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test handling large session data."""
        large_history = [f"message_{i}" for i in range(1000)]

        metadata = save_session(
            history=large_history,
            session_name="large_test",
            base_dir=tmp_path,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        assert metadata.message_count == 1000
        assert metadata.total_tokens > 0

        # Should be able to load large data
        loaded_history = load_session("large_test", tmp_path)
        assert loaded_history == large_history
        assert len(loaded_history) == 1000

    def test_nested_directories(
        self,
        tmp_path: Path,
        sample_history: List[Any],
        token_estimator: Callable[[Any], int],
    ):
        """Test saving to and loading from nested directories."""
        nested_dir = tmp_path / "level1" / "level2" / "sessions"

        save_session(
            history=sample_history,
            session_name="nested_session",
            base_dir=nested_dir,
            timestamp="2024-01-01T12:00:00",
            token_estimator=token_estimator,
        )

        # Directory should be created
        assert nested_dir.exists()
        assert nested_dir.is_dir()

        # Should be able to load from nested path
        loaded_history = load_session("nested_session", nested_dir)
        assert loaded_history == sample_history

    def test_session_name_variations(
        self, tmp_path: Path, token_estimator: Callable[[Any], int]
    ):
        """Test various session name formats."""
        test_cases = [
            ("simple", ["data"]),
            ("with-dashes", ["dash data"]),
            ("with_underscores", ["underscore data"]),
            ("with.dots", ["dot data"]),
            ("with spaces", ["space data"]),
        ]

        for session_name, history in test_cases:
            metadata = save_session(
                history=history,
                session_name=session_name,
                base_dir=tmp_path,
                timestamp="2024-01-01T12:00:00",
                token_estimator=token_estimator,
            )

            # Files should exist with correct names
            expected_pickle = tmp_path / f"{session_name}.pkl"
            expected_meta = tmp_path / f"{session_name}_meta.json"
            assert metadata.pickle_path == expected_pickle
            assert metadata.metadata_path == expected_meta

            # Should be able to load
            loaded_history = load_session(session_name, tmp_path)
            assert loaded_history == history

        # All should be listable
        all_sessions = list_sessions(tmp_path)
        assert len(all_sessions) == len(test_cases)
        for session_name, _ in test_cases:
            assert session_name in all_sessions
