"""Plugin loading with trust model for user plugins.

Built-in plugins (under code_puppy/plugins/) load unconditionally.
User plugins (under ~/.code_puppy/plugins/) require explicit trust
recorded in a manifest keyed by content hash; fail closed by default.
No sys.path insertion — user plugins are loaded via importlib with
unique module names to prevent stdlib/project shadowing.
"""

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

from code_puppy.secret_storage import atomic_write_private_json, ensure_private_dir

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".code_puppy" / "plugins"

# Track if plugins have already been loaded to prevent duplicate registration
_PLUGINS_LOADED = False

# ---------------------------------------------------------------------------
# Trust manifest helpers
# ---------------------------------------------------------------------------

# Env var / monkeypatch-friendly override for trust manifest path.
# Set CODE_PUPPY_PLUGIN_TRUST_MANIFEST to a file path to redirect the DB.
_TRUST_MANIFEST_ENV = "CODE_PUPPY_PLUGIN_TRUST_MANIFEST"

# Safe plugin name pattern: only alphanumeric + underscore + hyphen
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Max SKILL.md content size (bytes) before we refuse to read
_MAX_SKILL_MD_BYTES = 256 * 1024  # 256 KiB

# Cap for skill content injected into model context (chars)
_SKILL_CONTEXT_CAP = 64_000  # ~64k chars


def _default_trust_manifest_path() -> Path:
    """Return default path for the plugin trust manifest."""
    return Path.home() / ".code_puppy" / "plugin_trust.json"


def get_trust_manifest_path() -> Path:
    """Return the trust manifest path (env-override aware)."""
    env_val = os.environ.get(_TRUST_MANIFEST_ENV)
    if env_val:
        return Path(env_val)
    return _default_trust_manifest_path()


def _load_trust_manifest() -> dict:
    """Load the trust manifest from disk. Returns {} on any error."""
    path = get_trust_manifest_path()
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read plugin trust manifest at %s: %s", path, exc)
    return {}


def _save_trust_manifest(manifest: dict) -> None:
    """Persist the trust manifest to disk atomically with private perms."""
    path = get_trust_manifest_path()
    try:
        ensure_private_dir(path.parent)
        atomic_write_private_json(path, manifest)
    except OSError as exc:
        logger.warning("Failed to save plugin trust manifest: %s", exc)


def compute_plugin_hash(plugin_dir: Path) -> str:
    """Compute a SHA-256 hash over all .py files in a plugin directory.

    Hashes register_callbacks.py, __init__.py, and every other .py file
    found recursively under *plugin_dir*. Files are sorted by relative
    path for deterministic ordering. The hash covers file *contents*, not
    just file names.

    Returns the hex digest string.
    """
    h = hashlib.sha256()
    py_files: list[Path] = []
    try:
        for child in sorted(plugin_dir.rglob("*.py")):
            # Skip hidden files / dirs
            if any(
                part.startswith(".") for part in child.relative_to(plugin_dir).parts
            ):
                continue
            # Skip symlink escapes
            try:
                child.resolve().relative_to(plugin_dir.resolve())
            except ValueError:
                continue
            py_files.append(child)
    except OSError:
        pass

    for fpath in sorted(py_files):
        rel = fpath.relative_to(plugin_dir)
        h.update(str(rel).encode())
        h.update(b"\0")
        try:
            h.update(fpath.read_bytes())
        except OSError:
            pass
        h.update(b"\0")

    return h.hexdigest()


def is_plugin_trusted(plugin_name: str, content_hash: str) -> bool:
    """Check if a user plugin is trusted (manifest contains matching hash)."""
    manifest = _load_trust_manifest()
    entry = manifest.get(plugin_name)
    if not isinstance(entry, dict):
        return False
    return entry.get("hash") == content_hash


def record_plugin_trust(plugin_name: str, content_hash: str, plugin_dir: str) -> None:
    """Record trust for a user plugin in the manifest."""
    manifest = _load_trust_manifest()
    manifest[plugin_name] = {
        "hash": content_hash,
        "path": plugin_dir,
        "trusted_at": _utc_now_iso(),
    }
    _save_trust_manifest(manifest)


def revoke_plugin_trust(plugin_name: str) -> None:
    """Remove a plugin from the trust manifest."""
    manifest = _load_trust_manifest()
    manifest.pop(plugin_name, None)
    _save_trust_manifest(manifest)


def _utc_now_iso() -> str:
    """Return current UTC time as ISO string (no heavy deps)."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Symlink / hidden-directory safety checks
# ---------------------------------------------------------------------------


def _is_symlink_escape(child: Path, parent: Path) -> bool:
    """Return True if *child* resolves outside *parent* (symlink escape)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return False
    except ValueError:
        return True


def _should_skip_entry(item: Path, parent: Path) -> bool:
    """Return True if *item* should be skipped during plugin/skill discovery.

    Skips:
    - hidden dirs (name starts with '.' or '_')
    - symlink escapes outside *parent*
    """
    if item.name.startswith(".") or item.name.startswith("_"):
        return True
    if _is_symlink_escape(item, parent):
        logger.warning(
            "Skipping %s: resolves outside parent directory (symlink escape)", item
        )
        return True
    return False


# ---------------------------------------------------------------------------
# Built-in plugin loading
# ---------------------------------------------------------------------------


def _load_builtin_plugins(plugins_dir: Path) -> list[str]:
    """Load built-in plugins from the package plugins directory.

    Returns list of successfully loaded plugin names.
    """
    loaded = []

    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            plugin_name = item.name
            callbacks_file = item / "register_callbacks.py"

            if callbacks_file.exists():
                try:
                    module_name = f"code_puppy.plugins.{plugin_name}.register_callbacks"
                    importlib.import_module(module_name)
                    loaded.append(plugin_name)
                except ImportError as e:
                    logger.warning(
                        "Failed to import callbacks from built-in plugin %s: %s",
                        plugin_name,
                        e,
                    )
                except Exception as e:
                    logger.error(
                        "Unexpected error loading built-in plugin %s: %s",
                        plugin_name,
                        e,
                    )

    return loaded


# ---------------------------------------------------------------------------
# User plugin loading (trust-gated)
# ---------------------------------------------------------------------------


def _make_user_module_name(plugin_name: str, content_hash: str) -> str:
    """Build a unique, safe module name for a user plugin.

    Format: ``code_puppy_user_plugin_{safe_name}_{hash_prefix}``
    The hash prefix (first 12 chars) avoids name collisions while keeping
    the module name readable.
    """
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", plugin_name)
    return f"code_puppy_user_plugin_{safe}_{content_hash[:12]}"


def _load_single_user_plugin(
    plugin_dir: Path,
    plugin_name: str,
    user_plugins_dir: Path,
) -> Optional[str]:
    """Attempt to load a single user plugin directory.

    Returns the plugin name on success, None on failure/skip.
    """
    # Safety checks
    if _should_skip_entry(plugin_dir, user_plugins_dir):
        return None

    # Validate plugin name
    if not _SAFE_NAME_RE.match(plugin_name):
        logger.warning(
            "Skipping user plugin '%s': name contains unsafe characters", plugin_name
        )
        return None

    callbacks_file = plugin_dir / "register_callbacks.py"
    init_file = plugin_dir / "__init__.py"

    # Pick the file to load (prefer register_callbacks.py)
    load_file = None
    if callbacks_file.exists():
        if _is_symlink_escape(callbacks_file, plugin_dir):
            logger.warning(
                "Skipping user plugin '%s': register_callbacks.py is a symlink escape",
                plugin_name,
            )
            return None
        load_file = callbacks_file
    elif init_file.exists():
        if _is_symlink_escape(init_file, plugin_dir):
            logger.warning(
                "Skipping user plugin '%s': __init__.py is a symlink escape",
                plugin_name,
            )
            return None
        load_file = init_file
    else:
        # No entry point file
        return None

    # Compute content hash for trust check
    content_hash = compute_plugin_hash(plugin_dir)

    # Fail closed: untrusted plugins are NOT imported
    if not is_plugin_trusted(plugin_name, content_hash):
        logger.warning(
            "User plugin '%s' is not trusted (hash: %s…). "
            "To trust it, run: /plugin trust %s  "
            "or set CODE_PUPPY_TRUST_ALL_USER_PLUGINS=1 (dangerous).",
            plugin_name,
            content_hash[:12],
            plugin_name,
        )
        return None

    # Build unique module name to avoid import shadowing
    module_name = _make_user_module_name(plugin_name, content_hash)

    try:
        spec = importlib.util.spec_from_file_location(module_name, load_file)
        if spec is None or spec.loader is None:
            logger.warning(
                "Could not create module spec for user plugin: %s", plugin_name
            )
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return plugin_name

    except ImportError as e:
        logger.warning(
            "Failed to import callbacks from user plugin %s: %s", plugin_name, e
        )
    except Exception as e:
        logger.error(
            "Unexpected error loading user plugin %s: %s", plugin_name, e, exc_info=True
        )

    return None


def _load_user_plugins(user_plugins_dir: Path) -> list[str]:
    """Load user plugins from ~/.code_puppy/plugins/.

    Each plugin should be a directory containing a register_callbacks.py file.
    Plugins are loaded via importlib with unique module names — no sys.path
    insertion.  Untrusted plugins are skipped with a clear warning.

    Returns list of successfully loaded plugin names.
    """
    loaded = []

    if not user_plugins_dir.exists():
        return loaded

    if not user_plugins_dir.is_dir():
        logger.warning("User plugins path is not a directory: %s", user_plugins_dir)
        return loaded

    # Allow trusting all user plugins via env var (for development / CI)
    trust_all = os.environ.get("CODE_PUPPY_TRUST_ALL_USER_PLUGINS", "") == "1"

    for item in user_plugins_dir.iterdir():
        if not item.is_dir():
            continue

        plugin_name = item.name

        # Safety checks
        if _should_skip_entry(item, user_plugins_dir):
            continue

        # Validate plugin name
        if not _SAFE_NAME_RE.match(plugin_name):
            logger.warning(
                "Skipping user plugin '%s': name contains unsafe characters",
                plugin_name,
            )
            continue

        # Dev override: auto-trust everything
        if trust_all:
            content_hash = compute_plugin_hash(item)
            if not is_plugin_trusted(plugin_name, content_hash):
                record_plugin_trust(plugin_name, content_hash, str(item))

        result = _load_single_user_plugin(item, plugin_name, user_plugins_dir)
        if result is not None:
            loaded.append(result)

    return loaded


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_plugin_callbacks() -> dict[str, list[str]]:
    """Dynamically load register_callbacks.py from all plugin sources.

    Loads plugins from:
    1. Built-in plugins in the code_puppy/plugins/ directory
    2. User plugins in ~/.code_puppy/plugins/

    User plugins require trust (content-hash match in manifest).
    No sys.path manipulation is performed.

    Returns dict with 'builtin' and 'user' keys containing lists of loaded
    plugin names.

    NOTE: This function is idempotent - calling it multiple times will only
    load plugins once. Subsequent calls return empty lists.
    """
    global _PLUGINS_LOADED

    # Prevent duplicate loading - plugins register callbacks at import time,
    # so re-importing would cause duplicate registrations
    if _PLUGINS_LOADED:
        logger.debug("Plugins already loaded, skipping duplicate load")
        return {"builtin": [], "user": []}

    plugins_dir = Path(__file__).parent

    result = {
        "builtin": _load_builtin_plugins(plugins_dir),
        "user": _load_user_plugins(USER_PLUGINS_DIR),
    }

    _PLUGINS_LOADED = True
    logger.debug(
        "Loaded plugins: builtin=%s, user=%s", result["builtin"], result["user"]
    )

    return result


def get_user_plugins_dir() -> Path:
    """Return the path to the user plugins directory."""
    return USER_PLUGINS_DIR


def ensure_user_plugins_dir() -> Path:
    """Create the user plugins directory if it doesn't exist.

    Returns the path to the directory.
    """
    ensure_private_dir(USER_PLUGINS_DIR)
    return USER_PLUGINS_DIR
