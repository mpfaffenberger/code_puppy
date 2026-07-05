"""Content-hash trust store for project-level plugins.

Project plugins (``<CWD>/.code_puppy/plugins/``) execute arbitrary code at
import time, so they are **disabled by default**.  A plugin only loads after
the user explicitly accepts the risk in the ``/plugins`` TUI ceremony, which
records a SHA-256 hash of the plugin's contents here.

Key properties:

* **Store lives user-side** (``~/.code_puppy/trusted_plugins.json``) — never
  in the repo, so a repository can never self-trust.
* **Trust is per-plugin and content-addressed.**  If any file in the plugin
  directory changes, the hash no longer matches and the plugin reverts to
  requiring re-acceptance ("changed" status).  This blocks silent-update
  attacks against previously trusted plugins (same model as direnv's
  ``allow`` mechanism).
* **Fail closed.**  Unreadable store, malformed JSON, or unhashable plugin
  directories all resolve to "not trusted".
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

TRUST_STORE_FILE = Path.home() / ".code_puppy" / "trusted_plugins.json"

_STORE_VERSION = 1

# Trust statuses
TRUSTED = "trusted"  # entry exists and hash matches current contents
CHANGED = "changed"  # entry exists but contents differ since acceptance
UNTRUSTED = "untrusted"  # no entry — user never accepted this plugin


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
                "Malformed trust store at %s — treating as empty", TRUST_STORE_FILE
            )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Could not read trust store %s: %s", TRUST_STORE_FILE, exc)
    return {"version": _STORE_VERSION, "projects": {}}


def _save_store(store: dict) -> bool:
    """Persist the trust store. Returns False (and logs) on failure."""
    try:
        TRUST_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRUST_STORE_FILE.write_text(
            json.dumps(store, indent=2, sort_keys=True), encoding="utf-8"
        )
        return True
    except OSError as exc:
        logger.error("Could not write trust store %s: %s", TRUST_STORE_FILE, exc)
        return False


def compute_plugin_hash(plugin_dir: Path) -> str | None:
    """SHA-256 over every file in *plugin_dir* (recursive, deterministic).

    Includes relative paths in the digest so renames count as changes.
    Skips ``__pycache__``, hidden path components, and ``.pyc`` artifacts.
    Returns ``None`` if the directory cannot be read (callers must treat
    that as not-trusted).
    """
    plugin_dir = Path(plugin_dir)
    digest = hashlib.sha256()
    try:
        files = sorted(
            p
            for p in plugin_dir.rglob("*")
            if p.is_file()
            and p.suffix != ".pyc"
            and "__pycache__" not in p.relative_to(plugin_dir).parts
            and not any(
                part.startswith(".") for part in p.relative_to(plugin_dir).parts
            )
        )
        for path in files:
            digest.update(path.relative_to(plugin_dir).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    except OSError as exc:
        logger.warning("Could not hash plugin dir %s: %s", plugin_dir, exc)
        return None
    return digest.hexdigest()


def get_trust_status(project_root: Path, plugin_name: str, plugin_dir: Path) -> str:
    """Return TRUSTED, CHANGED, or UNTRUSTED for a project plugin."""
    store = _load_store()
    entry = store["projects"].get(_project_key(project_root), {}).get(plugin_name)
    if not isinstance(entry, dict) or not entry.get("hash"):
        return UNTRUSTED
    current = compute_plugin_hash(plugin_dir)
    if current is not None and current == entry["hash"]:
        return TRUSTED
    return CHANGED


def is_plugin_trusted(project_root: Path, plugin_name: str, plugin_dir: Path) -> bool:
    """True only when a stored hash exists AND matches current contents."""
    return get_trust_status(project_root, plugin_name, plugin_dir) == TRUSTED


def trust_plugin(project_root: Path, plugin_name: str, plugin_dir: Path) -> bool:
    """Record acceptance of *plugin_name* at its current content hash."""
    plugin_hash = compute_plugin_hash(plugin_dir)
    if plugin_hash is None:
        return False
    store = _load_store()
    store["projects"].setdefault(_project_key(project_root), {})[plugin_name] = {
        "hash": plugin_hash,
        "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return _save_store(store)


def revoke_plugin(project_root: Path, plugin_name: str) -> bool:
    """Remove trust for *plugin_name*. Returns True if an entry was removed."""
    store = _load_store()
    key = _project_key(project_root)
    project_entries = store["projects"].get(key)
    if not project_entries or plugin_name not in project_entries:
        return False
    del project_entries[plugin_name]
    if not project_entries:
        del store["projects"][key]
    return _save_store(store)
