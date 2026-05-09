"""Universal Constructor safety and approval engine.

Validates tool names/namespaces, blocks dangerous code patterns,
and stores per-tool approval decisions keyed by code hash.
"""

import ast
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# XDG state directory for private approval storage
_APPROVAL_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "code_puppy"
)
_APPROVAL_FILE = _APPROVAL_DIR / "uc_approvals.json"

# Valid tool name: [a-zA-Z_][a-zA-Z0-9_]*
_VALID_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Reserved module names that should not be used as tool names
_RESERVED_MODULE_NAMES: Set[str] = {
    "abc",
    "ast",
    "builtins",
    "code",
    "codecs",
    "collections",
    "copy",
    "datetime",
    "enum",
    "fnmatch",
    "functools",
    "glob",
    "hashlib",
    "importlib",
    "inspect",
    "io",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "pickle",
    "platform",
    "random",
    "re",
    "shutil",
    "signal",
    "socket",
    "sqlite3",
    "string",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "time",
    "traceback",
    "types",
    "typing",
    "urllib",
    "uuid",
    "warnings",
    "xml",
    "zipfile",
}

# Dangerous patterns that should BLOCK tool creation/execution
_DANGEROUS_IMPORTS_BLOCK: Set[str] = {
    "subprocess",
    "os.system",
    "eval",
    "exec",
    "compile",
    "__import__",
    "pickle",
    "marshal",
    "socket",
    "ctypes",
}

_DANGEROUS_CALLS_BLOCK: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "system",
    "popen",
    "spawn",
    "fork",
    "globals",
    "locals",
}

# Additional dangerous patterns that require explicit approval
_DANGEROUS_IMPORTS_APPROVAL: Set[str] = {
    "requests",
    "urllib",
    "http.client",
    "ftplib",
    "smtplib",
    "paramiko",
}

_DANGEROUS_OPEN_MODES = {
    "w",
    "a",
    "x",
    "wb",
    "ab",
    "xb",
    "w+",
    "a+",
    "r+",
    "rb+",
    "wb+",
}


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


def _load_approval_db() -> Dict[str, dict]:
    """Load the UC approval database from private storage."""
    _ensure_private_dir(_APPROVAL_DIR)
    if not _APPROVAL_FILE.exists():
        return {}
    try:
        with open(_APPROVAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_approval_db(db: Dict[str, dict]) -> None:
    """Save the UC approval database to private storage."""
    _ensure_private_dir(_APPROVAL_DIR)
    _atomic_write_private_json(_APPROVAL_FILE, db)


def compute_code_hash(code: str) -> str:
    """Compute SHA-256 hash of tool source code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def validate_tool_name(name: str) -> Optional[str]:
    """Strictly validate a tool name or namespace segment.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Tool name cannot be empty"
    if name.startswith(".") or name.startswith("_"):
        return f"Tool name cannot start with '.' or '_': {name}"
    if name.startswith("__") and name.endswith("__"):
        return f"Dunder names are reserved: {name}"
    if "/" in name or "\\" in name or ".." in name:
        return f"Path traversal characters not allowed: {name}"
    if not _VALID_NAME_RE.match(name):
        return f"Invalid tool name '{name}': must match [a-zA-Z_][a-zA-Z0-9_]*"
    if name.lower() in _RESERVED_MODULE_NAMES:
        return f"Tool name '{name}' is a reserved module name"
    return None


def validate_namespace(namespace: str) -> Optional[str]:
    """Validate a dot-separated namespace.

    Returns:
        Error message if invalid, None if valid.
    """
    if not namespace:
        return None
    parts = namespace.split(".")
    for part in parts:
        error = validate_tool_name(part)
        if error:
            return error
    return None


def validate_full_tool_name(name: str) -> Optional[str]:
    """Validate a full tool name possibly including namespace.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Tool name cannot be empty"
    if name.startswith(".") or name.endswith("."):
        return "Tool name cannot start or end with '.'"
    parts = name.split(".")
    for part in parts:
        error = validate_tool_name(part)
        if error:
            return error
    return None


class SafetyCheckResult:
    """Result of a UC safety check."""

    def __init__(
        self,
        safe: bool = True,
        blocked: bool = False,
        requires_approval: bool = False,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        code_hash: Optional[str] = None,
    ):
        self.safe = safe
        self.blocked = blocked
        self.requires_approval = requires_approval
        self.errors = errors or []
        self.warnings = warnings or []
        self.code_hash = code_hash


def check_code_safety(code: str) -> SafetyCheckResult:
    """Perform strict safety analysis on UC tool code.

    This is a BLOCKING check (not just advisory). Dangerous patterns
    like eval, exec, subprocess, pickle, etc. cause the tool to be
    rejected. Network-library usage requires explicit approval.

    Args:
        code: Python source code to analyze.

    Returns:
        SafetyCheckResult indicating whether the code is safe,
        blocked, or requires approval.
    """
    result = SafetyCheckResult(code_hash=compute_code_hash(code))

    # Parse AST
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.safe = False
        result.errors.append(f"Syntax error: {e}")
        return result

    dangerous_found: List[str] = []
    approval_required: List[str] = []

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _DANGEROUS_IMPORTS_BLOCK:
                    dangerous_found.append(f"import {alias.name}")
                elif alias.name in _DANGEROUS_IMPORTS_APPROVAL:
                    approval_required.append(f"import {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full_name = f"{module}.{alias.name}"
                if (
                    module in _DANGEROUS_IMPORTS_BLOCK
                    or full_name in _DANGEROUS_IMPORTS_BLOCK
                ):
                    dangerous_found.append(f"from {module} import {alias.name}")
                elif (
                    module in _DANGEROUS_IMPORTS_APPROVAL
                    or full_name in _DANGEROUS_IMPORTS_APPROVAL
                ):
                    approval_required.append(f"from {module} import {alias.name}")

        # Check function calls
        elif isinstance(node, ast.Call):
            func_name = _get_call_name(node)
            if func_name in _DANGEROUS_CALLS_BLOCK:
                line = getattr(node, "lineno", "?")
                dangerous_found.append(f"{func_name}() call at line {line}")
            elif func_name == "open":
                if _is_dangerous_open_call(node):
                    line = getattr(node, "lineno", "?")
                    dangerous_found.append(f"open() with write mode at line {line}")

    if dangerous_found:
        result.blocked = True
        result.safe = False
        result.errors.append(
            f"Blocked dangerous patterns: {', '.join(dangerous_found)}"
        )

    if approval_required and not result.blocked:
        result.requires_approval = True
        result.warnings.append(
            f"Potentially dangerous patterns require approval: {', '.join(approval_required)}"
        )

    return result


def _get_call_name(node: ast.Call) -> str:
    """Extract the function name from a Call node."""
    if hasattr(node, "func"):
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
    return ""


def _is_dangerous_open_call(node: ast.Call) -> bool:
    """Check if an open() call uses a dangerous (write) mode."""
    if len(node.args) >= 2:
        mode_arg = node.args[1]
        if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
            return mode_arg.value in _DANGEROUS_OPEN_MODES
    for kw in node.keywords:
        if kw.arg == "mode":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value in _DANGEROUS_OPEN_MODES
    return False


class UCApprovalStore:
    """Persistent store for UC tool approvals keyed by code hash."""

    def __init__(self):
        self._db: Dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._db = _load_approval_db()
            self._loaded = True

    def is_approved(self, tool_name: str, code_hash: str) -> bool:
        """Check whether a specific code hash is approved for a tool."""
        self._ensure_loaded()
        key = f"{tool_name}:{code_hash}"
        entry = self._db.get(key)
        if entry is None:
            return False
        stored_hash = entry.get("code_hash")
        if stored_hash != code_hash:
            return False
        return entry.get("approved", False)

    def approve(self, tool_name: str, code_hash: str) -> None:
        """Explicitly approve a tool code hash."""
        self._ensure_loaded()
        key = f"{tool_name}:{code_hash}"
        self._db[key] = {
            "tool_name": tool_name,
            "code_hash": code_hash,
            "approved": True,
        }
        _save_approval_db(self._db)
        logger.info(f"UC tool approved: {tool_name} (hash={code_hash[:16]}...)")

    def revoke(self, tool_name: str, code_hash: str) -> None:
        """Revoke approval for a tool code hash."""
        self._ensure_loaded()
        key = f"{tool_name}:{code_hash}"
        if key in self._db:
            del self._db[key]
            _save_approval_db(self._db)
            logger.info(f"UC tool approval revoked: {tool_name}")


def is_path_within_uc_dir(file_path: Path, uc_dir: Path) -> bool:
    """Verify that file_path is safely contained within uc_dir.

    Resolves both paths and checks for symlink escape.

    Returns:
        True if file_path is within uc_dir, False otherwise.
    """
    try:
        resolved_file = file_path.resolve()
        resolved_dir = uc_dir.resolve()
        resolved_file.relative_to(resolved_dir)
        return True
    except (ValueError, OSError):
        return False
