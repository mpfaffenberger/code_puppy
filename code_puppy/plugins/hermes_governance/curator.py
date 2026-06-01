"""Skill curator — lifecycle consolidation, ported from Hermes' curator.

Walks agent-created skills and transitions them through
``active -> stale -> archived`` based on how long since they were last used.
Last-use timestamps come from the budget carrier's ``skill_usage`` map (updated
on every ``activate_skill`` / ``skill_manage``), falling back to the skill
file's mtime.

Strict invariants (matching Hermes):
  * Never deletes — only moves to ``~/.code_puppy/skills/.archived/`` (recoverable).
  * Only touches skills authored by ``code-puppy`` (agent-created). User skills
    are never auto-managed.
  * Pinned skills (``metadata.pinned: true`` in frontmatter, or listed in the
    ``hermes_governance_pinned_skills`` config) bypass all transitions.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy.config import get_value

from .budget import snapshot

logger = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_DAYS = 14
DEFAULT_ARCHIVE_AFTER_DAYS = 45
_AGENT_AUTHOR = "code-puppy"


def _user_skills_root() -> Path:
    return Path.home() / ".code_puppy" / "skills"


def get_stale_after_days() -> int:
    raw = get_value("hermes_governance_stale_after_days")
    try:
        return int(raw) if raw else DEFAULT_STALE_AFTER_DAYS
    except (TypeError, ValueError):
        return DEFAULT_STALE_AFTER_DAYS


def get_archive_after_days() -> int:
    raw = get_value("hermes_governance_archive_after_days")
    try:
        return int(raw) if raw else DEFAULT_ARCHIVE_AFTER_DAYS
    except (TypeError, ValueError):
        return DEFAULT_ARCHIVE_AFTER_DAYS


def _pinned_from_config() -> set[str]:
    raw = get_value("hermes_governance_pinned_skills")
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x) for x in data}
    except json.JSONDecodeError:
        pass
    return {p.strip() for p in str(raw).split(",") if p.strip()}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _read_frontmatter(skill_md: Path) -> Dict[str, Any]:
    try:
        from code_puppy.plugins.agent_skills.metadata import parse_yaml_frontmatter

        return parse_yaml_frontmatter(skill_md.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _is_agent_created(fm: Dict[str, Any]) -> bool:
    return str(fm.get("author", "")).strip().lower() == _AGENT_AUTHOR


def _is_pinned(name: str, fm: Dict[str, Any], pinned_cfg: set[str]) -> bool:
    if name in pinned_cfg:
        return True
    val = fm.get("pinned")
    return (
        str(val).strip().lower() in ("1", "true", "yes") if val is not None else False
    )


def _last_activity(name: str, skill_md: Path, usage: Dict[str, str]) -> datetime:
    dt = _parse_iso(usage.get(name))
    if dt is not None:
        return dt
    try:
        return datetime.fromtimestamp(skill_md.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.now(timezone.utc)


def apply_automatic_transitions(now: Optional[datetime] = None) -> Dict[str, int]:
    """Walk agent-created skills and archive/mark-stale by inactivity.

    Returns a counter dict: ``{"checked", "marked_stale", "archived", "skipped"}``.
    Stale state is recorded as ``metadata.lifecycle: stale`` in the carrier-backed
    usage map is not modified here; staleness is advisory (surfaced in /skills).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    from datetime import timedelta

    stale_cut = now - timedelta(days=get_stale_after_days())
    archive_cut = now - timedelta(days=get_archive_after_days())

    usage = snapshot().get("skill_usage", {}) or {}
    pinned_cfg = _pinned_from_config()
    counts = {"checked": 0, "marked_stale": 0, "archived": 0, "skipped": 0}

    root = _user_skills_root()
    if not root.is_dir():
        return counts

    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        fm = _read_frontmatter(skill_md)
        name = str(fm.get("name") or skill_dir.name)

        if not _is_agent_created(fm):
            counts["skipped"] += 1
            continue
        if _is_pinned(name, fm, pinned_cfg):
            counts["skipped"] += 1
            continue

        counts["checked"] += 1
        anchor = _last_activity(name, skill_md, usage)

        if anchor <= archive_cut:
            if _archive_skill(skill_dir):
                counts["archived"] += 1
        elif anchor <= stale_cut:
            counts["marked_stale"] += 1

    return counts


def _archive_skill(skill_dir: Path) -> bool:
    """Move a skill directory to the recoverable archive. Never deletes."""
    try:
        archive_root = _user_skills_root() / ".archived"
        archive_root.mkdir(parents=True, exist_ok=True)
        target = archive_root / skill_dir.name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(skill_dir), str(target))
        return True
    except Exception:
        logger.debug("curator: failed to archive %s", skill_dir, exc_info=True)
        return False


def stale_skill_report(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """List agent-created skills with their inactivity status (no mutation)."""
    if now is None:
        now = datetime.now(timezone.utc)
    from datetime import timedelta

    stale_cut = now - timedelta(days=get_stale_after_days())
    usage = snapshot().get("skill_usage", {}) or {}
    pinned_cfg = _pinned_from_config()
    out: List[Dict[str, Any]] = []

    root = _user_skills_root()
    if not root.is_dir():
        return out

    for skill_dir in sorted(root.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.is_file():
            continue
        fm = _read_frontmatter(skill_md)
        name = str(fm.get("name") or skill_dir.name)
        if not _is_agent_created(fm):
            continue
        anchor = _last_activity(name, skill_md, usage)
        out.append(
            {
                "name": name,
                "pinned": _is_pinned(name, fm, pinned_cfg),
                "last_activity": anchor.isoformat(),
                "stale": anchor <= stale_cut,
            }
        )
    return out
