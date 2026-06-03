"""Logging behavior tests for agent skills metadata parsing."""

import logging
import sys

from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata

_REGISTER_CALLBACKS_MODULE = "code_puppy.plugins.agent_skills.register_callbacks"
_AGENT_SKILLS_PACKAGE = "code_puppy.plugins.agent_skills"


def _snapshot_callbacks():
    """Snapshot callback registry so importing plugin callbacks stays harmless."""
    from code_puppy import callbacks

    snapshot = {phase: list(funcs) for phase, funcs in callbacks._callbacks.items()}
    return callbacks, snapshot, _REGISTER_CALLBACKS_MODULE in sys.modules


def _restore_callbacks(callbacks, snapshot, was_imported):
    callbacks._callbacks.clear()
    callbacks._callbacks.update(
        {phase: list(funcs) for phase, funcs in snapshot.items()}
    )

    if was_imported:
        return

    sys.modules.pop(_REGISTER_CALLBACKS_MODULE, None)
    package = sys.modules.get(_AGENT_SKILLS_PACKAGE)
    if package is not None and hasattr(package, "register_callbacks"):
        delattr(package, "register_callbacks")


def test_parse_skill_metadata_invalid_content_is_quiet(tmp_path, caplog):
    """Invalid skill metadata is an expected skip, not terminal confetti."""
    skill_dir = tmp_path / "invalid-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("## Overview\nNot Code Puppy metadata.\n")

    with caplog.at_level(logging.WARNING):
        metadata = parse_skill_metadata(skill_dir)

    assert metadata is None
    assert "No valid frontmatter" not in caplog.text


def test_prompt_section_skips_invalid_skill_metadata_quietly(
    tmp_path, caplog, monkeypatch
):
    """Invalid discovered skills are skipped without startup warning spam."""
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "concord"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("## Overview\nNot Code Puppy metadata.\n")

    callbacks, snapshot, was_imported = _snapshot_callbacks()
    try:
        from code_puppy.plugins.agent_skills import register_callbacks

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skills_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            lambda: set(),
        )
        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            lambda: [str(skills_root)],
        )

        with caplog.at_level(logging.WARNING):
            section = register_callbacks._get_skills_prompt_section()

        assert section is None
        assert "No valid frontmatter" not in caplog.text
        assert "Failed to parse metadata" not in caplog.text
    finally:
        _restore_callbacks(callbacks, snapshot, was_imported)
