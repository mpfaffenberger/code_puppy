"""100% coverage tests for code_puppy/plugins/agent_skills/downloader.py."""

from __future__ import annotations

import shutil
import zipfile
from io import BytesIO
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

# ── _zip_entry_parts ──


def test_zip_entry_parts_basic():
    assert _zip_entry_parts("a/b/c.txt") == ["a", "b", "c.txt"]


def test_zip_entry_parts_backslashes():
    assert _zip_entry_parts("a\\b\\c.txt") == ["a", "b", "c.txt"]


def test_zip_entry_parts_dots_and_empty():
    assert _zip_entry_parts("./a//b/./c") == ["a", "b", "c"]


# ── _safe_rmtree ──


def test_safe_rmtree_nonexistent(tmp_path):
    assert _safe_rmtree(tmp_path / "nope") is True


def test_safe_rmtree_existing(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "f").write_text("x")
    assert _safe_rmtree(d) is True
    assert not d.exists()


def test_safe_rmtree_failure(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader.shutil.rmtree",
        side_effect=OSError("no"),
    ):
        d = tmp_path / "dir"
        d.mkdir()
        assert _safe_rmtree(d) is False


# ── _is_within_directory ──


def test_is_within_directory_yes(tmp_path):
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert _is_within_directory(tmp_path, child) is True


def test_is_within_directory_no(tmp_path):
    assert _is_within_directory(tmp_path / "a", tmp_path / "b") is False


def test_is_within_directory_exception():
    assert _is_within_directory(Path("/a"), Path("/b")) is False


# ── _download_to_file ──


def _make_mock_client(
    chunks=None, status_error=False, connect_error=False, generic_error=False
):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes = MagicMock(return_value=iter(chunks or [b"data"]))
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    if status_error:
        resp = httpx.Response(404, request=httpx.Request("GET", "http://x"))
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=resp.request, response=resp
        )
    elif connect_error:
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("fail"))
        return mock_client
    elif generic_error:
        mock_client.stream = MagicMock(side_effect=RuntimeError("boom"))
        return mock_client

    mock_client.stream = MagicMock(return_value=mock_response)
    return mock_client


def test_download_to_file_success(tmp_path):
    dest = tmp_path / "sub" / "out.zip"
    mc = _make_mock_client(chunks=[b"hello", b"", b"world"])
    with patch(
        "code_puppy.plugins.agent_skills.downloader.httpx.Client", return_value=mc
    ):
        assert _download_to_file("http://example.com/a.zip", dest) is True
    assert dest.read_bytes() == b"helloworld"


def test_download_to_file_http_error(tmp_path):
    mc = _make_mock_client(status_error=True)
    with patch(
        "code_puppy.plugins.agent_skills.downloader.httpx.Client", return_value=mc
    ):
        assert _download_to_file("http://x", tmp_path / "o.zip") is False


def test_download_to_file_connect_error(tmp_path):
    mc = _make_mock_client(connect_error=True)
    with patch(
        "code_puppy.plugins.agent_skills.downloader.httpx.Client", return_value=mc
    ):
        assert _download_to_file("http://x", tmp_path / "o.zip") is False


def test_download_to_file_generic_error(tmp_path):
    mc = _make_mock_client(generic_error=True)
    with patch(
        "code_puppy.plugins.agent_skills.downloader.httpx.Client", return_value=mc
    ):
        assert _download_to_file("http://x", tmp_path / "o.zip") is False


# ── _validate_zip_safety ──


def _make_zip_bytes(entries: dict[str, bytes | None]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            if data is None:
                zf.writestr(zipfile.ZipInfo(name + "/"), "")
            else:
                zf.writestr(name, data)
    return buf.getvalue()


def test_validate_zip_safety_ok():
    data = _make_zip_bytes({"SKILL.md": b"hi", "lib.py": b"code"})
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert _validate_zip_safety(zf) is None


def test_validate_zip_safety_directory_entry():
    data = _make_zip_bytes({"subdir": None, "subdir/a.txt": b"x"})
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert _validate_zip_safety(zf) is None


def test_validate_zip_safety_absolute_path():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/etc/passwd", b"bad")
    with zipfile.ZipFile(BytesIO(buf.getvalue())) as zf:
        result = _validate_zip_safety(zf)
        assert result is not None and "absolute" in result


def test_validate_zip_safety_traversal():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../../etc/passwd", b"bad")
    with zipfile.ZipFile(BytesIO(buf.getvalue())) as zf:
        result = _validate_zip_safety(zf)
        assert result is not None and "traversal" in result


def test_validate_zip_safety_too_large():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("big.bin", b"x" * 100)
    with zipfile.ZipFile(BytesIO(buf.getvalue())) as zf:
        for info in zf.infolist():
            if not info.is_dir():
                info.file_size = 60 * 1024 * 1024
        result = _validate_zip_safety(zf)
        assert result is not None and "too large" in result


# ── _safe_extract_zip ──


def test_safe_extract_zip_ok(tmp_path):
    data = _make_zip_bytes({"SKILL.md": b"# Skill", "lib/code.py": b"pass"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert _safe_extract_zip(zf, extract_dir) is True
    assert (extract_dir / "SKILL.md").read_bytes() == b"# Skill"
    assert (extract_dir / "lib" / "code.py").exists()


def test_safe_extract_zip_skips_macosx(tmp_path):
    data = _make_zip_bytes({"__MACOSX/junk": b"x", "SKILL.md": b"ok"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert _safe_extract_zip(zf, extract_dir) is True
    assert not (extract_dir / "__MACOSX").exists()


def test_safe_extract_zip_directory_entry(tmp_path):
    data = _make_zip_bytes({"subdir": None, "subdir/a.txt": b"hi"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert _safe_extract_zip(zf, extract_dir) is True
    assert (extract_dir / "subdir" / "a.txt").exists()


def test_safe_extract_zip_outside_dir(tmp_path):
    data = _make_zip_bytes({"a.txt": b"ok"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        with patch(
            "code_puppy.plugins.agent_skills.downloader._is_within_directory",
            return_value=False,
        ):
            assert _safe_extract_zip(zf, extract_dir) is False


def test_safe_extract_zip_exception(tmp_path):
    data = _make_zip_bytes({"a.txt": b"ok"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        with patch(
            "code_puppy.plugins.agent_skills.downloader._is_within_directory",
            side_effect=RuntimeError,
        ):
            assert _safe_extract_zip(zf, extract_dir) is False


# ── _determine_extracted_root ──


def test_determine_extracted_root_at_root(tmp_path):
    (tmp_path / "SKILL.md").write_text("hi")
    assert _determine_extracted_root(tmp_path) == tmp_path


def test_determine_extracted_root_in_subdir(tmp_path):
    sub = tmp_path / "my-skill"
    sub.mkdir()
    (sub / "SKILL.md").write_text("hi")
    assert _determine_extracted_root(tmp_path) == sub


def test_determine_extracted_root_no_skill_md(tmp_path):
    (tmp_path / "README.md").write_text("hi")
    assert _determine_extracted_root(tmp_path) is None


def test_determine_extracted_root_files_but_no_skill_md(tmp_path):
    (tmp_path / "random.txt").write_text("x")
    assert _determine_extracted_root(tmp_path) is None


def test_determine_extracted_root_multiple_dirs(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _determine_extracted_root(tmp_path) is None


def test_determine_extracted_root_subdir_no_skill_md(tmp_path):
    sub = tmp_path / "only"
    sub.mkdir()
    (sub / "README.md").write_text("hi")
    assert _determine_extracted_root(tmp_path) is None


def test_determine_extracted_root_macosx_ignored(tmp_path):
    (tmp_path / "__MACOSX").mkdir()
    sub = tmp_path / "skill"
    sub.mkdir()
    (sub / "SKILL.md").write_text("hi")
    assert _determine_extracted_root(tmp_path) == sub


def test_determine_extracted_root_exception(tmp_path):
    with patch.object(Path, "is_file", side_effect=RuntimeError):
        assert _determine_extracted_root(tmp_path) is None


# ── _stage_normalized_install ──


def test_stage_normalized_install_ok(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("hi")
    staging = tmp_path / "staging"
    staging.mkdir()
    result = _stage_normalized_install(src, "myskill", staging)
    assert result == staging / "myskill"
    assert (result / "SKILL.md").read_text() == "hi"


def test_stage_normalized_install_existing_dest(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("new")
    staging = tmp_path / "staging"
    dest = staging / "myskill"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("old")
    result = _stage_normalized_install(src, "myskill", staging)
    assert result is not None
    assert (result / "SKILL.md").read_text() == "new"


def test_stage_normalized_install_missing_skill_md(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "README.md").write_text("hi")
    staging = tmp_path / "staging"
    staging.mkdir()
    assert _stage_normalized_install(src, "myskill", staging) is None


def test_stage_normalized_install_exception(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader.shutil.copytree",
        side_effect=OSError,
    ):
        src = tmp_path / "src"
        src.mkdir()
        staging = tmp_path / "staging"
        staging.mkdir()
        assert _stage_normalized_install(src, "myskill", staging) is None


# ── download_and_install_skill ──


def test_empty_skill_name():
    r = download_and_install_skill("", "http://x")
    assert not r.success and "required" in r.message


def test_whitespace_skill_name():
    r = download_and_install_skill("  ", "http://x")
    assert not r.success and "required" in r.message


def test_traversal_skill_name():
    r = download_and_install_skill("../evil", "http://x")
    assert not r.success and "simple directory" in r.message


def test_dot_skill_name():
    r = download_and_install_skill(".", "http://x")
    assert not r.success and "simple directory" in r.message


def test_dotdot_skill_name():
    r = download_and_install_skill("..", "http://x")
    assert not r.success and "simple directory" in r.message


def test_already_installed_no_force(tmp_path):
    skill_dir = tmp_path / "myskill"
    skill_dir.mkdir()
    r = download_and_install_skill(
        "myskill", "http://x", target_dir=tmp_path, force=False
    )
    assert not r.success and "already installed" in r.message


def test_force_reinstall_rmtree_fails(tmp_path):
    skill_dir = tmp_path / "myskill"
    skill_dir.mkdir()
    with patch(
        "code_puppy.plugins.agent_skills.downloader._safe_rmtree", return_value=False
    ):
        r = download_and_install_skill(
            "myskill", "http://x", target_dir=tmp_path, force=True
        )
    assert not r.success and "Failed to remove" in r.message


def test_download_failure(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=False,
    ):
        r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert not r.success and "download" in r.message.lower()


def test_bad_zip_file(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            side_effect=zipfile.BadZipFile,
        ):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert not r.success and "not a valid zip" in r.message


def test_zip_open_generic_exception(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            side_effect=RuntimeError("boom"),
        ):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert not r.success and "Failed to extract zip" in r.message


def test_unsafe_zip(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value="too big",
            ):
                r = download_and_install_skill(
                    "myskill", "http://x", target_dir=tmp_path
                )
    assert not r.success and "unsafe" in r.message.lower()


def test_extract_failure(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                    return_value=False,
                ):
                    r = download_and_install_skill(
                        "myskill", "http://x", target_dir=tmp_path
                    )
    assert not r.success and "extract" in r.message.lower()


def test_no_extracted_root(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                    return_value=True,
                ):
                    with patch(
                        "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                        return_value=None,
                    ):
                        r = download_and_install_skill(
                            "myskill", "http://x", target_dir=tmp_path
                        )
    assert not r.success and "SKILL.md" in r.message


def test_stage_failure(tmp_path):
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                    return_value=True,
                ):
                    with patch(
                        "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                        return_value=Path("/fake"),
                    ):
                        with patch(
                            "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                            return_value=None,
                        ):
                            r = download_and_install_skill(
                                "myskill", "http://x", target_dir=tmp_path
                            )
    assert not r.success and "stage" in r.message.lower()


def test_move_failure(tmp_path):
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "SKILL.md").write_text("hi")
    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                    return_value=True,
                ):
                    with patch(
                        "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                        return_value=Path("/fake"),
                    ):
                        with patch(
                            "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                            return_value=staged,
                        ):
                            with patch(
                                "code_puppy.plugins.agent_skills.downloader.shutil.move",
                                side_effect=OSError,
                            ):
                                r = download_and_install_skill(
                                    "myskill", "http://x", target_dir=tmp_path
                                )
    assert not r.success and "move" in r.message.lower()


def test_full_success(tmp_path):
    zip_data = _make_zip_bytes({"SKILL.md": b"# Test Skill", "lib.py": b"pass"})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_data)
        return True

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        side_effect=fake_download,
    ):
        with patch("code_puppy.plugins.agent_skills.downloader.refresh_skill_cache"):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert r.success
    assert (tmp_path / "myskill" / "SKILL.md").exists()


def test_full_success_cache_refresh_fails(tmp_path):
    zip_data = _make_zip_bytes({"SKILL.md": b"# Test"})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_data)
        return True

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        side_effect=fake_download,
    ):
        with patch(
            "code_puppy.plugins.agent_skills.downloader.refresh_skill_cache",
            side_effect=RuntimeError("oops"),
        ):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert r.success


def test_post_install_missing_skill_md(tmp_path):
    """After move, SKILL.md not present -> failure."""
    # Create a zip that has SKILL.md (passes staging) but after move we fake it missing
    zip_data = _make_zip_bytes({"SKILL.md": b"# Test"})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_data)
        return True

    # After shutil.move, delete the SKILL.md so the post-install check fails
    original_move = shutil.move

    def fake_move(src, dst):
        result = original_move(src, dst)
        # Remove SKILL.md from the final destination
        skill_md = Path(dst) / "SKILL.md"
        if skill_md.exists():
            skill_md.unlink()
        return result

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        side_effect=fake_download,
    ):
        with patch(
            "code_puppy.plugins.agent_skills.downloader.shutil.move",
            side_effect=fake_move,
        ):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert not r.success and "missing SKILL.md" in r.message


def test_skill_dir_exists_during_move_no_force(tmp_path):
    """Edge case: skill_dir appears during move phase without force."""
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "SKILL.md").write_text("hi")

    skill_dir = tmp_path / "myskill"

    exists_calls = [0]
    orig_exists = Path.exists

    def fake_exists(self):
        if self == skill_dir:
            exists_calls[0] += 1
            if exists_calls[0] <= 1:
                return False
            return True
        return orig_exists(self)

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        return_value=True,
    ):
        mock_zf = MagicMock()
        mock_zf.__enter__ = MagicMock(return_value=mock_zf)
        mock_zf.__exit__ = MagicMock(return_value=False)
        with patch(
            "code_puppy.plugins.agent_skills.downloader.zipfile.ZipFile",
            return_value=mock_zf,
        ):
            with patch(
                "code_puppy.plugins.agent_skills.downloader._validate_zip_safety",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.agent_skills.downloader._safe_extract_zip",
                    return_value=True,
                ):
                    with patch(
                        "code_puppy.plugins.agent_skills.downloader._determine_extracted_root",
                        return_value=Path("/fake"),
                    ):
                        with patch(
                            "code_puppy.plugins.agent_skills.downloader._stage_normalized_install",
                            return_value=staged,
                        ):
                            with patch.object(Path, "exists", fake_exists):
                                r = download_and_install_skill(
                                    "myskill",
                                    "http://x",
                                    target_dir=tmp_path,
                                    force=False,
                                )
    assert not r.success and "already exists" in r.message


def test_skill_dir_exists_during_move_force(tmp_path):
    zip_data = _make_zip_bytes({"SKILL.md": b"# hi"})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_data)
        (tmp_path / "myskill").mkdir(exist_ok=True)
        return True

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        side_effect=fake_download,
    ):
        with patch("code_puppy.plugins.agent_skills.downloader.refresh_skill_cache"):
            r = download_and_install_skill(
                "myskill", "http://x", target_dir=tmp_path, force=True
            )
    assert r.success


def test_outer_exception(tmp_path):
    with patch.object(Path, "exists", side_effect=RuntimeError("boom")):
        r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert not r.success and "Unexpected error" in r.message


def test_full_success_nested_zip(tmp_path):
    zip_data = _make_zip_bytes(
        {"myskill-main/SKILL.md": b"# Nested", "myskill-main/code.py": b"x=1"}
    )

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_data)
        return True

    with patch(
        "code_puppy.plugins.agent_skills.downloader._download_to_file",
        side_effect=fake_download,
    ):
        with patch("code_puppy.plugins.agent_skills.downloader.refresh_skill_cache"):
            r = download_and_install_skill("myskill", "http://x", target_dir=tmp_path)
    assert r.success
    assert (tmp_path / "myskill" / "SKILL.md").read_text() == "# Nested"
