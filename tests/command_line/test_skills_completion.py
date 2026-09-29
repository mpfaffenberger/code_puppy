"""Tests for skills_completion.py - 100% coverage."""

from unittest.mock import MagicMock

import pytest
from termflow.tui.completion import Document

from code_puppy.command_line.skills_completion import SkillsCompleter


class TestSkillsCompleter:
    def setup_method(self):
        self.completer = SkillsCompleter()
        self.event = MagicMock()

    def _get_completions(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        doc = Document(text, cursor_pos)
        return list(self.completer.get_completions(doc, self.event))

    @pytest.mark.parametrize("text", ["hello", "/skills"])
    def test_no_completions(self, text):
        assert self._get_completions(text) == []

    def test_show_all_subcommands(self):
        result = self._get_completions("/skills ")
        names = [c.text for c in result]
        assert "list" in names
        assert "enable" in names
        # The remote marketplace is gone; don't advertise its command.
        assert "install" not in names

    def test_partial_subcommand(self):
        result = self._get_completions("/skills li")
        names = [c.text for c in result]
        assert names == ["list"]

    @pytest.mark.parametrize(
        "text",
        [
            "/skills list ",
            "hello /skills ",
            # No catalog anymore: install must not complete skill ids.
            "/skills install ",
            "/skills install al",
        ],
    )
    def test_no_further_completion(self, text):
        # After a full subcommand + space, or when /skills isn't at the start
        result = self._get_completions(text)
        assert result == []
