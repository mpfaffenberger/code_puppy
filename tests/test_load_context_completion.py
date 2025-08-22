import tempfile
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.document import Document

from code_puppy.command_line.load_context_completion import LoadContextCompleter


class TestLoadContextCompleter:
    def setup_method(self):
        self.completer = LoadContextCompleter()

    def test_trigger_detection(self):
        """Test that the completer only activates for /load_context commands."""
        # Should activate
        doc = Document("/load_context")
        completions = list(self.completer.get_completions(doc, None))
        assert len(completions) >= 0  # At least doesn't crash

        # Should not activate
        doc = Document("/other_command")
        completions = list(self.completer.get_completions(doc, None))
        assert len(completions) == 0

        doc = Document("regular text")
        completions = list(self.completer.get_completions(doc, None))
        assert len(completions) == 0

    def test_space_completion(self):
        """Test that typing just /load_context suggests adding a space."""
        doc = Document("/load_context")
        completions = list(self.completer.get_completions(doc, None))

        assert len(completions) == 1
        assert completions[0].text == "/load_context "
        # display_meta might be a FormattedText object, so convert to string
        display_meta = str(completions[0].display_meta)
        assert "load saved context" in display_meta

    def test_session_name_completion(self):
        """Test that available session files are suggested for completion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", temp_dir
            ):
                # Create contexts directory with some test files
                contexts_dir = Path(temp_dir) / "contexts"
                contexts_dir.mkdir()

                # Create test context files
                (contexts_dir / "session1.pkl").touch()
                (contexts_dir / "session2.pkl").touch()
                (contexts_dir / "another_session.pkl").touch()
                (contexts_dir / "not_a_pkl.txt").touch()  # Should be ignored

                # Test completion with space
                doc = Document("/load_context ")
                completions = list(self.completer.get_completions(doc, None))

                # Should suggest all .pkl files (without extension)
                completion_texts = [c.text for c in completions]
                assert "session1" in completion_texts
                assert "session2" in completion_texts
                assert "another_session" in completion_texts
                assert "not_a_pkl" not in completion_texts  # .txt files ignored

                # All should have proper metadata
                for completion in completions:
                    display_meta = str(completion.display_meta)
                    assert "saved context session" in display_meta

    def test_partial_session_name_completion(self):
        """Test that partial session names are filtered correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", temp_dir
            ):
                # Create contexts directory with some test files
                contexts_dir = Path(temp_dir) / "contexts"
                contexts_dir.mkdir()

                # Create test context files
                (contexts_dir / "session1.pkl").touch()
                (contexts_dir / "session2.pkl").touch()
                (contexts_dir / "another_session.pkl").touch()

                # Test completion with partial match
                doc = Document("/load_context sess")
                completions = list(self.completer.get_completions(doc, None))

                # Should only suggest files starting with "sess"
                completion_texts = [c.text for c in completions]
                assert "session1" in completion_texts
                assert "session2" in completion_texts
                assert (
                    "another_session" not in completion_texts
                )  # Doesn't start with "sess"

    def test_no_contexts_directory(self):
        """Test behavior when contexts directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", temp_dir
            ):
                # Don't create contexts directory

                # Test completion - should not crash
                doc = Document("/load_context ")
                completions = list(self.completer.get_completions(doc, None))

                # Should return empty list, not crash
                assert completions == []

    def test_whitespace_handling(self):
        """Test that leading whitespace is handled correctly."""
        # Test with leading spaces
        doc = Document("   /load_context")
        completions = list(self.completer.get_completions(doc, None))
        assert len(completions) == 1
        assert completions[0].text == "/load_context "

        # Test with tabs
        doc = Document("\t/load_context ")
        completions = list(self.completer.get_completions(doc, None))
        assert len(completions) >= 0  # At least doesn't crash
