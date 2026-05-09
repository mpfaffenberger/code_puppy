"""Hook trust engine for project-level hooks.

Requires explicit user trust before executing repository-controlled hooks.
Trust decisions are stored privately in XDG state and keyed by:
  - project root directory
  - hooks file path
  - content hash (SHA-256 of hooks file)

This prevents repo-controlled hooks from executing automatically after
cloning or when content changes.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# XDG state directory for private trust storage
_TRUST_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "code_puppy"
)
_TRUST_FILE = _TRUST_DIR / "hook_trust.json"

# Minimal env vars allowed for project hooks
_SAFE_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "SHELL",
    "PWD",
    "TERM",
    "LANG",
    "LC_ALL",
    "USER",
    "LOGNAME",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_TOOL_INPUT",
    "CLAUDE_TOOL_NAME",
    "CLAUDE_HOOK_EVENT",
    "CLAUDE_CODE_HOOK",
    "CLAUDE_FILE_PATH",
}

# Patterns that suggest a secret-bearing env var
_SECRET_ENV_PATTERNS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "private_key",
    "ssh_key",
    "aws_access",
    "aws_secret",
    "bearer",
    "jwt",
    "client_secret",
    "access_token",
    "refresh_token",
    "id_token",
)


def _ensure_private_dir(path: Path) -> Path:
    """Ensure directory exists with 0o700 permissions."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _atomic_write_private_json(file_path: Path, data: dict) -> None:
    """Atomically write JSON with 0o600 permissions."""
    tmp_path = file_path.with_suffix(".tmp")
    try:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(file_path))
        try:
            os.chmod(file_path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _load_trust_db() -> Dict[str, dict]:
    """Load the trust database from private storage."""
    _ensure_private_dir(_TRUST_DIR)
    if not _TRUST_FILE.exists():
        return {}
    try:
        with open(_TRUST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_trust_db(db: Dict[str, dict]) -> None:
    """Save the trust database to private storage."""
    _ensure_private_dir(_TRUST_DIR)
    _atomic_write_private_json(_TRUST_FILE, db)


def _compute_trust_key(
    project_root: str, hooks_file_path: str, content_hash: str
) -> str:
    """Compute a deterministic trust key."""
    raw = f"{project_root}\n{hooks_file_path}\n{content_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of hook file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_hook_trusted(
    project_root: str,
    hooks_file_path: str,
    content_hash: str,
) -> bool:
    """Check whether a project hook file is explicitly trusted.

    Args:
        project_root: Absolute path to the project root directory.
        hooks_file_path: Absolute path to the hooks configuration file.
        content_hash: SHA-256 hash of the current hooks file content.

    Returns:
        True if the user has previously approved this exact content.
    """
    db = _load_trust_db()
    key = _compute_trust_key(project_root, hooks_file_path, content_hash)
    entry = db.get(key)
    if entry is None:
        return False
    stored_hash = entry.get("content_hash")
    if stored_hash != content_hash:
        return False
    return entry.get("trusted", False)


def approve_hook(
    project_root: str,
    hooks_file_path: str,
    content_hash: str,
) -> None:
    """Explicitly mark a project hook file as trusted.

    Args:
        project_root: Absolute path to the project root directory.
        hooks_file_path: Absolute path to the hooks configuration file.
        content_hash: SHA-256 hash of the current hooks file content.
    """
    db = _load_trust_db()
    key = _compute_trust_key(project_root, hooks_file_path, content_hash)
    db[key] = {
        "project_root": project_root,
        "hooks_file_path": hooks_file_path,
        "content_hash": content_hash,
        "trusted": True,
    }
    _save_trust_db(db)
    logger.info(f"Hook trusted: {hooks_file_path} (hash={content_hash[:16]}...)")


def revoke_hook_trust(
    project_root: str,
    hooks_file_path: str,
) -> None:
    """Revoke trust for a project hook file regardless of content hash.

    Args:
        project_root: Absolute path to the project root directory.
        hooks_file_path: Absolute path to the hooks configuration file.
    """
    db = _load_trust_db()
    keys_to_remove = []
    for key, entry in db.items():
        if (
            entry.get("project_root") == project_root
            and entry.get("hooks_file_path") == hooks_file_path
        ):
            keys_to_remove.append(key)
    for key in keys_to_remove:
        del db[key]
    if keys_to_remove:
        _save_trust_db(db)
        logger.info(f"Hook trust revoked: {hooks_file_path}")


def build_minimal_hook_env(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build a minimal environment dict for project hooks.

    Strips secret-like environment variables while preserving safe
    operational variables and any hook-specific vars.

    Args:
        base_env: Optional base environment to filter. Defaults to os.environ.

    Returns:
        Filtered environment dictionary.
    """
    env = base_env if base_env is not None else os.environ.copy()
    filtered: Dict[str, str] = {}
    for key, value in env.items():
        upper_key = key.upper()
        # Always allow safe vars
        if upper_key in _SAFE_ENV_ALLOWLIST:
            filtered[key] = value
            continue
        # Block anything that looks secret-bearing
        lower_key = key.lower()
        if any(pattern in lower_key for pattern in _SECRET_ENV_PATTERNS):
            continue
        # Block very long values that might be tokens/keys
        if len(value) > 4096 and upper_key not in _SAFE_ENV_ALLOWLIST:
            continue
        filtered[key] = value
    return filtered


def cap_hook_output(text: str, max_chars: int = 4096, max_lines: int = 256) -> str:
    """Cap hook stdout/stderr to prevent unbounded output in model context.

    Args:
        text: Raw output string.
        max_chars: Maximum total characters to retain.
        max_lines: Maximum number of lines to retain.

    Returns:
        Capped output with a truncation marker if trimmed.
    """
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    else:
        truncated = False
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True
    if truncated:
        result += "\n... [output truncated]"
    return result
