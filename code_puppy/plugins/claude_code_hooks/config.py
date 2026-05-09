"""
Configuration loader for Claude Code hooks.

Loads and merges hooks from multiple locations:
1. ~/.code_puppy/hooks.json (global level) - always loaded if exists
2. .claude/settings.json (project-level) - merged with global

Both configurations are loaded and merged so that hooks from both levels
coexist and execute together.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.hook_engine.trust import compute_content_hash, is_hook_trusted

logger = logging.getLogger(__name__)

PROJECT_HOOKS_FILE = ".claude/settings.json"
GLOBAL_HOOKS_FILE = os.path.expanduser("~/.code_puppy/hooks.json")


def _deep_merge_hooks(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge hook configurations, combining event types and hook groups.

    When the same event type exists in both base and overlay, their hook groups
    are concatenated (overlay hooks appear after base hooks).

    Args:
        base: Base configuration dictionary
        overlay: Configuration to merge on top

    Returns:
        Merged configuration with all hooks from both sources
    """
    merged = dict(base)

    for event_type, hook_groups in overlay.items():
        if event_type.startswith("_"):
            # Skip comment keys
            merged[event_type] = hook_groups
            continue

        if event_type not in merged:
            # New event type, just add it
            merged[event_type] = hook_groups
        elif isinstance(merged[event_type], list) and isinstance(hook_groups, list):
            # Both are lists, concatenate them (overlay hooks come after)
            merged[event_type] = merged[event_type] + hook_groups
            logger.debug(
                f"Merged {len(hook_groups)} hook group(s) for event '{event_type}'"
            )
        else:
            # Type mismatch or unexpected structure, keep base
            logger.warning(
                f"Cannot merge event type '{event_type}': type mismatch or unexpected structure"
            )

    return merged


def load_hooks_config() -> Optional[Dict[str, Any]]:
    """
    Load and merge hooks configuration from available sources.

    Priority order:
    1. ~/.code_puppy/hooks.json (global level) - always loaded if exists
    2. .claude/settings.json (project-level) - merged with global

    Returns:
        Merged configuration dictionary or None if no config found.
        This function preserves backward compatibility; trust metadata
        is handled separately via load_hooks_config_with_sources().
    """
    config, _sources = load_hooks_config_with_sources()
    return config


def load_hooks_config_with_sources() -> Tuple[Optional[Dict[str, Any]], List[dict]]:
    """
    Load and merge hooks configuration from available sources with trust metadata.

    Priority order:
    1. ~/.code_puppy/hooks.json (global level) - always loaded if exists
    2. .claude/settings.json (project-level) - merged with global

    Returns:
        Tuple of (merged configuration dictionary, list of source metadata dicts).
        Each source metadata dict contains:
            - path: file path
            - source: "global" | "project"
            - config: the raw hooks dict from this source
            - content_hash: SHA-256 of file content
            - trusted: bool
    """
    merged_config: Dict[str, Any] = {}
    sources: List[dict] = []

    # Load global hooks first
    global_config_path = Path(GLOBAL_HOOKS_FILE)

    if global_config_path.exists():
        try:
            raw = global_config_path.read_text(encoding="utf-8")
            config = json.loads(raw)
            hooks_part = None
            if "hooks" in config and isinstance(config["hooks"], dict):
                logger.info(
                    f"Loaded hooks configuration (wrapped format) from {GLOBAL_HOOKS_FILE}"
                )
                hooks_part = config["hooks"]
            elif isinstance(config, dict):
                logger.info(f"Loaded hooks configuration from {GLOBAL_HOOKS_FILE}")
                hooks_part = config
            if hooks_part is not None:
                merged_config = _deep_merge_hooks(merged_config, hooks_part)
                sources.append(
                    {
                        "path": str(global_config_path),
                        "source": "global",
                        "config": hooks_part,
                        "content_hash": compute_content_hash(raw),
                        "trusted": True,
                    }
                )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {GLOBAL_HOOKS_FILE}: {e}")
        except Exception as e:
            logger.error(f"Failed to load {GLOBAL_HOOKS_FILE}: {e}", exc_info=True)

    # Load and merge project-level hooks
    project_config_path = Path(os.getcwd()) / PROJECT_HOOKS_FILE

    if project_config_path.exists():
        try:
            raw = project_config_path.read_text(encoding="utf-8")
            config = json.loads(raw)
            hooks_config = config.get("hooks")
            if hooks_config:
                logger.info(f"Merging hooks configuration from {project_config_path}")
                merged_config = _deep_merge_hooks(merged_config, hooks_config)
                content_hash = compute_content_hash(raw)
                project_root = str(Path(os.getcwd()).resolve())
                trusted = is_hook_trusted(
                    project_root,
                    str(project_config_path.resolve()),
                    content_hash,
                )
                sources.append(
                    {
                        "path": str(project_config_path),
                        "source": "project",
                        "config": hooks_config,
                        "content_hash": content_hash,
                        "trusted": trusted,
                    }
                )
            else:
                logger.debug(f"No 'hooks' section found in {project_config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {project_config_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load {project_config_path}: {e}", exc_info=True)

    if not merged_config:
        logger.debug("No hooks configuration found")
        return None, sources

    event_count = len(
        [event for event in merged_config.keys() if not event.startswith("_")]
    )
    logger.info(f"Hooks configuration ready ({event_count} event type(s))")
    return merged_config, sources


def get_hooks_config_paths() -> list:
    """
    Return list of hook configuration paths.

    Returns paths in order of precedence (project-level first, then global).
    Note: internally, hooks are loaded in reverse order (global first, then project)
    so that project-level hooks can extend/append to global hooks.
    """
    return [
        str(Path(os.getcwd()) / PROJECT_HOOKS_FILE),
        GLOBAL_HOOKS_FILE,
    ]
