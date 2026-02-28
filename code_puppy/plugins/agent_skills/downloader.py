"""Remote skill downloader/installer.

Downloads a remote skill ZIP and installs it into the local skills directory.

Security notes:
- Defends against zip-slip path traversal.
- Defends (somewhat) against zip bombs by capping total uncompressed size.

This module never raises to callers; failures are returned as InstallResult.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from code_puppy.plugins.agent_skills.discovery import refresh_skill_cache
from code_puppy.plugins.agent_skills.installer import InstallResult

logger = logging.getLogger(__name__)

_DEFAULT_SKILLS_DIR = Path.home() / ".code_puppy" / "skills"
_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50MB


def _zip_entry_parts(name: str) -> list[str]:
    """Return safe-ish path parts for a zip entry.

    Zip files use POSIX-style separators, but malicious zips sometimes include
    backslashes. We normalize to '/' then split.
    """

    normalized = name.replace("\\", "/")
    return [part for part in normalized.split("/") if part not in {"", "."}]


def _safe_rmtree(path: Path) -> bool:
    """Remove a directory tree, logging errors instead of raising."""

    try:
        if not path.exists():
            return True
        shutil.rmtree(path)
        return True
    except Exception as e:
        logger.warning(f"Failed to remove directory {path}: {e}")
        return False


def _download_to_file(url: str, dest: Path) -> bool:
    """Download a URL to a local file path with streaming."""

    headers = {
        "Accept": "application/zip, application/octet-stream, */*",
        "User-Agent": "code-puppy/skill-downloader",
    }

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()

                with dest.open("wb") as f:
                    for chunk in response.iter_bytes():
                        if chunk:
                            f.write(chunk)

        logger.info(f"Downloaded skill zip to {dest}")
        return True

    except httpx.HTTPStatusError as e:
        logger.warning(
            "Skill download failed with HTTP status: "
            f"{e.response.status_code} {e.response.reason_phrase}"
        )
        return False
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(f"Skill download network failure: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error downloading {url}: {e}")
        return False


def _is_within_directory(base_dir: Path, candidate: Path) -> bool:
    """Check that a path is safely contained within a directory."""

    try:
        base_resolved = base_dir.resolve()
        candidate_resolved = candidate.resolve()
        candidate_resolved.relative_to(base_resolved)
        return True
    except Exception:
        return False


def _validate_zip_safety(zf: zipfile.ZipFile) -> Optional[str]:
    """Return an error message if unsafe, otherwise None."""

    total_uncompressed = 0

    for info in zf.infolist():
        # Directory entries are fine.
        if info.is_dir():
            continue

        total_uncompressed += int(info.file_size or 0)
        if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
            return (
                "ZIP appears too large when uncompressed "
                f"(>{_MAX_UNCOMPRESSED_BYTES} bytes)"
            )

        # Basic zip-slip protection: reject absolute paths and parent traversals.
        name = info.filename
        normalized = name.replace("\\", "/")
        if normalized.startswith("/"):
            return f"Unsafe zip entry path (absolute): {name}"

        parts = _zip_entry_parts(name)
        if ".." in parts:
            return f"Unsafe zip entry path (traversal): {name}"

    return None


def _safe_extract_zip(zf: zipfile.ZipFile, extract_dir: Path) -> bool:
    """Safely extract zip contents into extract_dir."""

    try:
        extract_dir.mkdir(parents=True, exist_ok=True)

        for info in zf.infolist():
            parts = _zip_entry_parts(info.filename)

            # Skip weird metadata folders.
            if parts and parts[0] == "__MACOSX":
                continue

            dest_path = extract_dir.joinpath(*parts)

            if not _is_within_directory(extract_dir, dest_path):
                logger.warning(
                    f"Blocked zip entry outside extraction dir: {info.filename}"
                )
                return False

            if info.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with zf.open(info, "r") as src, dest_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)

        return True

    except Exception as e:
        logger.exception(f"Failed to extract zip safely: {e}")
        return False


def _determine_extracted_root(extract_dir: Path) -> Optional[Path]:
    """Determine where the skill files live inside an extracted zip.

    Supports:
    - Files at the zip root
    - Files inside a single top-level folder

    Returns:
        Path to the directory containing SKILL.md, or None.
    """

    try:
        if (extract_dir / "SKILL.md").is_file():
            return extract_dir

        children = [p for p in extract_dir.iterdir() if p.name != "__MACOSX"]
        dirs = [p for p in children if p.is_dir()]
        files = [p for p in children if p.is_file()]

        # If it's root-level but SKILL.md missing, no good.
        if files:
            return None

        if len(dirs) == 1:
            candidate = dirs[0]
            if (candidate / "SKILL.md").is_file():
                return candidate

        return None

    except Exception as e:
        logger.warning(f"Failed to inspect extracted zip directory {extract_dir}: {e}")
        return None


def _stage_normalized_install(
    extracted_root: Path, skill_name: str, staging_base: Path
) -> Optional[Path]:
    """Copy extracted content into staging_base/<skill_name>."""

    try:
        staged_skill_dir = staging_base / skill_name
        if staged_skill_dir.exists():
            _safe_rmtree(staged_skill_dir)

        shutil.copytree(extracted_root, staged_skill_dir)

        if not (staged_skill_dir / "SKILL.md").is_file():
            logger.warning(
                f"Staged skill is missing SKILL.md: {(staged_skill_dir / 'SKILL.md')}"
            )
            return None

        return staged_skill_dir

    except Exception as e:
        logger.exception(f"Failed to stage normalized install for {skill_name}: {e}")
        return None


def download_and_install_skill(
    skill_name: str,
    download_url: str,
    target_dir: Optional[Path] = None,
    force: bool = False,
) -> InstallResult:
    """Download and install a remote skill zip.

    Args:
        skill_name: Skill name (directory name under target_dir).
        download_url: Absolute URL to the skill .zip.
        target_dir: Base skills directory. Defaults to ~/.code_puppy/skills.
        force: If True, delete any existing install first.

    Returns:
        InstallResult indicating success/failure.
    """

    skill_name = skill_name.strip()
    if not skill_name:
        return InstallResult(success=False, message="skill_name is required")

    # Prevent path traversal via skill_name.
    if Path(skill_name).name != skill_name or skill_name in {".", ".."}:
        return InstallResult(
            success=False, message="skill_name must be a simple directory name"
        )

    base_dir = target_dir or _DEFAULT_SKILLS_DIR
    skill_dir = base_dir / skill_name

    try:
        if skill_dir.exists():
            if not force:
                return InstallResult(
                    success=False,
                    message=f"Skill already installed at {skill_dir} (use force=True to reinstall)",
                    installed_path=skill_dir,
                )

            logger.info(
                f"Force reinstall enabled; removing existing skill at {skill_dir}"
            )
            if not _safe_rmtree(skill_dir):
                return InstallResult(
                    success=False,
                    message=f"Failed to remove existing skill directory: {skill_dir}",
                    installed_path=skill_dir,
                )

        base_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="code_puppy_skill_") as tmp:
            tmp_dir = Path(tmp)
            tmp_zip = tmp_dir / f"{skill_name}.zip"
            extract_dir = tmp_dir / "extracted"
            staging_dir = tmp_dir / "staging"
            staging_dir.mkdir(parents=True, exist_ok=True)

            if not _download_to_file(download_url, tmp_zip):
                return InstallResult(
                    success=False,
                    message=f"Failed to download skill zip from {download_url}",
                )

            try:
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    unsafe_reason = _validate_zip_safety(zf)
                    if unsafe_reason:
                        logger.warning(
                            f"Rejected unsafe zip for {skill_name}: {unsafe_reason}"
                        )
                        return InstallResult(
                            success=False,
                            message=f"Rejected unsafe zip: {unsafe_reason}",
                        )

                    if not _safe_extract_zip(zf, extract_dir):
                        return InstallResult(
                            success=False,
                            message="Failed to extract skill zip safely",
                        )
            except zipfile.BadZipFile:
                logger.warning(f"Downloaded file is not a valid zip: {tmp_zip}")
                return InstallResult(
                    success=False, message="Downloaded file is not a valid zip"
                )
            except Exception as e:
                logger.exception(f"Failed to open/extract zip for {skill_name}: {e}")
                return InstallResult(success=False, message="Failed to extract zip")

            extracted_root = _determine_extracted_root(extract_dir)
            if extracted_root is None:
                logger.warning(
                    "Extracted zip layout not recognized or missing SKILL.md. "
                    f"extract_dir={extract_dir}"
                )
                return InstallResult(
                    success=False,
                    message="Extracted zip missing SKILL.md or has unexpected layout",
                )

            staged_skill_dir = _stage_normalized_install(
                extracted_root=extracted_root,
                skill_name=skill_name,
                staging_base=staging_dir,
            )
            if staged_skill_dir is None:
                return InstallResult(
                    success=False,
                    message="Failed to stage extracted skill (missing SKILL.md)",
                )

            # Move staged install into final destination.
            try:
                if skill_dir.exists():
                    # Shouldn't happen (handled earlier), but be safe.
                    if force:
                        _safe_rmtree(skill_dir)
                    else:
                        return InstallResult(
                            success=False,
                            message=f"Skill directory already exists: {skill_dir}",
                            installed_path=skill_dir,
                        )

                shutil.move(str(staged_skill_dir), str(skill_dir))
            except Exception as e:
                logger.exception(f"Failed to install skill into {skill_dir}: {e}")
                # Cleanup partial install.
                _safe_rmtree(skill_dir)
                return InstallResult(
                    success=False, message="Failed to move skill into place"
                )

        # Post-install verification.
        if not (skill_dir / "SKILL.md").is_file():
            logger.warning(f"Installed skill missing SKILL.md: {skill_dir}")
            _safe_rmtree(skill_dir)
            return InstallResult(
                success=False,
                message="Installed skill is missing SKILL.md",
                installed_path=skill_dir,
            )

        try:
            refresh_skill_cache()
        except Exception as e:
            # Cache refresh failure should not poison a successful install.
            logger.warning(f"Skill installed but failed to refresh skill cache: {e}")

        logger.info(f"Installed skill '{skill_name}' into {skill_dir}")
        return InstallResult(
            success=True,
            message=f"Installed skill '{skill_name}'",
            installed_path=skill_dir,
        )

    except Exception as e:
        logger.exception(f"Unexpected error installing skill {skill_name}: {e}")
        return InstallResult(success=False, message="Unexpected error installing skill")
