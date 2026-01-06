"""Tests for Jira field configuration module."""

import json

import pytest

from code_puppy.plugins.walmart_specific.jira_field_config import (
    DEFAULT_FIELD_MAPPINGS,
    _load_field_config,
    get_epic_link_field,
    get_sprint_field,
    get_story_points_field,
    reload_field_mappings,
    show_current_config,
)


class TestDefaultMappings:
    """Test default field mappings."""

    def test_default_epic_link(self):
        assert DEFAULT_FIELD_MAPPINGS["epic_link"] == "customfield_10007"

    def test_default_sprint(self):
        assert DEFAULT_FIELD_MAPPINGS["sprint"] == "customfield_10005"

    def test_default_story_points(self):
        assert DEFAULT_FIELD_MAPPINGS["story_points"] == "customfield_10002"


class TestFieldGetters:
    """Test field getter functions."""

    def test_get_epic_link_field(self):
        # Should return a string starting with customfield_
        field = get_epic_link_field()
        assert isinstance(field, str)
        assert field.startswith("customfield_")

    def test_get_sprint_field(self):
        field = get_sprint_field()
        assert isinstance(field, str)
        assert field.startswith("customfield_")

    def test_get_story_points_field(self):
        field = get_story_points_field()
        assert isinstance(field, str)
        assert field.startswith("customfield_")


class TestConfigLoading:
    """Test configuration file loading."""

    def test_load_returns_dict(self):
        mappings = _load_field_config()
        assert isinstance(mappings, dict)
        assert "epic_link" in mappings
        assert "sprint" in mappings
        assert "story_points" in mappings

    def test_reload_returns_dict(self):
        mappings = reload_field_mappings()
        assert isinstance(mappings, dict)

    def test_load_with_custom_config(self, tmp_path, monkeypatch):
        """Test loading custom config from file."""
        # Create a custom config file
        config_file = tmp_path / "jira_fields.json"
        custom_config = {
            "epic_link": "customfield_99999",
            "sprint": "customfield_88888",
            "story_points": "customfield_77777",
        }
        config_file.write_text(json.dumps(custom_config))

        # Monkeypatch the config file path
        import code_puppy.plugins.walmart_specific.jira_field_config as config_module

        monkeypatch.setattr(config_module, "FIELD_CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_field_mappings", None)  # Clear cache

        # Reload and check
        mappings = reload_field_mappings()
        assert mappings["epic_link"] == "customfield_99999"
        assert mappings["sprint"] == "customfield_88888"
        assert mappings["story_points"] == "customfield_77777"

    def test_load_with_partial_config(self, tmp_path, monkeypatch):
        """Test that partial config merges with defaults."""
        config_file = tmp_path / "jira_fields.json"
        # Only override epic_link
        custom_config = {"epic_link": "customfield_12345"}
        config_file.write_text(json.dumps(custom_config))

        import code_puppy.plugins.walmart_specific.jira_field_config as config_module

        monkeypatch.setattr(config_module, "FIELD_CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_field_mappings", None)

        mappings = reload_field_mappings()
        assert mappings["epic_link"] == "customfield_12345"  # Custom
        assert mappings["sprint"] == "customfield_10005"  # Default
        assert mappings["story_points"] == "customfield_10002"  # Default

    def test_load_with_invalid_json(self, tmp_path, monkeypatch):
        """Test that invalid JSON falls back to defaults."""
        config_file = tmp_path / "jira_fields.json"
        config_file.write_text("not valid json {{{")

        import code_puppy.plugins.walmart_specific.jira_field_config as config_module

        monkeypatch.setattr(config_module, "FIELD_CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_field_mappings", None)

        # Should not raise, just use defaults
        mappings = reload_field_mappings()
        assert mappings == DEFAULT_FIELD_MAPPINGS


class TestShowConfig:
    """Test config display function."""

    def test_show_current_config_returns_string(self):
        output = show_current_config()
        assert isinstance(output, str)
        assert "Epic Link" in output
        assert "Sprint" in output
        assert "Story Points" in output
