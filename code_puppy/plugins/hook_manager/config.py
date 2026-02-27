"""
Helpers for reading and writing hook configurations from both global and project sources.

Supports:
- Global hooks: ~/.code_puppy/hooks.json
- Project hooks: .claude/settings.json

Hooks from both sources are loaded and can be managed independently in the TUI.
"""

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

_SETTINGS_FILENAME = ".claude/settings.json"
_GLOBAL_HOOKS_FILE = os.path.expanduser("~/.code_puppy/hooks.json")

HookSource = Literal["project", "global"]


def _find_settings_path() -> Path:
    """Return the path to .claude/settings.json, searching from cwd upward."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / _SETTINGS_FILENAME
        if candidate.exists():
            return candidate
    return cwd / _SETTINGS_FILENAME


def _load_global_hooks_config() -> Dict[str, Any]:
    """Load hooks from ~/.code_puppy/hooks.json."""
    path = Path(_GLOBAL_HOOKS_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Handle both wrapped {"hooks": {...}} and direct format
        if "hooks" in data and isinstance(data["hooks"], dict):
            return data.get("hooks", {})
        return data
    except Exception as exc:
        logger.warning("Failed to parse global hooks from %s: %s", path, exc)
        return {}


def _load_project_hooks_config() -> Dict[str, Any]:
    """Load hooks from .claude/settings.json."""
    path = _find_settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("hooks", {})
    except Exception as exc:
        logger.warning("Failed to parse project hooks from %s: %s", path, exc)
        return {}


def load_hooks_config() -> Dict[str, Any]:
    """Load raw hooks config from .claude/settings.json (project only).

    Returns the value of the top-level "hooks" key, or {} if absent/unreadable.
    Note: For the TUI, we load hooks from both sources separately.
    """
    return _load_project_hooks_config()


def load_all_hooks_config() -> Dict[str, Any]:
    """Load and merge hooks from both global and project sources.

    Returns a merged configuration with all hooks.
    """
    global_hooks = _load_global_hooks_config()
    project_hooks = _load_project_hooks_config()

    # Simple merge: combine hook groups
    merged = {}
    for event_type in set(list(global_hooks.keys()) + list(project_hooks.keys())):
        if event_type.startswith("_"):
            # Skip comment keys
            merged[event_type] = project_hooks.get(event_type) or global_hooks.get(
                event_type
            )
            continue

        global_groups = (
            global_hooks.get(event_type, [])
            if isinstance(global_hooks.get(event_type), list)
            else []
        )
        project_groups = (
            project_hooks.get(event_type, [])
            if isinstance(project_hooks.get(event_type), list)
            else []
        )

        if global_groups or project_groups:
            merged[event_type] = global_groups + project_groups

    return merged


def save_hooks_config(hooks: Dict[str, Any]) -> Path:
    """Persist hooks config back to .claude/settings.json.

    Performs a read-modify-write so other top-level keys are preserved.
    Returns the path written.
    """
    path = _find_settings_path()
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing["hooks"] = hooks
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    logger.debug("Saved hooks config to %s", path)
    return path


def save_global_hooks_config(hooks: Dict[str, Any]) -> Path:
    """Persist hooks config to ~/.code_puppy/hooks.json.

    Returns the path written.
    """
    path = Path(_GLOBAL_HOOKS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
    logger.debug("Saved global hooks config to %s", path)
    return path


class HookEntry:
    """Flat, mutable representation of a single hook for the TUI."""

    __slots__ = (
        "event_type",
        "matcher",
        "hook_type",
        "command",
        "timeout",
        "enabled",
        "hook_id",
        "source",
        "_group_index",
        "_hook_index",
    )

    def __init__(
        self,
        event_type: str,
        matcher: str,
        hook_type: str,
        command: str,
        timeout: int = 5000,
        enabled: bool = True,
        hook_id: Optional[str] = None,
        source: HookSource = "project",
        group_index: int = 0,
        hook_index: int = 0,
    ) -> None:
        self.event_type = event_type
        self.matcher = matcher
        self.hook_type = hook_type
        self.command = command
        self.timeout = timeout
        self.enabled = enabled
        self.hook_id = hook_id
        self.source = source
        self._group_index = group_index
        self._hook_index = hook_index

    @property
    def display_command(self) -> str:
        """Command truncated to 60 chars for list display."""
        cmd = self.command
        return cmd[:57] + "..." if len(cmd) > 60 else cmd

    @property
    def display_matcher(self) -> str:
        """Matcher truncated to 40 chars."""
        m = self.matcher
        return m[:37] + "..." if len(m) > 40 else m


def flatten_hooks(
    hooks_config: Dict[str, Any], source: HookSource = "project"
) -> List[HookEntry]:
    """Convert nested hooks config into a flat list of HookEntry objects.

    Each entry remembers its group_index and hook_index for round-trip
    serialisation, and which source it came from.
    """
    entries: List[HookEntry] = []
    for event_type, groups in hooks_config.items():
        if event_type.startswith("_"):
            # Skip comment keys
            continue
        if not isinstance(groups, list):
            continue
        for g_idx, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher", "*")
            for h_idx, hook in enumerate(group.get("hooks", [])):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command") or hook.get("prompt", "")
                entries.append(
                    HookEntry(
                        event_type=event_type,
                        matcher=matcher,
                        hook_type=hook.get("type", "command"),
                        command=command,
                        timeout=hook.get("timeout", 5000),
                        enabled=hook.get("enabled", True),
                        hook_id=hook.get("id"),
                        source=source,
                        group_index=g_idx,
                        hook_index=h_idx,
                    )
                )
    return entries


def flatten_all_hooks() -> List[HookEntry]:
    """Load and flatten hooks from both global and project sources.

    Returns a combined list with source information for each hook.
    """
    global_config = _load_global_hooks_config()
    project_config = _load_project_hooks_config()

    global_entries = flatten_hooks(global_config, source="global")
    project_entries = flatten_hooks(project_config, source="project")

    # Project hooks first for easier viewing
    return project_entries + global_entries


def toggle_hook_enabled(
    hooks_config: Dict[str, Any],
    event_type: str,
    group_index: int,
    hook_index: int,
    enabled: bool,
) -> Dict[str, Any]:
    """Return a deep copy of hooks_config with the specified hook toggled.

    Does NOT write to disk – call save_hooks_config() afterwards.
    """
    cfg = copy.deepcopy(hooks_config)
    try:
        hook = cfg[event_type][group_index]["hooks"][hook_index]
        hook["enabled"] = enabled
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("toggle_hook_enabled: cannot find hook (%s)", exc)
    return cfg


def delete_hook(
    hooks_config: Dict[str, Any],
    event_type: str,
    group_index: int,
    hook_index: int,
) -> Dict[str, Any]:
    """Return a deep copy of hooks_config with the specified hook removed.

    Empty groups and event keys are pruned automatically.
    Does NOT write to disk – call save_hooks_config() afterwards.
    """
    cfg = copy.deepcopy(hooks_config)
    try:
        group = cfg[event_type][group_index]
        group["hooks"].pop(hook_index)
        if not group["hooks"]:
            cfg[event_type].pop(group_index)
        if not cfg[event_type]:
            del cfg[event_type]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("delete_hook: cannot remove hook (%s)", exc)
    return cfg
