"""Tests for the agent_skills implementation of the neutral provider seam."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.callbacks import clear_callbacks, register_callback
from code_puppy.plugins.agent_skills.provider import AgentSkillsProvider


@pytest.mark.plugin_skills
def test_provider_listing_does_not_recurse_through_register_skills(
    tmp_path, monkeypatch
):
    """Discovery sees provider registrations but never invokes/materializes them."""
    from code_puppy.plugins.agent_skills import discovery, enabled_skills

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example\ndescription: Example skill\ntags:\n  - test\n---\n",
        encoding="utf-8",
    )

    provider = AgentSkillsProvider()
    clear_callbacks("register_skills")
    register_callback("register_skills", lambda: [{"provider": provider}])
    discovery._plugin_skills_cache = None
    discovery._plugin_skills_signature = None
    monkeypatch.setattr(
        discovery, "_PLUGIN_SKILLS_CACHE_DIR", tmp_path / "plugin-cache"
    )
    monkeypatch.setattr(enabled_skills._config, "get_skills_enabled", lambda: True)
    monkeypatch.setattr(
        enabled_skills._config,
        "get_skill_directories",
        lambda: [str(skills_root)],
    )
    monkeypatch.setattr(enabled_skills._config, "get_disabled_skills", set)
    # discover_skills() resolves dirs via names bound at module load, not the patched
    # config attr — pin those too so the test stays hermetic from real default-dir skills.
    monkeypatch.setattr(discovery, "get_skill_directories", lambda: [str(skills_root)])
    monkeypatch.setattr(discovery, "get_default_skill_directories", lambda: [])

    try:
        assert provider.list_enabled_skills() == [
            {
                "name": "example",
                "description": "Example skill",
                "path": str(skill_dir),
                "tags": ["test"],
                "version": None,
                "author": None,
            }
        ]
        assert not list((tmp_path / "plugin-cache").rglob("SKILL.md"))
    finally:
        clear_callbacks("register_skills")
        discovery._plugin_skills_cache = None
        discovery._plugin_skills_signature = None


def test_provider_delegates_config_content_resources_and_catalog():
    provider = AgentSkillsProvider()
    skill_path = Path("/skill")
    info = MagicMock(name="info", path=skill_path)
    info.name = "example"
    catalog_entry = MagicMock(id="remote-example")

    with (
        patch(
            "code_puppy.plugins.agent_skills.provider.get_skills_enabled",
            return_value=True,
        ),
        patch(
            "code_puppy.plugins.agent_skills.provider.get_disabled_skills",
            return_value={"disabled"},
        ),
        patch(
            "code_puppy.plugins.agent_skills.provider.iter_enabled_skills",
            return_value=iter([info]),
        ),
        patch(
            "code_puppy.plugins.agent_skills.provider.load_full_skill_content",
            return_value="# body",
        ),
        patch(
            "code_puppy.plugins.agent_skills.provider.get_skill_resources",
            return_value=[skill_path / "reference.md"],
        ),
        patch(
            "code_puppy.plugins.agent_skills.provider.catalog.get_all",
            return_value=[catalog_entry],
        ),
    ):
        assert provider.is_enabled() is True
        assert provider.get_disabled_skill_names() == {"disabled"}
        assert provider.find_enabled_skill_path("example") == skill_path
        assert provider.find_enabled_skill_path("missing") is None
        assert provider.load_skill_content(skill_path) == "# body"
        assert provider.get_skill_resources(skill_path) == [skill_path / "reference.md"]
        assert provider.get_catalog_skill_ids() == ["remote-example"]
