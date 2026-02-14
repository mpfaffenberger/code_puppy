"""Focused regression tests for agent skill discovery.

Keep this file small and targeted to avoid growing the main agent skills test module.
"""

from code_puppy.plugins.agent_skills.discovery import discover_skills


def test_discover_skills_deduplicates_duplicate_skill_directories(tmp_path):
    """Duplicate scan roots should not yield duplicate discovered skills."""
    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    skill_a = skill_root / "skill-a"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("---\nname: skill-a\ndescription: Skill A\n---\n")

    skills = discover_skills(directories=[skill_root, skill_root])

    assert len(skills) == 1
    assert skills[0].name == "skill-a"
    assert skills[0].path == skill_a
