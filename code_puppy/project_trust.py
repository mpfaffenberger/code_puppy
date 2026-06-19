"""Persisted trust decisions for project-local executable resources."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

_LOCK = threading.RLock()
_ENV_OVERRIDE = "CODE_PUPPY_TRUST_PROJECT"


def _trust_file() -> Path:
    from code_puppy.config import CONFIG_DIR

    return Path(CONFIG_DIR) / "trust.json"


def _project_key(project_dir: Path | str | None = None) -> str:
    return str(Path(project_dir or Path.cwd()).expanduser().resolve())


def load_trust_decisions() -> dict[str, bool]:
    path = _trust_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): bool(value) for key, value in raw.items()}


def set_project_trusted(
    project_dir: Path | str | None,
    trusted: bool,
) -> None:
    with _LOCK:
        path = _trust_file()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        decisions = load_trust_decisions()
        decisions[_project_key(project_dir)] = trusted
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(decisions, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        temp.replace(path)


def get_project_trust(project_dir: Path | str | None = None) -> bool | None:
    override = os.getenv(_ENV_OVERRIDE, "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return load_trust_decisions().get(_project_key(project_dir))


def ensure_project_trusted(
    project_dir: Path | str | None = None,
    *,
    prompt: bool = True,
) -> bool:
    """Return whether project-local Python may be imported.

    Unknown projects fail closed when stdin is not interactive. Interactive
    decisions are persisted by canonical project path.
    """
    key = _project_key(project_dir)
    decision = get_project_trust(key)
    if decision is not None:
        return decision
    if not prompt or not getattr(sys.stdin, "isatty", lambda: False)():
        return False

    sys.stderr.write(
        "\nProject-local Code Puppy plugins execute Python during startup.\n"
        f"Trust this project? {key}\nType 'yes' to trust: "
    )
    sys.stderr.flush()
    try:
        trusted = input().strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        trusted = False
    set_project_trusted(key, trusted)
    return trusted


def filter_untrusted_project_paths(paths: list[str | Path]) -> list[str]:
    """Drop paths inside the current project until that project is trusted."""
    project = Path.cwd().resolve()
    project_paths: list[tuple[str, bool]] = []
    requires_trust = False
    for raw in paths:
        resolved = Path(raw).expanduser().resolve()
        is_project_path = resolved == project or project in resolved.parents
        project_paths.append((str(raw), is_project_path))
        requires_trust = requires_trust or is_project_path
    if not requires_trust or ensure_project_trusted(project):
        return [raw for raw, _ in project_paths]
    return [raw for raw, is_project_path in project_paths if not is_project_path]
