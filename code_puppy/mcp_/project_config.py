"""Project-level MCP server configuration discovery + trust gating.

Code Puppy loads MCP server definitions from the user-level
``$XDG_CONFIG_HOME/code_puppy/mcp_servers.json``. This module adds an
*optional*, **trust-gated** project-level source at
``<CWD>/.code_puppy/mcp_servers.json`` so a team can version-control the MCP
servers their repo needs — mirroring the existing project-level discovery for
agents, skills, and plugins.

Why a trust gate?  A ``stdio`` MCP server runs an arbitrary command, and a
project can also ship an agent (``.code_puppy/agents/*.json``) that declares an
``auto_start`` binding to one of these servers. That combination is a
code-execution vector the moment you open a freshly cloned repo. So, exactly
like project *plugins* (see :mod:`code_puppy.plugins.trust`), project MCP
configs are **disabled until the user explicitly trusts them** via
``/mcp trust``.

Trust model (identical philosophy to ``code_puppy/plugins/trust.py``):

* Trust store lives **user-side** at ``~/.code_puppy/trusted_mcp.json`` — a repo
  can never self-trust.
* Trust is **content-addressed**: a SHA-256 of the project config file, scoped
  to the resolved project path. Any edit to the file reverts it to "changed"
  and demands re-acceptance (blocks silent-update attacks, same as direnv's
  ``allow``).
* **Fail closed**: an unreadable store, malformed JSON, or an unhashable file
  all resolve to "not trusted" → the project config is silently ignored.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Trust store lives user-side so a repository can never self-trust. We hardcode
# ``~/.code_puppy`` to match ``plugins/trust.py`` — the whole trust subsystem is
# deliberately anchored to the legacy home dir, not the XDG config dir.
TRUST_STORE_FILE = Path.home() / ".code_puppy" / "trusted_mcp.json"

# Project-local MCP config path, relative to the current working directory.
PROJECT_MCP_RELPATH = Path(".code_puppy") / "mcp_servers.json"

_STORE_VERSION = 1

# Trust statuses (mirrors plugins.trust for a consistent mental model).
TRUSTED = "trusted"  # entry exists and hash matches current contents
CHANGED = "changed"  # entry exists but contents differ since acceptance
UNTRUSTED = "untrusted"  # no entry — user never accepted this config

# Warn-once-per-session dedupe so a long-running session doesn't spam the same
# "found an untrusted project MCP config" message on every registry sync.
_WARNED: set[tuple[str, str]] = set()


# ---------- discovery --------------------------------------------------------


def get_project_mcp_servers_file(project_root: Optional[Path] = None) -> Optional[Path]:
    """Return the project-local MCP config path if it exists, else ``None``.

    Like :func:`code_puppy.config.get_project_agents_directory`, this never
    creates anything — the team opts in by committing the file.
    """
    root = Path(project_root) if project_root is not None else Path.cwd()
    candidate = root / PROJECT_MCP_RELPATH
    try:
        if candidate.is_file():
            return candidate
    except OSError:  # pragma: no cover - exotic filesystem errors
        return None
    return None


# ---------- content hashing --------------------------------------------------


def compute_mcp_file_hash(config_file: Path) -> Optional[str]:
    """SHA-256 of the config file's bytes, or ``None`` if unreadable.

    Callers must treat ``None`` as *not trusted* (fail closed).
    """
    try:
        return hashlib.sha256(Path(config_file).read_bytes()).hexdigest()
    except OSError as exc:
        logger.warning("Could not hash project MCP config %s: %s", config_file, exc)
        return None


# ---------- trust store I/O --------------------------------------------------


def _project_key(project_root: Path) -> str:
    """Canonical store key for a project root (resolved absolute path)."""
    return str(Path(project_root).resolve())


def _load_store() -> dict:
    """Read the trust store, returning an empty store on any problem."""
    try:
        if TRUST_STORE_FILE.is_file():
            data = json.loads(TRUST_STORE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("projects"), dict):
                return data
            logger.warning(
                "Malformed MCP trust store at %s — treating as empty",
                TRUST_STORE_FILE,
            )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Could not read MCP trust store %s: %s", TRUST_STORE_FILE, exc)
    return {"version": _STORE_VERSION, "projects": {}}


def _save_store(store: dict) -> bool:
    """Persist the trust store. Returns ``False`` (and logs) on failure."""
    try:
        TRUST_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRUST_STORE_FILE.write_text(
            json.dumps(store, indent=2, sort_keys=True), encoding="utf-8"
        )
        return True
    except OSError as exc:
        logger.error("Could not write MCP trust store %s: %s", TRUST_STORE_FILE, exc)
        return False


# ---------- trust queries / mutations ----------------------------------------


def get_trust_status(project_root: Path, config_file: Path) -> str:
    """Return :data:`TRUSTED`, :data:`CHANGED`, or :data:`UNTRUSTED`."""
    store = _load_store()
    entry = store["projects"].get(_project_key(project_root))
    if not isinstance(entry, dict) or not entry.get("hash"):
        return UNTRUSTED
    current = compute_mcp_file_hash(config_file)
    if current is not None and current == entry["hash"]:
        return TRUSTED
    return CHANGED


def is_project_mcp_trusted(project_root: Optional[Path] = None) -> bool:
    """True only when the current project's MCP config is trusted & unchanged."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    config_file = get_project_mcp_servers_file(root)
    if config_file is None:
        return False
    return get_trust_status(root, config_file) == TRUSTED


def trust_project_mcp(project_root: Optional[Path] = None) -> bool:
    """Record acceptance of the current project's MCP config at its hash.

    Returns ``False`` if there's no project config or it can't be hashed.
    """
    root = Path(project_root) if project_root is not None else Path.cwd()
    config_file = get_project_mcp_servers_file(root)
    if config_file is None:
        return False
    config_hash = compute_mcp_file_hash(config_file)
    if config_hash is None:
        return False
    store = _load_store()
    store["projects"][_project_key(root)] = {
        "hash": config_hash,
        "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return _save_store(store)


def revoke_project_mcp(project_root: Optional[Path] = None) -> bool:
    """Remove trust for the current project. Returns True if an entry existed."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    store = _load_store()
    key = _project_key(root)
    if key not in store["projects"]:
        return False
    del store["projects"][key]
    return _save_store(store)


# ---------- config loading ---------------------------------------------------


def load_project_mcp_server_configs(
    project_root: Optional[Path] = None,
) -> Dict[str, dict]:
    """Return the project's MCP server mapping, or ``{}`` when not usable.

    Returns ``{}`` (and, for the untrusted/changed cases, emits a one-time
    warning) when:

    * there's no ``<CWD>/.code_puppy/mcp_servers.json``, or
    * the user hasn't trusted it (or its contents changed since acceptance), or
    * the file is malformed.

    This function never raises — a broken project file must not be able to
    break user-level MCP loading.
    """
    root = Path(project_root) if project_root is not None else Path.cwd()
    config_file = get_project_mcp_servers_file(root)
    if config_file is None:
        return {}

    status = get_trust_status(root, config_file)
    if status != TRUSTED:
        _warn_untrusted(root, config_file, status)
        return {}

    # Trusted: parse via the same chokepoint the user-level loader uses.
    try:
        from code_puppy.config import _parse_mcp_servers_mapping

        return _parse_mcp_servers_mapping(config_file.read_text(encoding="utf-8"))
    except Exception as exc:
        from code_puppy.messaging.message_queue import emit_error

        emit_error(f"Failed to load project MCP servers from {config_file}: {exc}")
        return {}


def _warn_untrusted(project_root: Path, config_file: Path, status: str) -> None:
    """Emit a one-time, actionable warning about an unloaded project config."""
    key = (_project_key(project_root), status)
    if key in _WARNED:
        return
    _WARNED.add(key)

    try:
        from code_puppy.messaging.message_queue import emit_warning
    except Exception:  # pragma: no cover - defensive
        return

    if status == CHANGED:
        reason = "has changed since you trusted it"
    else:
        reason = "is not trusted yet"
    emit_warning(
        f"Project MCP config '{config_file}' {reason}; its servers are "
        f"NOT loaded. Review it, then run '/mcp trust' to accept "
        f"(project MCP servers can run arbitrary commands)."
    )


def _reset_warning_cache() -> None:
    """Clear the warn-once cache. Test hook only."""
    _WARNED.clear()
