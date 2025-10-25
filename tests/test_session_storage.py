"""Comprehensive unit tests for code_puppy.session_storage module.

Tests session persistence, restoration, and management.
"""
import json
import pickle
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_puppy.session_storage import (
    SessionMetadata,
    SessionPaths,
    build_session_paths,
    cleanup_sessions,
    ensure_directory,
    list_sessions,
    load_session,
    save_session,
)


class TestSessionPaths:
    """Test SessionPaths dataclass."""
    
    def test_session_paths_creation(self):
        """Test creating SessionPaths dataclass."""
        pickle_path = Path("/tmp/test.pkl")
        metadata_path = Path("/tmp/test_meta.json")
        
        paths = SessionPaths(pickle_path=pickle_path, metadata_path=metadata_path)
        
        assert paths.pickle_path == pickle_path
        assert paths.metadata_path == metadata_path


class TestSessionMetadata:
    """Test SessionMetadata dataclass."""
    
    def test_session_metadata_creation(self):
        """Test creating SessionMetadata dataclass."""
        metadata = SessionMetadata(
            session_name="test_session",
            timestamp="2025-01-01T12:00:00",
            message_count=5,
            total_tokens=100,
            pickle_path=Path("/tmp/test.pkl"),
            metadata_path=Path("/tmp/test_meta.json"),
            auto_saved=True,
        )
        
        assert metadata.session_name == "test_session"
        assert metadata.timestamp == "2025-01-01T12:00:00"
        assert metadata.message_count == 5
        assert metadata.total_tokens == 100
        assert metadata.auto_saved is True
    
    def test_session_metadata_default_auto_saved(self):
        """Test SessionMetadata auto_saved defaults to False."""
        metadata = SessionMetadata(
            session_name="test",
            timestamp="2025-01-01T12:00:00",
            message_count=0,
            total_tokens=0,
            pickle_path=Path("/tmp/test.pkl"),
            metadata_path=Path("/tmp/test_meta.json"),
        )
        
        assert metadata.auto_saved is False
    
    def test_as_serialisable(self):
        """Test SessionMetadata.as_serialisable() returns correct dict."""
        metadata = SessionMetadata(
            session_name="my_session",
            timestamp="2025-01-01T12:00:00",
            message_count=3,
            total_tokens=50,
            pickle_path=Path("/tmp/my_session.pkl"),
            metadata_path=Path("/tmp/my_session_meta.json"),
            auto_saved=True,
        )
        
        result = metadata.as_serialisable()
        
        assert result["session_name"] == "my_session"
        assert result["timestamp"] == "2025-01-01T12:00:00"
        assert result["message_count"] == 3
        assert result["total_tokens"] == 50
        assert result["file_path"] == "/tmp/my_session.pkl"
        assert result["auto_saved"] is True


class TestEnsureDirectory:
    """Test ensure_directory function."""
    
    def test_ensure_directory_creates_dir(self, temp_test_dir):
        """Test ensure_directory creates directory if it doesn't exist."""
        test_dir = temp_test_dir / "new_directory"
        
        result = ensure_directory(test_dir)
        
        assert test_dir.exists()
        assert test_dir.is_dir()
        assert result == test_dir
    
    def test_ensure_directory_existing_dir(self, temp_test_dir):
        """Test ensure_directory with existing directory."""
        # temp_test_dir already exists
        result = ensure_directory(temp_test_dir)
        
        assert temp_test_dir.exists()
        assert result == temp_test_dir
    
    def test_ensure_directory_creates_parents(self, temp_test_dir):
        """Test ensure_directory creates parent directories."""
        nested_dir = temp_test_dir / "parent" / "child" / "grandchild"
        
        result = ensure_directory(nested_dir)
        
        assert nested_dir.exists()
        assert nested_dir.is_dir()
        assert result == nested_dir


class TestBuildSessionPaths:
    """Test build_session_paths function."""
    
    def test_build_session_paths(self, temp_test_dir):
        """Test building session paths."""
        session_name = "my_session"
        
        paths = build_session_paths(temp_test_dir, session_name)
        
        assert paths.pickle_path == temp_test_dir / "my_session.pkl"
        assert paths.metadata_path == temp_test_dir / "my_session_meta.json"
    
    def test_build_session_paths_different_names(self, temp_test_dir):
        """Test building paths with different session names."""
        paths1 = build_session_paths(temp_test_dir, "session1")
        paths2 = build_session_paths(temp_test_dir, "session2")
        
        assert paths1.pickle_path != paths2.pickle_path
        assert paths1.metadata_path != paths2.metadata_path


class TestSaveSession:
    """Test save_session function."""
    
    def test_save_session_creates_files(self, temp_test_dir):
        """Test save_session creates pickle and metadata files."""
        history = [{"role": "user", "content": "Hello"}]
        
        def token_estimator(msg):
            return len(msg.get("content", ""))
        
        metadata = save_session(
            history=history,
            session_name="test_session",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=token_estimator,
        )
        
        pickle_path = temp_test_dir / "test_session.pkl"
        metadata_path = temp_test_dir / "test_session_meta.json"
        
        assert pickle_path.exists()
        assert metadata_path.exists()
        assert metadata.session_name == "test_session"
        assert metadata.message_count == 1
        assert metadata.total_tokens == 5  # "Hello" = 5 chars
    
    def test_save_session_auto_saved_flag(self, temp_test_dir):
        """Test save_session with auto_saved flag."""
        history = []
        
        metadata = save_session(
            history=history,
            session_name="auto_session",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
            auto_saved=True,
        )
        
        assert metadata.auto_saved is True
        
        # Verify it's in the JSON
        meta_path = temp_test_dir / "auto_session_meta.json"
        with meta_path.open("r") as f:
            data = json.load(f)
        assert data["auto_saved"] is True
    
    def test_save_session_token_counting(self, temp_test_dir):
        """Test save_session correctly counts tokens."""
        history = [
            {"content": "Hello"},  # 5 tokens
            {"content": "World"},  # 5 tokens
            {"content": "!"},      # 1 token
        ]
        
        def token_estimator(msg):
            return len(msg.get("content", ""))
        
        metadata = save_session(
            history=history,
            session_name="tokens",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=token_estimator,
        )
        
        assert metadata.total_tokens == 11
        assert metadata.message_count == 3


class TestLoadSession:
    """Test load_session function."""
    
    def test_load_session_success(self, temp_test_dir):
        """Test loading an existing session."""
        history = [{"role": "user", "content": "Test"}]
        
        save_session(
            history=history,
            session_name="load_test",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        
        loaded_history = load_session("load_test", temp_test_dir)
        
        assert loaded_history == history
    
    def test_load_session_file_not_found(self, temp_test_dir):
        """Test loading a non-existent session raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_session("nonexistent", temp_test_dir)


class TestListSessions:
    """Test list_sessions function."""
    
    def test_list_sessions_empty_dir(self, temp_test_dir):
        """Test listing sessions in empty directory."""
        sessions = list_sessions(temp_test_dir)
        
        assert sessions == []
    
    def test_list_sessions_nonexistent_dir(self, temp_test_dir):
        """Test listing sessions in non-existent directory."""
        nonexistent = temp_test_dir / "does_not_exist"
        
        sessions = list_sessions(nonexistent)
        
        assert sessions == []
    
    def test_list_sessions_multiple_sessions(self, temp_test_dir):
        """Test listing multiple saved sessions."""
        for name in ["session1", "session2", "session3"]:
            save_session(
                history=[],
                session_name=name,
                base_dir=temp_test_dir,
                timestamp="2025-01-01T12:00:00",
                token_estimator=lambda x: 0,
            )
        
        sessions = list_sessions(temp_test_dir)
        
        assert len(sessions) == 3
        assert "session1" in sessions
        assert "session2" in sessions
        assert "session3" in sessions
    
    def test_list_sessions_sorted(self, temp_test_dir):
        """Test sessions are returned sorted."""
        for name in ["zebra", "apple", "mango"]:
            save_session(
                history=[],
                session_name=name,
                base_dir=temp_test_dir,
                timestamp="2025-01-01T12:00:00",
                token_estimator=lambda x: 0,
            )
        
        sessions = list_sessions(temp_test_dir)
        
        assert sessions == ["apple", "mango", "zebra"]


class TestCleanupSessions:
    """Test cleanup_sessions function."""
    
    def test_cleanup_sessions_no_cleanup_needed(self, temp_test_dir):
        """Test cleanup when under max_sessions limit."""
        save_session(
            history=[],
            session_name="session1",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        
        removed = cleanup_sessions(temp_test_dir, max_sessions=5)
        
        assert removed == []
        assert "session1" in list_sessions(temp_test_dir)
    
    def test_cleanup_sessions_removes_oldest(self, temp_test_dir):
        """Test cleanup removes oldest sessions."""
        import time
        
        # Create sessions with delays to ensure different mtimes
        save_session(
            history=[],
            session_name="old",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        time.sleep(0.01)
        
        save_session(
            history=[],
            session_name="new",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T13:00:00",
            token_estimator=lambda x: 0,
        )
        
        removed = cleanup_sessions(temp_test_dir, max_sessions=1)
        
        assert "old" in removed
        assert "old" not in list_sessions(temp_test_dir)
        assert "new" in list_sessions(temp_test_dir)
    
    def test_cleanup_sessions_zero_max(self, temp_test_dir):
        """Test cleanup with max_sessions=0 returns empty list."""
        save_session(
            history=[],
            session_name="session1",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        
        removed = cleanup_sessions(temp_test_dir, max_sessions=0)
        
        assert removed == []
    
    def test_cleanup_sessions_nonexistent_dir(self, temp_test_dir):
        """Test cleanup on non-existent directory."""
        nonexistent = temp_test_dir / "does_not_exist"
        
        removed = cleanup_sessions(nonexistent, max_sessions=5)
        
        assert removed == []
    
    def test_cleanup_sessions_removes_metadata_too(self, temp_test_dir):
        """Test cleanup removes both pickle and metadata files."""
        import time
        
        save_session(
            history=[],
            session_name="to_remove",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        time.sleep(0.01)
        
        save_session(
            history=[],
            session_name="to_keep",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T13:00:00",
            token_estimator=lambda x: 0,
        )
        
        cleanup_sessions(temp_test_dir, max_sessions=1)
        
        # Verify both pickle and metadata are gone
        assert not (temp_test_dir / "to_remove.pkl").exists()
        assert not (temp_test_dir / "to_remove_meta.json").exists()
        # But kept session files exist
        assert (temp_test_dir / "to_keep.pkl").exists()
        assert (temp_test_dir / "to_keep_meta.json").exists()


class TestCleanupSessionsErrorHandling:
    """Test cleanup_sessions error handling."""
    
    def test_cleanup_sessions_handles_oserror(self, temp_test_dir):
        """Test cleanup gracefully handles OSError during file deletion."""
        import time
        from unittest.mock import patch, Mock
        
        # Create two sessions
        save_session(
            history=[],
            session_name="session1",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        time.sleep(0.01)
        
        save_session(
            history=[],
            session_name="session2",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T13:00:00",
            token_estimator=lambda x: 0,
        )
        
        # Mock unlink to raise OSError on first session
        original_unlink = Path.unlink
        
        def mock_unlink(self, *args, **kwargs):
            if "session1" in str(self):
                raise OSError("Permission denied")
            return original_unlink(self, *args, **kwargs)
        
        with patch.object(Path, 'unlink', mock_unlink):
            removed = cleanup_sessions(temp_test_dir, max_sessions=1)
        
        # Even though session1 failed to delete, function should continue
        # and not include it in removed list
        assert "session1" not in removed


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_save_session_creates_directory(self, temp_test_dir):
        """Test save_session creates base directory if it doesn't exist."""
        nonexistent = temp_test_dir / "new_dir"
        
        save_session(
            history=[],
            session_name="test",
            base_dir=nonexistent,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        
        assert nonexistent.exists()
        assert (nonexistent / "test.pkl").exists()
    
    def test_save_session_empty_history(self, temp_test_dir):
        """Test saving session with empty history."""
        metadata = save_session(
            history=[],
            session_name="empty",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 0,
        )
        
        assert metadata.message_count == 0
        assert metadata.total_tokens == 0
        
        loaded = load_session("empty", temp_test_dir)
        assert loaded == []
    
    def test_save_session_complex_messages(self, temp_test_dir):
        """Test saving session with complex message structures."""
        history = [
            {"role": "user", "content": "Hello", "metadata": {"timestamp": 123}},
            {"role": "assistant", "content": "Hi", "nested": {"data": [1, 2, 3]}},
        ]
        
        save_session(
            history=history,
            session_name="complex",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: len(str(x)),
        )
        
        loaded = load_session("complex", temp_test_dir)
        assert loaded == history
    
    def test_metadata_path_format(self, temp_test_dir):
        """Test metadata file contains correct JSON structure."""
        save_session(
            history=[{"content": "test"}],
            session_name="json_test",
            base_dir=temp_test_dir,
            timestamp="2025-01-01T12:00:00",
            token_estimator=lambda x: 10,
        )
        
        meta_path = temp_test_dir / "json_test_meta.json"
        with meta_path.open("r") as f:
            data = json.load(f)
        
        assert "session_name" in data
        assert "timestamp" in data
        assert "message_count" in data
        assert "total_tokens" in data
        assert "file_path" in data
        assert "auto_saved" in data
    
    def test_cleanup_exactly_at_limit(self, temp_test_dir):
        """Test cleanup when exactly at max_sessions limit."""
        import time
        
        for i in range(3):
            save_session(
                history=[],
                session_name=f"session{i}",
                base_dir=temp_test_dir,
                timestamp=f"2025-01-01T12:00:0{i}",
                token_estimator=lambda x: 0,
            )
            time.sleep(0.01)
        
        # Exactly 3 sessions, limit is 3
        removed = cleanup_sessions(temp_test_dir, max_sessions=3)
        
        assert removed == []
        assert len(list_sessions(temp_test_dir)) == 3
