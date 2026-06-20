"""Regression tests for plugin skill discovery races."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from code_puppy.plugins.agent_skills import discovery


def test_collect_plugin_skills_is_stable_under_concurrent_calls(monkeypatch, tmp_path):
    """Concurrent discovery runs should not delete the shared cache root.

    Historically, ``_collect_plugin_skills()`` removed the entire
    ``plugin-skills`` cache directory on every call. When multiple threads hit
    discovery at the same time, one thread could remove the cache while
    another was creating or reading it, causing Windows-specific
    ``FileExistsError`` / ``FileNotFoundError`` failures.
    """

    monkeypatch.setattr(discovery, "_PLUGIN_SKILLS_CACHE_DIR", tmp_path / "plugin-skills")

    entries = [
        (
            "tests.fake_plugin.register_callbacks",
            "register_skills",
            {
                "name": "demo-skill",
                "frontmatter": {"description": "demo skill"},
                "body": "# Demo skill\n",
            },
        )
    ]
    monkeypatch.setattr(discovery, "_iter_plugin_skill_registrations", lambda: iter(entries))

    def _collect_once() -> tuple[list[str], Path]:
        skills = discovery._collect_plugin_skills()
        names = [skill.name for skill in skills]
        skill_path = skills[0].path
        return names, skill_path

    results: list[tuple[list[str], Path]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_collect_once) for _ in range(40)]
        for future in as_completed(futures):
            results.append(future.result())

    assert len(results) == 40
    for names, skill_path in results:
        assert names == ["demo-skill"]
        assert (skill_path / "SKILL.md").is_file()

    owner_dir = tmp_path / "plugin-skills" / "tests.fake_plugin.register_callbacks"
    assert owner_dir.is_dir()
    assert (owner_dir / "demo-skill" / "SKILL.md").is_file()
