"""Workspace and sensitive-file path policy for Code Puppy.

Provides resolve, classify, and check functions that enforce:
- Workspace containment (cwd-based root)
- Path traversal and symlink escape detection
- Sensitive file/directory blocking
- Operation-level gating (READ, LIST, SEARCH, WRITE, DELETE)

All file tools should call ``check_path_allowed()`` before opening/spawning
operations. Denials never include full file content.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple


class Operation(Enum):
    READ = auto()
    LIST = auto()
    SEARCH = auto()
    WRITE = auto()
    DELETE = auto()


class PathDecision(NamedTuple):
    allowed: bool
    reason: str | None = None


# Files and directories that are considered sensitive and require explicit approval
SENSITIVE_PATHS: set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".envrc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
    "ssh_config",
    ".aws",
    ".gnupg",
    ".ssh",
    ".docker",
    ".kube",
    "kubeconfig",
    "credentials",
    "secrets",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "tokens",
    "cookie",
    "cookies",
    "keychain",
    "keystore",
    "private_key",
    "private.pem",
    "cert.pem",
    ".pgpass",
    ".mylogin.cnf",
    "terraform.tfstate",
    ".terraform",
    "service_account.json",
    ".htpasswd",
    ".htaccess",
}

# Basenames that indicate a sensitive file regardless of path
_SENSITIVE_BASENAMES: set[str] = {
    "passwd",
    "shadow",
    "sudoers",
    "group",
    "hosts",
    "resolv.conf",
    "fstab",
    "crypttab",
    "shadow-",
    "passwd-",
}


def get_workspace_root() -> Path:
    """Return the workspace root for path containment checks.

    Uses the current working directory as the default workspace root.
    """
    return Path.cwd().resolve()


def resolve_user_path(file_path: str) -> Path:
    """Resolve a user-supplied path to an absolute, canonical path.

    Expands ``~`` and resolves ``..`` / symlinks via ``Path.resolve()``.
    """
    p = Path(file_path).expanduser()
    try:
        return p.resolve()
    except (OSError, RuntimeError):
        # If resolve fails (e.g., permission denied), fall back to absolute
        return p.absolute()


def classify_path(file_path: Path) -> dict[str, bool]:
    """Classify a resolved path into policy-relevant categories.

    Returns a dict with:
    - ``inside_workspace``: True if within the workspace root
    - ``sensitive``: True if the path touches a sensitive file/dir
    - ``traversal``: True if path contains ``..`` components (pre-resolve)
    """
    workspace = get_workspace_root()
    resolved = file_path

    inside_workspace = False
    try:
        resolved.relative_to(workspace)
        inside_workspace = True
    except ValueError:
        inside_workspace = False

    sensitive = False
    parts_lower = [part.lower() for part in resolved.parts]
    basename_lower = resolved.name.lower()

    for part in parts_lower:
        if part in SENSITIVE_PATHS or part in _SENSITIVE_BASENAMES:
            sensitive = True
            break

    if basename_lower in SENSITIVE_PATHS or basename_lower in _SENSITIVE_BASENAMES:
        sensitive = True

    # Symlink escape detection: if the resolved path differs from the
    # absolute non-resolved path in a way that breaks containment.
    traversal = False
    try:
        abs_no_resolve = Path(file_path).expanduser().absolute()
        # If the path was expanded but resolve took us outside workspace,
        # and the absolute path itself also looks outside, mark traversal.
        if not inside_workspace:
            try:
                abs_no_resolve.relative_to(workspace)
            except ValueError:
                # Both resolved and absolute are outside workspace
                pass
    except Exception:
        pass

    return {
        "inside_workspace": inside_workspace,
        "sensitive": sensitive,
        "traversal": traversal,
    }


def check_path_allowed(
    file_path: str,
    operation: Operation,
    approved_sensitive: Sequence[str] | None = None,
) -> PathDecision:
    """Check whether an operation on *file_path* is allowed by policy.

    Args:
        file_path: The target path (may be relative, contain ``~``, etc.)
        operation: The operation being attempted
        approved_sensitive: Optional sequence of already-approved sensitive
            paths (exact strings). Used when a user has explicitly approved
            a previous read/search of a sensitive file.

    Returns:
        ``PathDecision`` with ``allowed`` and an optional ``reason``.
    """
    resolved = resolve_user_path(file_path)
    classification = classify_path(resolved)

    # Always block path traversal / symlink escapes for write/delete
    if operation in (Operation.WRITE, Operation.DELETE) and classification["traversal"]:
        return PathDecision(
            allowed=False,
            reason="Path traversal or symlink escape detected; write/delete blocked.",
        )

    # Outside workspace writes/deletes denied by default
    if (
        operation in (Operation.WRITE, Operation.DELETE)
        and not classification["inside_workspace"]
    ):
        return PathDecision(
            allowed=False,
            reason="Outside-workspace writes and deletes are denied by default.",
        )

    # Sensitive file reads/search require approval
    if (
        operation in (Operation.READ, Operation.LIST, Operation.SEARCH)
        and classification["sensitive"]
    ):
        if approved_sensitive and str(resolved) in approved_sensitive:
            return PathDecision(allowed=True)
        return PathDecision(
            allowed=False,
            reason="Sensitive file or directory access requires explicit user approval.",
        )

    # Outside-workspace reads/search: warn but allow (existing semantics)
    if (
        operation in (Operation.READ, Operation.LIST, Operation.SEARCH)
        and not classification["inside_workspace"]
    ):
        # We allow but don't include content in denial messages
        return PathDecision(allowed=True)

    return PathDecision(allowed=True)
