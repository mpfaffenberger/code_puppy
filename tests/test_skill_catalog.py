"""Tests for bundled skill catalog.

These tests primarily use the real bundled catalog singleton (which discovers
skills shipped in-repo under `code_puppy/bundled_skills`).

We keep tests small, deterministic, and filesystem-light.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_puppy.plugins.agent_skills.skill_catalog import (
    SkillCatalog,
    SkillCatalogEntry,
    _format_display_name,
    catalog,
)


def test_catalog_discovers_bundled_skills() -> None:
    entries = catalog.get_all()
    assert entries, "Expected bundled catalog to contain at least one skill"

    # Sanity check: one known bundled skill id.
    assert any(e.id == "data-exploration" for e in entries)


def test_catalog_list_categories() -> None:
    categories = catalog.list_categories()
    assert categories, "Expected at least one category"
    assert categories == sorted(categories, key=str.lower)
    assert "Data" in categories


def test_catalog_get_by_category() -> None:
    data_skills = catalog.get_by_category("Data")
    assert data_skills, "Expected Data category to contain skills"
    assert {e.category for e in data_skills} == {"Data"}
    assert any(e.id == "data-exploration" for e in data_skills)


def test_catalog_get_by_category_case_insensitive() -> None:
    assert catalog.get_by_category("data") == catalog.get_by_category("Data")


def test_catalog_get_by_id() -> None:
    entry = catalog.get_by_id("data-exploration")
    assert entry is not None
    assert entry.id == "data-exploration"
    assert entry.category == "Data"


def test_catalog_get_by_id_unknown() -> None:
    assert catalog.get_by_id("definitely-not-a-real-skill") is None


def test_catalog_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Name/id search (real catalog)
    results = catalog.search("sql-queries")
    assert any(e.id == "sql-queries" for e in results)

    # Description search (real catalog) - keyword appears in data-exploration description.
    results = catalog.search("outliers")
    assert any(e.id == "data-exploration" for e in results)

    # Tag search: bundled skills currently dont ship tags, so we create a tiny
    # temporary bundled-skills tree and monkeypatch discovery for a dedicated catalog.
    bundled_root = tmp_path / "bundled_skills"
    skill_dir = bundled_root / "Data" / "tagged-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: tagged-skill\n"
        "description: A skill created for testing tag search\n"
        "tags:\n"
        "  - testing\n"
        "  - automation\n"
        "---\n"
        "\n"
        "# Tagged Skill\n",
        encoding="utf-8",
    )

    import code_puppy.plugins.agent_skills.skill_catalog as sc

    monkeypatch.setattr(sc, "_get_bundled_skills_dir", lambda: bundled_root)
    tagged_catalog = SkillCatalog()

    tagged_results = tagged_catalog.search("automation")
    assert any(e.id == "tagged-skill" for e in tagged_results)


def test_catalog_search_empty() -> None:
    assert catalog.search("") == []
    assert catalog.search("   ") == []


def test_catalog_entry_fields() -> None:
    entry = catalog.get_by_id("data-context-extractor")
    assert entry is not None, "Expected known bundled skill to exist"

    assert isinstance(entry, SkillCatalogEntry)

    assert entry.id
    assert entry.name
    assert entry.display_name
    assert entry.description
    assert entry.category

    assert isinstance(entry.tags, list)
    assert all(isinstance(t, str) for t in entry.tags)

    assert isinstance(entry.source_path, Path)
    assert entry.source_path.is_dir()

    assert isinstance(entry.has_scripts, bool)
    assert isinstance(entry.has_references, bool)

    assert isinstance(entry.file_count, int)
    assert entry.file_count > 0


def test_format_display_name() -> None:
    assert _format_display_name("data-exploration") == "Data Exploration"
    assert _format_display_name("contract_review") == "Contract Review"
    assert _format_display_name("pdf") == "PDF"
    assert _format_display_name("sql-queries") == "SQL Queries"
    assert _format_display_name("") == ""
    assert _format_display_name("   ") == ""
