"""Tests for skills_completion.py - 100% coverage."""

from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from code_puppy.command_line.skills_completion import (
    SkillsCompleter,
    load_catalog_skill_ids,
)


class TestLoadCatalogSkillIds:
    @patch("code_puppy.plugins.agent_skills.skill_catalog.catalog")
    def test_success(self, mock_catalog):
        mock_entry = MagicMock()
        mock_entry.id = "test-skill"
        mock_catalog.get_all.return_value = [mock_entry]
        result = load_catalog_skill_ids()
        assert result == ["test-skill"]

    def test_import_failure(self):
        with patch.dict(
            "sys.modules", {"code_puppy.plugins.agent_skills.skill_catalog": None}
        ):
            result = load_catalog_skill_ids()
            assert result == []


class TestSkillsCompleter:
    def setup_method(self):
        self.completer = SkillsCompleter()
        self.event = MagicMock()

    def _get_completions(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        doc = Document(text, cursor_pos)
        return list(self.completer.get_completions(doc, self.event))

    def test_no_trigger(self):
        assert self._get_completions("hello") == []

    def test_trigger_no_space(self):
        assert self._get_completions("/skills") == []

    def test_show_all_subcommands(self):
        result = self._get_completions("/skills ")
        names = [c.text for c in result]
        assert "list" in names
        assert "install" in names
        assert "enable" in names

    def test_partial_subcommand(self):
        result = self._get_completions("/skills li")
        names = [c.text for c in result]
        assert "list" in names
        assert "install" not in names

    @patch.object(
        SkillsCompleter, "_get_skill_ids", return_value=["skill-a", "skill-b"]
    )
    def test_install_show_all_skills(self, mock_ids):
        result = self._get_completions("/skills install ")
        names = [c.text for c in result]
        assert "skill-a" in names
        assert "skill-b" in names

    @patch.object(SkillsCompleter, "_get_skill_ids", return_value=["alpha", "beta"])
    def test_install_filter_skills(self, mock_ids):
        result = self._get_completions("/skills install al")
        names = [c.text for c in result]
        assert "alpha" in names
        assert "beta" not in names

    def test_no_further_completion(self):
        # After a full subcommand + space (non-install)
        result = self._get_completions("/skills list ")
        assert result == []

    def test_get_skill_ids_cache(self):
        with patch.object(self.completer, "_skill_ids_cache", ["cached"]):
            self.completer._cache_timestamp = 999999999999.0
            result = self.completer._get_skill_ids()
            assert result == ["cached"]

    def test_get_skill_ids_refresh(self):
        self.completer._skill_ids_cache = None
        self.completer._cache_timestamp = None
        with patch(
            "code_puppy.command_line.skills_completion.load_catalog_skill_ids",
            return_value=["new"],
        ):
            result = self.completer._get_skill_ids()
            assert result == ["new"]

    def test_not_at_beginning(self):
        result = self._get_completions("hello /skills ")
        assert result == []
