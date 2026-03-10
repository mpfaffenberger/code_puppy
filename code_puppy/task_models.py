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
import os
from pathlib import Path

from code_puppy.config import (
    get_value,
    get_global_model_name,
    get_agent_pinned_model,
    set_value,
    reset_value,
    set_model_name,
    reset_session_model,
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
    env_var: Optional[str] = None  # Environment variable override (highest priority)


# Task configuration registry - single source of truth
TASK_CONFIGS: Dict[Task, TaskModelConfig] = {
    Task.MAIN: TaskModelConfig(
        config_key="model",  # matches config.py get_global_model_name / set_model_name
        description="Main conversation model",
        fallback_task=None,
    ),
    Task.COMPACTION: TaskModelConfig(
        config_key="compaction_model",
        description="Message compaction and summarization",
        fallback_task=Task.MAIN,
        env_var="CODE_PUPPY_COMPACTION_MODEL",
    ),
    Task.SUBAGENT: TaskModelConfig(
        config_key="subagent_model",
        description="Delegated agent invocations",
        fallback_task=Task.MAIN,
        env_var="CODE_PUPPY_SUBAGENT_MODEL",
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

        Resolution order (highest → lowest priority):
          0. Environment variable override (CODE_PUPPY_COMPACTION_MODEL, etc.)
          1. Active profile (read directly from profile JSON)
          2. Task-specific config key in puppy.cfg
          3. Agent-specific pinned model
          4. Fallback task (recursive)
          5. Global default model
        """
        config = TASK_CONFIGS.get(task)
        if not config:
            return get_global_model_name()

        # 0. Environment variable override
        if config.env_var:
            env_val = os.environ.get(config.env_var)
            if env_val:
                return env_val

        # 1. Active profile — read directly from the profile file so that
        #    profile resolution doesn't depend on config keys being written
        active_profile = get_value("active_profile")
        if active_profile:
            try:
                profile_path = _get_profile_path(active_profile)
                if profile_path.exists():
                    with open(profile_path) as _pf:
                        _pd = json.load(_pf)
                    profile_model = _pd.get("models", {}).get(task.name.lower())
                    if profile_model:
                        return profile_model
            except Exception:
                pass  # Profile unreadable — fall through

        # 2. Task-specific config key in puppy.cfg
        task_model = get_value(config.config_key)
        if task_model:
            return task_model

        # 3. Agent-specific pinned model
        if agent_name:
            agent_model = get_agent_pinned_model(agent_name)
            if agent_model:
                return agent_model

        # 4. Fall back to parent task or global default
        if config.fallback_task:
            return cls.get_model(config.fallback_task, agent_name)

        # 5. Global default
        return get_global_model_name()

    @classmethod
    def set_model(cls, task: Task, model_name: str) -> None:
        """
        Set the model for a task type in config.

        For Task.MAIN, routes through set_model_name() so the in-process
        session cache (_SESSION_MODEL) is updated immediately.

        If an active profile is loaded, the change is also written into the
        profile's JSON file so that the profile layer (highest-priority) sees
        the update immediately and the file stays in sync.
        """
        config = TASK_CONFIGS.get(task)
        if config:
            if task == Task.MAIN:
                # set_model_name updates _SESSION_MODEL and writes "model" to cfg
                set_model_name(model_name)
            else:
                set_value(config.config_key, model_name)
            # Patch active profile on disk so layer-1 reads the updated value
            cls._patch_active_profile(task, model_name)
            cls._cache.pop(task, None)

    @classmethod
    def _patch_active_profile(cls, task: Task, model_name: Optional[str]) -> None:
        """
        If a profile is currently active, update (or remove) the task's entry
        inside the profile's JSON file so that layer-1 resolution stays in sync
        with in-session changes.

        ``model_name=None`` removes the task key from the profile (used by
        ``clear_model`` when a profile is active).
        """
        active_profile = get_value("active_profile")
        if not active_profile:
            return
        try:
            profile_path = _get_profile_path(active_profile)
            if not profile_path.exists():
                return
            with open(profile_path, "r") as _pf:
                data = json.load(_pf)
            models = data.setdefault("models", {})
            if model_name is None:
                models.pop(task.name.lower(), None)
            else:
                models[task.name.lower()] = model_name
            with open(profile_path, "w") as _pf:
                json.dump(data, _pf, indent=2)
        except Exception:
            pass  # Never crash — profile update is best-effort

    @classmethod
    def clear_model(cls, task: Task) -> None:
        """Clear task-specific model, reverting to default."""
        config = TASK_CONFIGS.get(task)
        if config:
            if task == Task.MAIN:
                # Reset the session cache so get_global_model_name() re-reads
                reset_session_model()
            reset_value(config.config_key)
            # Remove from active profile so layer-1 stops shadowing the default
            cls._patch_active_profile(task, None)
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


def _is_safe_profile_name(name: str) -> bool:
    """Return True iff *name* is a valid, non-traversal profile name."""
    return bool(name) and all(c.isalnum() or c in "-_" for c in name)


def _get_profile_path(name: str) -> Path:
    """
    Return the resolved path for *name* inside the profiles directory.

    Raises ValueError if the resolved path escapes the profiles directory
    (directory-traversal guard).
    """
    profiles_dir = _get_profiles_dir().resolve()
    candidate = (profiles_dir / f"{name}.json").resolve()
    if not candidate.is_relative_to(profiles_dir):
        raise ValueError(f"Invalid profile name: {name!r}")
    return candidate


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
    if not _is_safe_profile_name(name):
        return False
    try:
        return _get_profile_path(name).exists()
    except ValueError:
        return False


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
    if not _is_safe_profile_name(name):
        return False, f"Invalid profile name: {name!r}"

    try:
        profile_path = _get_profile_path(name)
    except ValueError as exc:
        return False, str(exc)

    if not profile_path.exists():
        return False, f"Profile '{name}' not found"

    try:
        with open(profile_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Failed to read profile: {e}"

    models = data.get("models", {})
    applied = []

    # Clear existing per-task overrides so keys omitted from this profile
    # don't linger from a previously loaded profile or manual /set.
    for task in Task:
        if task != Task.MAIN:
            clear_model_for(task)

    # Apply each model setting from the profile
    for task_name, model_name in models.items():
        task_name_upper = task_name.upper()
        try:
            task = Task[task_name_upper]
            set_model_for(task, model_name)
            applied.append(f"{task_name_upper}={model_name}")
        except KeyError:
            continue  # Unknown task key in profile file, skip

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
    if not _is_safe_profile_name(name):
        return False, f"Invalid profile name: {name!r}"

    try:
        profile_path = _get_profile_path(name)
    except ValueError as exc:
        return False, str(exc)

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


def save_profile_from_models(
    name: str,
    description: str,
    models: Dict[Task, str],
) -> bool:
    """
    Save a named profile using an explicit agent→model mapping.

    Unlike ``save_profile()``, this does NOT read from the live puppy.cfg —
    it serialises exactly the *models* dict supplied by the caller.  Useful
    for TUI wizards that build a custom model set before writing to disk.

    Args:
        name:        Profile name (alphanumeric, dashes, underscores).
        description: Optional human-readable description.
        models:      Mapping of Task → model name to persist.

    Returns:
        True on success, False on validation or I/O failure.
    """
    if not _is_safe_profile_name(name):
        return False
    try:
        _get_profiles_dir().mkdir(parents=True, exist_ok=True)
        profile_path = _get_profile_path(name)
        serialised = {
            task.name.lower(): model for task, model in models.items() if model
        }
        data = {
            "name": name,
            "description": description,
            "models": serialised,
            "created": datetime.datetime.now().isoformat(),
        }
        with open(profile_path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


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
    "save_profile_from_models",
    "load_profile",
    "delete_profile",
    "get_active_profile",
    "clear_active_profile",
    # Registry
    "TASK_CONFIGS",
]
