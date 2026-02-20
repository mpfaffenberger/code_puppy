"""Tests for agent_skills/downloader.py full coverage."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from code_puppy.plugins.agent_skills.downloader import (
    _determine_extracted_root,
    _download_to_file,
    _is_within_directory,
    _safe_extract_zip,
    _safe_rmtree,
    _stage_normalized_install,
    _validate_zip_safety,
    _zip_entry_parts,
    download_and_install_skill,
)


class TestZipEntryParts:
    def test_normal(self):
        assert _zip_entry_parts("a/b/c.txt") == ["a", "b", "c.txt"]

    def test_backslash(self):
        assert _zip_entry_parts("a\\b\\c.txt") == ["a", "b", "c.txt"]

    def test_dots_and_empty(self):
        assert _zip_entry_parts("./a//b/./c") == ["a", "b", "c"]


class TestSafeRmtree:
    def test_nonexistent(self, tmp_path):
        assert _safe_rmtree(tmp_path / "nope") is True

    def test_success(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        (d / "f.txt").write_text("x")
        assert _safe_rmtree(d) is True
        assert not d.exists()

    def test_failure(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        with patch("shutil.rmtree", side_effect=OSError("nope")):
            assert _safe_rmtree(d) is False


class TestDownloadToFile:
    def test_success(self, tmp_path):
        dest = tmp_path / "out.zip"
        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"data"]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.return_value = mock_response

        with patch(
            "code_puppy.plugins.agent_skills.downloader.httpx.Client",
            return_value=mock_client,
        ):
            assert _download_to_file("http://example.com/f.zip", dest) is True

    def test_http_error(self, tmp_path):
        dest = tmp_path / "out.zip"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.reason_phrase = "Not Found"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=mock_resp
        )
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.return_value = mock_resp

        with patch(
            "code_puppy.plugins.agent_skills.downloader.httpx.Client",
            return_value=mock_client,
        ):
            assert _download_to_file("http://example.com/f.zip", dest) is False

    def test_connect_error(self, tmp_path):
        dest = tmp_path / "out.zip"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.side_effect = httpx.ConnectError("fail")

        with patch(
            "code_puppy.plugins.agent_skills.downloader.httpx.Client",
            return_value=mock_client,
        ):
            assert _download_to_file("http://example.com/f.zip", dest) is False

    def test_unexpected_error(self, tmp_path):
        dest = tmp_path / "out.zip"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.side_effect = RuntimeError("boom")

        with patch(
            "code_puppy.plugins.agent_skills.downloader.httpx.Client",
            return_value=mock_client,
        ):
            assert _download_to_file("http://example.com/f.zip", dest) is False


class TestIsWithinDirectory:
    def test_within(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        child.parent.mkdir(parents=True, exist_ok=True)
        child.touch()
        assert _is_within_directory(tmp_path, child) is True

    def test_outside(self, tmp_path):
        # Use a path that resolves outside
        assert _is_within_directory(tmp_path, Path("/etc/passwd")) is False


class TestValidateZipSafety:
    def test_safe_zip(self, tmp_path):
        zp = tmp_path / "safe.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("file.txt", "hello")
        with zipfile.ZipFile(zp, "r") as zf:
            assert _validate_zip_safety(zf) is None

    def test_absolute_path(self, tmp_path):
        zp = tmp_path / "abs.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("/etc/passwd", "bad")
        with zipfile.ZipFile(zp, "r") as zf:
            result = _validate_zip_safety(zf)
            assert result is not None
            assert "absolute" in result

    def test_traversal(self, tmp_path):
        zp = tmp_path / "trav.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("../../../etc/passwd", "bad")
        with zipfile.ZipFile(zp, "r") as zf:
            result = _validate_zip_safety(zf)
            assert result is not None
            assert "traversal" in result

    def test_too_large(self, tmp_path):
        zp = tmp_path / "big.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            # Create entry that claims huge size
            zf.writestr("big.txt", "x")

        # Mock infolist to return huge file_size
        mock_info = MagicMock()
        mock_info.is_dir.return_value = False
        mock_info.file_size = 100 * 1024 * 1024  # 100MB
        mock_info.filename = "big.txt"

        mock_zf = MagicMock()
        mock_zf.infolist.return_value = [mock_info]
        result = _validate_zip_safety(mock_zf)
        assert result is not None
        assert "large" in result


class TestSafeExtractZip:
    def test_success(self, tmp_path):
        zp = tmp_path / "test.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("SKILL.md", "# Skill")
            zf.writestr("sub/", "")  # directory
        extract_dir = tmp_path / "extracted"
        with zipfile.ZipFile(zp, "r") as zf:
            assert _safe_extract_zip(zf, extract_dir) is True
        assert (extract_dir / "SKILL.md").exists()

    def test_skips_macosx(self, tmp_path):
        zp = tmp_path / "test.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("__MACOSX/junk", "junk")
            zf.writestr("SKILL.md", "# Skill")
        extract_dir = tmp_path / "extracted"
        with zipfile.ZipFile(zp, "r") as zf:
            assert _safe_extract_zip(zf, extract_dir) is True
        assert not (extract_dir / "__MACOSX").exists()

    def test_blocked_path(self, tmp_path):
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        mock_info = MagicMock()
        mock_info.filename = "../../../etc/passwd"
        mock_info.is_dir.return_value = False

        mock_zf = MagicMock()
        mock_zf.infolist.return_value = [mock_info]

        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._zip_entry_parts",
                return_value=["..", "..", "etc", "passwd"],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._is_within_directory",
                return_value=False,
            ),
        ):
            assert _safe_extract_zip(mock_zf, extract_dir) is False

    def test_exception(self, tmp_path):
        extract_dir = tmp_path / "extracted"
        mock_zf = MagicMock()
        mock_zf.infolist.side_effect = RuntimeError("boom")
        assert _safe_extract_zip(mock_zf, extract_dir) is False


class TestDetermineExtractedRoot:
    def test_skill_md_at_root(self, tmp_path):
        (tmp_path / "SKILL.md").write_text("# Skill")
        assert _determine_extracted_root(tmp_path) == tmp_path

    def test_skill_md_in_subfolder(self, tmp_path):
        sub = tmp_path / "my_skill"
        sub.mkdir()
        (sub / "SKILL.md").write_text("# Skill")
        assert _determine_extracted_root(tmp_path) == sub

    def test_no_skill_md(self, tmp_path):
        (tmp_path / "README.md").write_text("hi")
        assert _determine_extracted_root(tmp_path) is None

    def test_files_at_root_no_skill_md(self, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        assert _determine_extracted_root(tmp_path) is None

    def test_multiple_dirs(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        assert _determine_extracted_root(tmp_path) is None

    def test_exception(self):
        with patch(
            "code_puppy.plugins.agent_skills.downloader.Path.is_file",
            side_effect=RuntimeError,
        ):
            # Should return None gracefully
            result = _determine_extracted_root(Path("/fake"))
            assert result is None


class TestStageNormalizedInstall:
    def test_success(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "SKILL.md").write_text("# Skill")
        staging = tmp_path / "staging"
        staging.mkdir()
        result = _stage_normalized_install(src, "my_skill", staging)
        assert result is not None
        assert (result / "SKILL.md").exists()

    def test_missing_skill_md(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "README.md").write_text("hi")
        staging = tmp_path / "staging"
        staging.mkdir()
        result = _stage_normalized_install(src, "my_skill", staging)
        assert result is None

    def test_exception(self, tmp_path):
        with patch("shutil.copytree", side_effect=RuntimeError("boom")):
            result = _stage_normalized_install(tmp_path, "sk", tmp_path / "staging")
            assert result is None


class TestDownloadAndInstallSkill:
    def test_empty_name(self):
        result = download_and_install_skill("", "http://example.com/s.zip")
        assert not result.success

    def test_traversal_name(self):
        result = download_and_install_skill("../bad", "http://example.com/s.zip")
        assert not result.success

    def test_already_exists_no_force(self, tmp_path):
        skill_dir = tmp_path / "sk"
        skill_dir.mkdir()
        result = download_and_install_skill(
            "sk", "http://example.com/s.zip", target_dir=tmp_path
        )
        assert not result.success
        assert "already installed" in result.message

    def test_force_rmtree_fails(self, tmp_path):
        skill_dir = tmp_path / "sk"
        skill_dir.mkdir()
        with patch(
            "code_puppy.plugins.agent_skills.downloader._safe_rmtree",
            return_value=False,
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path, force=True
            )
            assert not result.success

    def test_download_fails(self, tmp_path):
        with patch(
            "code_puppy.plugins.agent_skills.downloader._download_to_file",
            return_value=False,
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success

    def test_bad_zip(self, tmp_path):
        bad_zip = tmp_path / "not_a.zip"
        bad_zip.write_text("not a zip")

        with patch(
            "code_puppy.plugins.agent_skills.downloader._download_to_file",
            side_effect=lambda url, dest: dest.write_bytes(b"not a zip") or True,
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success

    def test_unsafe_zip(self, tmp_path):
        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value="dangerous",
            ),
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success
            assert "unsafe" in result.message.lower()

    def test_extract_fails(self, tmp_path):
        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=False,
            ),
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success

    def test_no_skill_md_in_extracted(self, tmp_path):
        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=None,
            ),
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success

    def test_staging_fails(self, tmp_path):
        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=tmp_path,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                return_value=None,
            ),
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=tmp_path
            )
            assert not result.success

    def test_full_success(self, tmp_path):
        staged = tmp_path / "staged_sk"
        staged.mkdir()
        (staged / "SKILL.md").write_text("# Skill")

        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=tmp_path,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                return_value=staged,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader.refresh_skill_cache",
            ),
        ):
            target = tmp_path / "target"
            target.mkdir()
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert result.success

    def test_move_fails(self, tmp_path):
        staged = tmp_path / "staged_sk"
        staged.mkdir()
        (staged / "SKILL.md").write_text("# Skill")

        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=tmp_path,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                return_value=staged,
            ),
            patch("shutil.move", side_effect=RuntimeError("fail")),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_rmtree",
                return_value=True,
            ),
        ):
            target = tmp_path / "target"
            target.mkdir()
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert not result.success

    def test_post_install_missing_skill_md(self, tmp_path):
        staged = tmp_path / "staged_sk"
        staged.mkdir()
        (staged / "SKILL.md").write_text("# Skill")

        target = tmp_path / "target"
        target.mkdir()

        def fake_move(src, dst):
            # Move but delete SKILL.md to simulate missing
            import shutil

            shutil.copytree(src, dst)
            (Path(dst) / "SKILL.md").unlink()

        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=tmp_path,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                return_value=staged,
            ),
            patch("shutil.move", side_effect=fake_move),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_rmtree",
                return_value=True,
            ),
        ):
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert not result.success

    def test_unexpected_exception(self, tmp_path):
        with patch(
            "code_puppy.plugins.agent_skills.downloader._download_to_file",
            side_effect=RuntimeError("unexpected"),
        ):
            # Need skill_dir.exists() to return False
            target = tmp_path / "t"
            target.mkdir()
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert not result.success

    def test_zip_open_generic_exception(self, tmp_path):
        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "zipfile.ZipFile",
                side_effect=RuntimeError("generic zip error"),
            ),
        ):
            target = tmp_path / "t"
            target.mkdir()
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert not result.success

    def test_refresh_cache_fails(self, tmp_path):
        staged = tmp_path / "staged_sk"
        staged.mkdir()
        (staged / "SKILL.md").write_text("# Skill")

        with (
            patch(
                "code_puppy.plugins.agent_skills.downloader._download_to_file",
                side_effect=lambda url, dest: (
                    _write_test_zip(dest, {"SKILL.md": "# S"}),
                    True,
                )[-1],
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                return_value=tmp_path,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                return_value=staged,
            ),
            patch(
                "code_puppy.plugins.agent_skills.downloader.refresh_skill_cache",
                side_effect=RuntimeError("cache fail"),
            ),
        ):
            target = tmp_path / "target"
            target.mkdir()
            result = download_and_install_skill(
                "sk", "http://example.com/s.zip", target_dir=target
            )
            assert result.success  # Still succeeds despite cache refresh failure


def _write_test_zip(dest: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(dest, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
