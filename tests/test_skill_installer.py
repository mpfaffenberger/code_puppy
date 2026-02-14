"""Tests for bundled skill installer.

These tests use tmp_path for isolation and a real bundled catalog entry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_puppy.plugins.agent_skills.installer import (
    get_default_install_dir,
    install_skill,
    is_skill_installed,
    uninstall_skill,
)
from code_puppy.plugins.agent_skills.skill_catalog import SkillCatalogEntry, catalog


@pytest.fixture(autouse=True)
def _no_refresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep installer tests fast and side-effect free.

    The installer calls refresh_skill_cache() after successful install/uninstall.
    Thats fine in production, but for unit tests its just unnecessary work.
    """

    import code_puppy.plugins.agent_skills.installer as installer

    monkeypatch.setattr(installer, "refresh_skill_cache", lambda: None)


@pytest.fixture
def sample_catalog_entry() -> SkillCatalogEntry:
    entry = catalog.get_by_id("data-context-extractor")
    assert entry is not None, "Expected bundled skill 'data-context-extractor' to exist"
    return entry


def test_install_skill(tmp_path: Path, sample_catalog_entry: SkillCatalogEntry) -> None:
    result = install_skill(sample_catalog_entry, target_dir=tmp_path)
    assert result.success is True
    assert result.error is None

    install_path = tmp_path / sample_catalog_entry.id
    assert install_path.is_dir()
    assert (install_path / "SKILL.md").is_file()

    # If the bundled skill contains these, they should get copied too.
    if sample_catalog_entry.has_scripts:
        assert (install_path / "scripts").is_dir()
    if sample_catalog_entry.has_references:
        assert (install_path / "references").is_dir()


def test_install_skill_already_exists(
    tmp_path: Path, sample_catalog_entry: SkillCatalogEntry
) -> None:
    first = install_skill(sample_catalog_entry, target_dir=tmp_path)
    assert first.success is True

    second = install_skill(sample_catalog_entry, target_dir=tmp_path, force=False)
    assert second.success is False
    assert second.error is not None
    assert "already installed" in second.error.lower()


def test_install_skill_force_overwrite(
    tmp_path: Path, sample_catalog_entry: SkillCatalogEntry
) -> None:
    first = install_skill(sample_catalog_entry, target_dir=tmp_path)
    assert first.success is True

    install_md = tmp_path / sample_catalog_entry.id / "SKILL.md"
    source_md = sample_catalog_entry.source_path / "SKILL.md"
    assert source_md.is_file()

    install_md.write_text("garbage", encoding="utf-8")
    assert install_md.read_text(encoding="utf-8") == "garbage"

    second = install_skill(sample_catalog_entry, target_dir=tmp_path, force=True)
    assert second.success is True
    assert second.was_update is True

    assert install_md.read_text(encoding="utf-8") == source_md.read_text(
        encoding="utf-8"
    )


def test_is_skill_installed(
    tmp_path: Path, sample_catalog_entry: SkillCatalogEntry
) -> None:
    assert is_skill_installed(sample_catalog_entry.id, target_dir=tmp_path) is False

    install_result = install_skill(sample_catalog_entry, target_dir=tmp_path)
    assert install_result.success is True

    assert is_skill_installed(sample_catalog_entry.id, target_dir=tmp_path) is True

    # Remove SKILL.md and ensure detection is false.
    (tmp_path / sample_catalog_entry.id / "SKILL.md").unlink()
    assert is_skill_installed(sample_catalog_entry.id, target_dir=tmp_path) is False


def test_uninstall_skill(
    tmp_path: Path, sample_catalog_entry: SkillCatalogEntry
) -> None:
    install_result = install_skill(sample_catalog_entry, target_dir=tmp_path)
    assert install_result.success is True

    uninstall_result = uninstall_skill(sample_catalog_entry.id, target_dir=tmp_path)
    assert uninstall_result.success is True
    assert uninstall_result.error is None

    assert not (tmp_path / sample_catalog_entry.id).exists()


def test_uninstall_nonexistent(tmp_path: Path) -> None:
    result = uninstall_skill("definitely-not-installed", target_dir=tmp_path)
    assert result.success is False
    assert result.error is not None
    assert "not installed" in result.error.lower()


def test_get_default_install_dir() -> None:
    assert get_default_install_dir() == Path.home() / ".code_puppy" / "skills"
