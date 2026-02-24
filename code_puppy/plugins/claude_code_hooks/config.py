"""
Configuration loader for Claude Code hooks.

Loads hooks from multiple locations (in priority order):
1. .claude/settings.json (project-level, Claude Code compatible)
2. ~/.code_puppy/hooks.json (global level)
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

PROJECT_HOOKS_FILE = ".claude/settings.json"
GLOBAL_HOOKS_FILE = os.path.expanduser("~/.code_puppy/hooks.json")


def load_hooks_config() -> Optional[Dict[str, Any]]:
    """
    Load hooks configuration from available sources.

    Priority order:
    1. .claude/settings.json (project-level)
    2. ~/.code_puppy/hooks.json (global level)

    Returns:
        Configuration dictionary or None if no config found
    """
    project_config_path = Path(os.getcwd()) / PROJECT_HOOKS_FILE

    if project_config_path.exists():
        try:
            with open(project_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            hooks_config = config.get('hooks')
            if hooks_config:
                logger.info(f"Loaded hooks configuration from {project_config_path}")
                return hooks_config
            else:
                logger.debug(f"No 'hooks' section found in {project_config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {project_config_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load {project_config_path}: {e}", exc_info=True)

    global_config_path = Path(GLOBAL_HOOKS_FILE)

    if global_config_path.exists():
        try:
            with open(global_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if "hooks" in config and isinstance(config["hooks"], dict):
                logger.info(
                    f"Loaded hooks configuration (wrapped format) from {GLOBAL_HOOKS_FILE}"
                )
                return config["hooks"]
            logger.info(f"Loaded hooks configuration from {GLOBAL_HOOKS_FILE}")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {GLOBAL_HOOKS_FILE}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load {GLOBAL_HOOKS_FILE}: {e}", exc_info=True)
            return None

    logger.debug("No hooks configuration found")
    return None


def get_hooks_config_paths() -> list:
    return [
        str(Path(os.getcwd()) / PROJECT_HOOKS_FILE),
        GLOBAL_HOOKS_FILE,
    ]
