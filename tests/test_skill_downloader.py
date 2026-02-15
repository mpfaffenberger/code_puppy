"""Tests for remote skill downloader/installer."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import code_puppy.plugins.agent_skills.downloader as dl


@pytest.fixture(autouse=True)
def _no_refresh(monkeypatch):
    """Fixture that prevents catalog refresh during tests."""

    monkeypatch.setattr(dl, "refresh_skill_cache", lambda: None)


def _make_zip(path: Path, files: dict[str, str]) -> None:
    """Create a zip file with given file contents."""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_download_and_install_success(tmp_path: Path, monkeypatch) -> None:
    """Test successful download and installation of a skill."""

    skill_name = "test-skill"
    skills_dir = tmp_path / "skills"

    src_zip = tmp_path / "src.zip"
    _make_zip(
        src_zip,
        {
            "SKILL.md": "---\nname: test-skill\ndescription: hi\n---\n",
            "README.txt": "hello",
        },
    )

    def fake_download(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download)

    result = dl.download_and_install_skill(
        skill_name=skill_name,
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
        force=False,
    )

    assert result.success is True
    assert result.installed_path == skills_dir / skill_name
    assert (skills_dir / skill_name / "SKILL.md").is_file()


def test_download_fails(tmp_path: Path, monkeypatch) -> None:
    """Test graceful handling when download fails."""

    monkeypatch.setattr(dl, "_download_to_file", lambda url, dest: False)

    result = dl.download_and_install_skill(
        skill_name="test-skill",
        download_url="https://example.test/test-skill.zip",
        target_dir=tmp_path / "skills",
    )

    assert result.success is False
    assert "Failed to download" in result.message


def test_already_installed_no_force(tmp_path: Path, monkeypatch) -> None:
    """Test that already-installed skills are skipped without force."""

    skill_name = "test-skill"
    skills_dir = tmp_path / "skills"

    src_zip = tmp_path / "src.zip"
    _make_zip(src_zip, {"SKILL.md": "---\nname: test-skill\ndescription: hi\n---\n"})

    def fake_download(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download)

    first = dl.download_and_install_skill(
        skill_name=skill_name,
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
    )
    assert first.success is True

    second = dl.download_and_install_skill(
        skill_name=skill_name,
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
        force=False,
    )

    assert second.success is False
    assert "already installed" in second.message.lower()


def test_already_installed_with_force(tmp_path: Path, monkeypatch) -> None:
    """Test that force flag replaces already-installed skills."""

    skill_name = "test-skill"
    skills_dir = tmp_path / "skills"

    src_zip_1 = tmp_path / "src1.zip"
    _make_zip(src_zip_1, {"SKILL.md": "---\nname: test-skill\ndescription: v1\n---\n"})

    src_zip_2 = tmp_path / "src2.zip"
    _make_zip(src_zip_2, {"SKILL.md": "---\nname: test-skill\ndescription: v2\n---\n"})

    def fake_download_v1(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip_1.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download_v1)

    first = dl.download_and_install_skill(
        skill_name=skill_name,
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
    )
    assert first.success is True

    # Now reinstall with different zip
    def fake_download_v2(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip_2.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download_v2)

    second = dl.download_and_install_skill(
        skill_name=skill_name,
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
        force=True,
    )
    assert second.success is True

    installed = (skills_dir / skill_name / "SKILL.md").read_text(encoding="utf-8")
    assert "v2" in installed


def test_invalid_zip(tmp_path: Path, monkeypatch) -> None:
    """Test handling of corrupted zip archives."""

    skills_dir = tmp_path / "skills"
    garbage = tmp_path / "garbage.zip"
    garbage.write_bytes(b"not a zip")

    def fake_download(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(garbage.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download)

    result = dl.download_and_install_skill(
        skill_name="test-skill",
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
    )

    assert result.success is False
    assert "valid zip" in result.message.lower()


def test_missing_skill_md_in_zip(tmp_path: Path, monkeypatch) -> None:
    """Test handling of zip archives missing SKILL.md."""

    skills_dir = tmp_path / "skills"
    src_zip = tmp_path / "src.zip"
    _make_zip(src_zip, {"README.md": "no skill md"})

    def fake_download(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download)

    result = dl.download_and_install_skill(
        skill_name="test-skill",
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
    )

    assert result.success is False
    assert "missing skill.md" in result.message.lower()


def test_zip_with_subdirectory(tmp_path: Path, monkeypatch) -> None:
    """Zip contains a single top-level directory; installer should flatten it."""

    skills_dir = tmp_path / "skills"
    src_zip = tmp_path / "src.zip"

    _make_zip(
        src_zip,
        {
            "some-folder/SKILL.md": "---\nname: test-skill\ndescription: hi\n---\n",
            "some-folder/foo.txt": "bar",
        },
    )

    def fake_download(url: str, dest: Path) -> bool:
        """Fake download function for testing."""

        dest.write_bytes(src_zip.read_bytes())
        return True

    monkeypatch.setattr(dl, "_download_to_file", fake_download)

    result = dl.download_and_install_skill(
        skill_name="test-skill",
        download_url="https://example.test/test-skill.zip",
        target_dir=skills_dir,
    )

    assert result.success is True
    assert (skills_dir / "test-skill" / "SKILL.md").is_file()
    assert (skills_dir / "test-skill" / "foo.txt").is_file()
