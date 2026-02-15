"""Tests for the remote-backed skill catalog adapter."""

from __future__ import annotations

import importlib

import code_puppy.plugins.agent_skills.remote_catalog as rc
from code_puppy.plugins.agent_skills.remote_catalog import (
    RemoteCatalogData,
    RemoteSkillEntry,
)


def _load_skill_catalog():
    """Import/reload skill_catalog without hitting the network.

    skill_catalog creates a module-level singleton at import time, so we must
    patch the remote fetcher before importing.
    """

    def _no_fetch(*args, **kwargs):
        return None

    rc.fetch_remote_catalog = _no_fetch  # type: ignore[assignment]
    module = importlib.import_module("code_puppy.plugins.agent_skills.skill_catalog")
    return importlib.reload(module)


def _mk_remote(
    *,
    base_url: str = "https://example.test",
    entries: list[RemoteSkillEntry],
) -> RemoteCatalogData:
    return RemoteCatalogData(
        version="1.0.0",
        base_url=base_url,
        total_skills=len(entries),
        groups=[],
        entries=entries,
    )


def test_format_display_name() -> None:
    sc_module = _load_skill_catalog()

    assert sc_module._format_display_name("data-exploration") == "Data Exploration"
    assert sc_module._format_display_name("pdf") == "PDF"
    assert sc_module._format_display_name("sql-queries") == "SQL Queries"
    assert sc_module._format_display_name("") == ""


def test_catalog_with_remote_data(monkeypatch) -> None:
    sc_module = _load_skill_catalog()

    remote = _mk_remote(
        entries=[
            RemoteSkillEntry(
                name="data-exploration",
                description="Explore data sets",
                group="data",
                download_url="https://example.test/skills/data-exploration.zip",
                zip_size_bytes=1234,
                file_count=1,
                has_scripts=False,
                has_references=False,
                has_license=False,
            ),
            RemoteSkillEntry(
                name="sql-queries",
                description="Write SQL",
                group="data",
                download_url="https://example.test/skills/sql-queries.zip",
                zip_size_bytes=2345,
                file_count=2,
                has_scripts=True,
                has_references=False,
                has_license=True,
            ),
            RemoteSkillEntry(
                name="audit-support",
                description="Support SOX audits",
                group="finance",
                download_url="https://example.test/skills/audit-support.zip",
                zip_size_bytes=3456,
                file_count=3,
                has_scripts=False,
                has_references=True,
                has_license=False,
            ),
        ]
    )

    monkeypatch.setattr(sc_module, "fetch_remote_catalog", lambda: remote)

    cat = sc_module.SkillCatalog()
    all_entries = cat.get_all()

    assert len(all_entries) == 3
    assert all(isinstance(e, sc_module.SkillCatalogEntry) for e in all_entries)

    # get_by_id
    sql_entry = cat.get_by_id("sql-queries")
    assert sql_entry is not None
    assert sql_entry.display_name == "SQL Queries"

    # list_categories
    assert cat.list_categories() == ["data", "finance"]

    # get_by_category
    data_entries = cat.get_by_category("data")
    assert {e.id for e in data_entries} == {"data-exploration", "sql-queries"}

    # search
    assert {e.id for e in cat.search("sql")} == {"sql-queries"}
    assert {e.id for e in cat.search("SOX")} == {"audit-support"}
    assert {e.id for e in cat.search("finance")} == {"audit-support"}


def test_catalog_empty_when_fetch_fails(monkeypatch) -> None:
    sc_module = _load_skill_catalog()

    monkeypatch.setattr(sc_module, "fetch_remote_catalog", lambda: None)

    cat = sc_module.SkillCatalog()
    assert cat.get_all() == []
    assert cat.list_categories() == []
    assert cat.get_by_id("anything") is None


def test_search_case_insensitive(monkeypatch) -> None:
    sc_module = _load_skill_catalog()

    remote = _mk_remote(
        entries=[
            RemoteSkillEntry(
                name="pdf-tools",
                description="Work with PDF files",
                group="office",
                download_url="https://example.test/skills/pdf-tools.zip",
                zip_size_bytes=1,
                file_count=1,
                has_scripts=False,
                has_references=False,
                has_license=False,
            )
        ]
    )
    monkeypatch.setattr(sc_module, "fetch_remote_catalog", lambda: remote)

    cat = sc_module.SkillCatalog()
    assert [e.id for e in cat.search("pdf")] == ["pdf-tools"]
    assert [e.id for e in cat.search("PDF")] == ["pdf-tools"]
    assert [e.id for e in cat.search("Office")] == ["pdf-tools"]


def test_get_by_category_case_insensitive(monkeypatch) -> None:
    sc_module = _load_skill_catalog()

    remote = _mk_remote(
        entries=[
            RemoteSkillEntry(
                name="close-management",
                description="Month-end close",
                group="Finance",
                download_url="https://example.test/skills/close-management.zip",
                zip_size_bytes=1,
                file_count=1,
                has_scripts=False,
                has_references=False,
                has_license=False,
            )
        ]
    )
    monkeypatch.setattr(sc_module, "fetch_remote_catalog", lambda: remote)

    cat = sc_module.SkillCatalog()
    assert [e.id for e in cat.get_by_category("finance")] == ["close-management"]
    assert [e.id for e in cat.get_by_category("FINANCE")] == ["close-management"]


def test_catalog_entry_fields(monkeypatch) -> None:
    sc_module = _load_skill_catalog()

    remote = _mk_remote(
        entries=[
            RemoteSkillEntry(
                name="data-exploration",
                description="Explore data sets",
                group="data",
                download_url="https://example.test/skills/data-exploration.zip",
                zip_size_bytes=1234,
                file_count=42,
                has_scripts=True,
                has_references=True,
                has_license=False,
            )
        ]
    )
    monkeypatch.setattr(sc_module, "fetch_remote_catalog", lambda: remote)

    cat = sc_module.SkillCatalog()
    entry = cat.get_by_id("data-exploration")
    assert entry is not None

    assert entry.id == "data-exploration"
    assert entry.name == "data-exploration"
    assert entry.display_name == "Data Exploration"
    assert entry.description == "Explore data sets"
    assert entry.category == "data"
    assert entry.tags == []
    assert entry.source_path is None
    assert entry.has_scripts is True
    assert entry.has_references is True
    assert entry.file_count == 42
    assert entry.download_url == "https://example.test/skills/data-exploration.zip"
    assert entry.zip_size_bytes == 1234
