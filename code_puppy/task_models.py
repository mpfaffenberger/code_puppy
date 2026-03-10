"""
Task Model Resolution - Surgical Profile System

This module provides a unified, extensible way to configure different models
for different tasks (compaction, vision, subagents, etc.).

Design Principles:
1. Single source of truth for task→model resolution
2. Graceful fallback chain (never breaks)
3. Minimal changes to existing code
4. Easy to extend with new task types
5. Great UX through /models and /profile commands

Configuration (puppy.cfg):
    # Task-specific model overrides (optional)
    compaction_model = gpt-4.1-nano
    vision_model = gemini-2.5-flash
    subagent_model = gpt-4.1

Usage:
    from code_puppy.task_models import get_model_for, Task

    model_name = get_model_for(Task.COMPACTATION)
    model = ModelFactory.get_model(model_name, config)
"""

from enum import Enum, auto
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import datetime
import json
from pathlib import Path

from code_puppy.config import (
    get_value,
    get_global_model_name,
    get_agent_pinned_model,
    set_value,
    reset_value,
)


class Task(Enum):
    """
    Task types that can have dedicated model configurations.

    Each task type represents a distinct use case that may benefit from
    a different model (cheaper, faster, or more capable).

    Only tasks that have actual integration points in the codebase are listed.
    """

    MAIN = auto()  # Main agent conversations
    COMPACTION = auto()  # Message summarization/compaction
    SUBAGENT = auto()  # Delegated agent invocations


@dataclass
class TaskModelConfig:
    """
    Configuration for a specific task type.

    Attributes:
        config_key: The puppy.cfg key for this task (e.g., "compaction_model")
        description: Human-readable description for UI
        fallback_task: Task to fall back to if not configured (None = global default)
        recommended_default: Suggested model for this task (informational)
        requires_capability: Optional capability required (e.g., "vision")
    """

    config_key: str
    description: str
    fallback_task: Optional["Task"] = None
    recommended_default: Optional[str] = None
    requires_capability: Optional[str] = None


# Task configuration registry - single source of truth
TASK_CONFIGS: Dict[Task, TaskModelConfig] = {
    Task.MAIN: TaskModelConfig(
        config_key="model_name",
        description="Main conversation model",
        fallback_task=None,
    ),
    Task.COMPACTION: TaskModelConfig(
        config_key="compaction_model",
        description="Message compaction and summarization",
        fallback_task=Task.MAIN,
    ),
    Task.SUBAGENT: TaskModelConfig(
        config_key="subagent_model",
        description="Delegated agent invocations",
        fallback_task=Task.MAIN,
    ),
}


class TaskModelResolver:
    """
    Resolves the appropriate model for a given task type.

    Resolution Chain (in order):
    1. Task-specific override (puppy.cfg: compaction_model, etc.)
    2. Agent-specific default (if agent context available)
    3. Global default model (puppy.cfg: model_name)
    4. Hard fallback (first available in models.json)

    This class is stateless and can be used anywhere.
    All methods are class methods for convenience.
    """

    _cache: Dict[Task, Optional[str]] = {}

    @classmethod
    def get_model(cls, task: Task, agent_name: Optional[str] = None) -> str:
        """
        Get the configured model for a task type.

        Args:
            task: The task type to get model for
            agent_name: Optional agent name for agent-specific resolution

        Returns:
            Model name string (never None, always falls back to global)

        Example:
            >>> TaskModelResolver.get_model(Task.COMPACTION)
            'gpt-4.1-nano'
        """
        config = TASK_CONFIGS.get(task)
        if not config:
            # Unknown task, fall back to global
            return get_global_model_name()

        # 1. Check task-specific override
        task_model = get_value(config.config_key)
        if task_model:
            return task_model

        # 2. Check agent-specific default (if agent provided)
        if agent_name:
            agent_model = get_agent_pinned_model(agent_name)
            if agent_model:
                return agent_model

        # 3. Fall back to parent task or global default
        if config.fallback_task:
            return cls.get_model(config.fallback_task, agent_name)

        # 4. Global default
        return get_global_model_name()

    @classmethod
    def set_model(cls, task: Task, model_name: str) -> None:
        """
        Set the model for a task type in config.

        Args:
            task: The task type to configure
            model_name: The model to use for this task
        """
        config = TASK_CONFIGS.get(task)
        if config:
            set_value(config.config_key, model_name)
            cls._cache.pop(task, None)  # Invalidate cache

    @classmethod
    def clear_model(cls, task: Task) -> None:
        """Clear task-specific model, reverting to default."""
        config = TASK_CONFIGS.get(task)
        if config:
            reset_value(config.config_key)
            cls._cache.pop(task, None)

    @classmethod
    def get_all_configs(cls, agent_name: Optional[str] = None) -> Dict[Task, Dict]:
        """
        Get all task model configurations for display.

        Returns dict with task -> {configured, effective, description, recommended}
        """
        result = {}
        for task, config in TASK_CONFIGS.items():
            configured = get_value(config.config_key)
            effective = cls.get_model(task, agent_name)
            result[task] = {
                "task": task,
                "config_key": config.config_key,
                "configured": configured,
                "effective": effective,
                "description": config.description,
                "recommended": config.recommended_default,
                "requires_capability": config.requires_capability,
                "is_custom": configured is not None,
            }
        return result

    @classmethod
    def get_profile_summary(cls, agent_name: Optional[str] = None) -> str:
        """
        Get a human-readable summary of the current profile.

        Returns:
            Multi-line string suitable for display in CLI
        """
        lines = ["📋 Model Profile Configuration", ""]
        configs = cls.get_all_configs(agent_name)

        for task, info in configs.items():
            task_name = task.name.ljust(12)
            effective = info["effective"] or "default"

            if info["is_custom"]:
                # Show configured override
                configured = info["configured"]
                lines.append(f"  {task_name} {configured} (override → {effective})")
            else:
                # Show effective model
                lines.append(f"  {task_name} {effective}")
                if info["recommended"]:
                    lines.append(f"      💡 Recommended: {info['recommended']}")

        return "\n".join(lines)


# =============================================================================
# Convenience Functions - Primary API
# =============================================================================


def get_model_for(task: Task, agent_name: Optional[str] = None) -> str:
    """
    Get the configured model for a task type.

    This is the primary API for getting task-specific models.

    Args:
        task: The task type (Task.COMPACTION, Task.VISION, etc.)
        agent_name: Optional agent name for context-aware resolution

    Returns:
        Model name string

    Example:
        >>> from code_puppy.task_models import get_model_for, Task
        >>> model_name = get_model_for(Task.COMPACTION)
        >>> model = ModelFactory.get_model(model_name, config)
    """
    return TaskModelResolver.get_model(task, agent_name)


def set_model_for(task: Task, model_name: str) -> None:
    """
    Set the model for a task type.

    Args:
        task: The task type to configure
        model_name: The model to use
    """
    TaskModelResolver.set_model(task, model_name)


def clear_model_for(task: Task) -> None:
    """Clear task-specific model override."""
    TaskModelResolver.clear_model(task)


def get_profile_summary(agent_name: Optional[str] = None) -> str:
    """Get human-readable profile summary."""
    return TaskModelResolver.get_profile_summary(agent_name)


def get_all_task_configs(agent_name: Optional[str] = None) -> Dict[Task, Dict]:
    """Get all task configurations for UI display."""
    return TaskModelResolver.get_all_configs(agent_name)


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================


def get_compaction_model() -> str:
    """Get model for message compaction. Convenience alias."""
    return get_model_for(Task.COMPACTION)


def get_subagent_model() -> str:
    """Get model for subagent invocations. Convenience alias."""
    return get_model_for(Task.SUBAGENT)


# =============================================================================
# Named Profile Management
# =============================================================================


def _get_profiles_dir() -> Path:
    """Get the profiles directory, creating it if needed."""
    from code_puppy.config import PROFILES_DIR

    profiles_dir = Path(PROFILES_DIR)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def _get_profile_path(name: str) -> Path:
    """Get the file path for a named profile."""
    return _get_profiles_dir() / f"{name}.json"


def list_profiles() -> List[Dict]:
    """
    List all saved profiles.

    Returns:
        List of profile dicts with 'name' and 'description' keys
    """
    profiles_dir = _get_profiles_dir()
    profiles = []

    for profile_file in profiles_dir.glob("*.json"):
        try:
            with open(profile_file, "r") as f:
                data = json.load(f)
                profiles.append(
                    {
                        "name": data.get("name", profile_file.stem),
                        "description": data.get("description", ""),
                        "models": data.get("models", {}),
                    }
                )
        except (json.JSONDecodeError, IOError):
            continue

    return sorted(profiles, key=lambda p: p["name"])


def profile_exists(name: str) -> bool:
    """Check if a profile with the given name exists."""
    return _get_profile_path(name).exists()


def save_profile(name: str, description: str = "") -> bool:
    """
    Save current model settings as a named profile.

    Args:
        name: Profile name (alphanumeric, dashes, underscores)
        description: Optional description of the profile

    Returns:
        True if saved successfully
    """
    # Validate name
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        return False

    # Collect current model settings
    models = {}
    for task, config in TASK_CONFIGS.items():
        current = get_value(config.config_key)
        if current:
            models[task.name.lower()] = current

    profile_data = {
        "name": name,
        "description": description,
        "models": models,
        "created": datetime.datetime.now().isoformat(),
    }

    profile_path = _get_profile_path(name)
    with open(profile_path, "w") as f:
        json.dump(profile_data, f, indent=2)

    return True


def load_profile(name: str) -> Tuple[bool, str]:
    """
    Load a named profile, applying its model settings.

    Args:
        name: Profile name to load

    Returns:
        Tuple of (success, message)
    """
    profile_path = _get_profile_path(name)

    if not profile_path.exists():
        return False, f"Profile '{name}' not found"

    try:
        with open(profile_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Failed to read profile: {e}"

    models = data.get("models", {})
    applied = []

    # Apply each model setting
    for task_name, model_name in models.items():
        task_name_upper = task_name.upper()
        try:
            task = Task[task_name_upper]
            set_model_for(task, model_name)
            applied.append(f"{task_name_upper}={model_name}")
        except KeyError:
            continue  # Unknown task, skip

    # Set the profile as active
    set_value("active_profile", name)

    return True, f"Loaded profile '{name}': {', '.join(applied)}"


def delete_profile(name: str) -> Tuple[bool, str]:
    """
    Delete a named profile.

    Args:
        name: Profile name to delete

    Returns:
        Tuple of (success, message)
    """
    profile_path = _get_profile_path(name)

    if not profile_path.exists():
        return False, f"Profile '{name}' not found"

    try:
        profile_path.unlink()

        # Clear active profile if this was it
        if get_value("active_profile") == name:
            reset_value("active_profile")

        return True, f"Deleted profile '{name}'"
    except IOError as e:
        return False, f"Failed to delete profile: {e}"


def get_active_profile() -> Optional[str]:
    """Get the name of the currently active profile, if any."""
    return get_value("active_profile")


def clear_active_profile() -> None:
    """Clear all task-specific model settings and the active profile."""
    for task in Task:
        clear_model_for(task)
    reset_value("active_profile")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Types
    "Task",
    "TaskModelConfig",
    "TaskModelResolver",
    # Primary API
    "get_model_for",
    "set_model_for",
    "clear_model_for",
    "get_profile_summary",
    "get_all_task_configs",
    # Convenience aliases
    "get_compaction_model",
    "get_subagent_model",
    # Profile management
    "list_profiles",
    "profile_exists",
    "save_profile",
    "load_profile",
    "delete_profile",
    "get_active_profile",
    "clear_active_profile",
    # Registry
    "TASK_CONFIGS",
]
