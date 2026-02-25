"""Tests for load_context_completion.py - 100% coverage."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from code_puppy.command_line.load_context_completion import LoadContextCompleter


class TestLoadContextCompleter:
    def setup_method(self):
        self.completer = LoadContextCompleter()
        self.event = MagicMock()

    def _get_completions(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        doc = Document(text, cursor_pos)
        return list(self.completer.get_completions(doc, self.event))

    def test_no_trigger(self):
        result = self._get_completions("hello")
        assert result == []

    def test_just_trigger_no_space(self):
        result = self._get_completions("/load_context")
        assert len(result) == 1
        assert result[0].text == "/load_context "

    def test_trigger_with_space_no_contexts(self):
        with tempfile.TemporaryDirectory() as td:
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", td
            ):
                result = self._get_completions("/load_context ")
                assert result == []

    def test_trigger_with_contexts(self):
        with tempfile.TemporaryDirectory() as td:
            contexts_dir = os.path.join(td, "contexts")
            os.makedirs(contexts_dir)
            # Create fake pkl files
            for name in ["session1.pkl", "session2.pkl"]:
                with open(os.path.join(contexts_dir, name), "w") as f:
                    f.write("")
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", td
            ):
                result = self._get_completions("/load_context ")
                names = [c.text for c in result]
                assert "session1" in names
                assert "session2" in names

    def test_trigger_with_filter(self):
        with tempfile.TemporaryDirectory() as td:
            contexts_dir = os.path.join(td, "contexts")
            os.makedirs(contexts_dir)
            for name in ["alpha.pkl", "beta.pkl"]:
                with open(os.path.join(contexts_dir, name), "w") as f:
                    f.write("")
            with patch(
                "code_puppy.command_line.load_context_completion.CONFIG_DIR", td
            ):
                result = self._get_completions("/load_context al")
                names = [c.text for c in result]
                assert "alpha" in names
                assert "beta" not in names

    def test_exception_in_listing(self):
        with patch(
            "code_puppy.command_line.load_context_completion.CONFIG_DIR",
            "/nonexistent_xyz",
        ):
            result = self._get_completions("/load_context ")
            assert result == []
