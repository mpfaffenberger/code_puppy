"""Bundled skill installer.

Phase 1: "install" means copying a bundled skill from the shipped catalog into
the user's skills directory (default: ~/.code_puppy/skills).

We keep this implementation intentionally boring and safe:
- never overwrite unless `force=True`
- use `shutil.copytree(..., dirs_exist_ok=False)`
- refresh the discovery cache on successful install/uninstall
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from code_puppy.plugins.agent_skills.discovery import refresh_skill_cache
from code_puppy.plugins.agent_skills.skill_catalog import SkillCatalogEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InstallResult:
    success: bool
    skill_name: str
    install_path: Path
    error: Optional[str] = None
    was_update: bool = False


def get_default_install_dir() -> Path:
    """Default directory where user-installed skills live."""

    return Path.home() / ".code_puppy" / "skills"


def _resolve_target_dir(target_dir: Optional[Path]) -> Path:
    return target_dir if target_dir is not None else get_default_install_dir()


def is_skill_installed(skill_id: str, target_dir: Optional[Path] = None) -> bool:
    """Check if a skill is installed by verifying `<dir>/<skill_id>/SKILL.md` exists."""

    base = _resolve_target_dir(target_dir)
    skill_md = base / skill_id / "SKILL.md"
    return skill_md.is_file()


def install_skill(
    catalog_entry: SkillCatalogEntry,
    target_dir: Optional[Path] = None,
    force: bool = False,
) -> InstallResult:
    """Install a bundled skill into the user skills directory.

    Args:
        catalog_entry: The bundled skill catalog entry.
        target_dir: Optional override install root.
        force: If True, overwrite an existing install.

    Returns:
        InstallResult describing success/failure.
    """

    base = _resolve_target_dir(target_dir)
    install_path = base / catalog_entry.id

    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = f"Failed to create skills directory at {base}: {e}"
        logger.error(msg)
        return InstallResult(
            success=False,
            skill_name=catalog_entry.name,
            install_path=install_path,
            error=msg,
            was_update=False,
        )

    was_update = install_path.exists()
    if was_update and not force:
        msg = (
            f"Skill '{catalog_entry.id}' already installed at {install_path}. "
            "Use force=True to overwrite."
        )
        logger.info(msg)
        return InstallResult(
            success=False,
            skill_name=catalog_entry.name,
            install_path=install_path,
            error=msg,
            was_update=False,
        )

    if was_update and force:
        try:
            shutil.rmtree(install_path)
        except OSError as e:
            msg = f"Failed to remove existing skill at {install_path}: {e}"
            logger.error(msg)
            return InstallResult(
                success=False,
                skill_name=catalog_entry.name,
                install_path=install_path,
                error=msg,
                was_update=True,
            )

    try:
        shutil.copytree(
            src=catalog_entry.source_path,
            dst=install_path,
            dirs_exist_ok=False,
        )
    except FileExistsError:
        # Shouldn't happen because we guard + dirs_exist_ok=False, but be explicit.
        msg = (
            f"Refusing to overwrite existing skill directory at {install_path}. "
            "Use force=True to overwrite."
        )
        logger.info(msg)
        return InstallResult(
            success=False,
            skill_name=catalog_entry.name,
            install_path=install_path,
            error=msg,
            was_update=False,
        )
    except OSError as e:
        msg = f"Failed to copy skill from {catalog_entry.source_path} to {install_path}: {e}"
        logger.error(msg)
        return InstallResult(
            success=False,
            skill_name=catalog_entry.name,
            install_path=install_path,
            error=msg,
            was_update=was_update,
        )

    # Only refresh cache after success.
    try:
        refresh_skill_cache()
    except Exception as e:  # pragma: no cover - refresh should be best-effort
        logger.warning(f"Skill installed but failed to refresh cache: {e}")

    return InstallResult(
        success=True,
        skill_name=catalog_entry.name,
        install_path=install_path,
        error=None,
        was_update=was_update,
    )


def uninstall_skill(skill_id: str, target_dir: Optional[Path] = None) -> InstallResult:
    """Uninstall a previously installed skill."""

    base = _resolve_target_dir(target_dir)
    install_path = base / skill_id

    if not install_path.exists():
        msg = f"Skill '{skill_id}' is not installed (missing {install_path})."
        logger.info(msg)
        return InstallResult(
            success=False,
            skill_name=skill_id,
            install_path=install_path,
            error=msg,
            was_update=False,
        )

    try:
        shutil.rmtree(install_path)
    except OSError as e:
        msg = f"Failed to uninstall skill '{skill_id}' at {install_path}: {e}"
        logger.error(msg)
        return InstallResult(
            success=False,
            skill_name=skill_id,
            install_path=install_path,
            error=msg,
            was_update=False,
        )

    try:
        refresh_skill_cache()
    except Exception as e:  # pragma: no cover
        logger.warning(f"Skill uninstalled but failed to refresh cache: {e}")

    return InstallResult(
        success=True,
        skill_name=skill_id,
        install_path=install_path,
        error=None,
        was_update=False,
    )
