"""Configuration schema for session logging."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class SessionLoggingConfig:
    """Configuration for session logging."""

    enabled: bool = False
    log_file: str = "~/.code_puppy/sessions/{session_id}.md"
    format: Literal["markdown", "json"] = "markdown"
    include_user_prompts: bool = True
    include_agent_reasoning: bool = True
    include_agent_responses: bool = True
    include_tool_calls: bool = True
    include_tool_outputs: bool = True
    timestamp_format: Literal["ISO8601", "unix", "human"] = "ISO8601"

    def resolve_log_path(self, session_id: str) -> Path:
        """Resolve log file path with session_id substitution."""
        path_str = self.log_file.replace("{session_id}", session_id)
        return Path(path_str).expanduser().resolve()


def load_session_logging_config_from_dict(config_dict: dict) -> SessionLoggingConfig:
    """Load session logging config from a dictionary.

    Args:
        config_dict: Dictionary with session_logging configuration

    Returns:
        SessionLoggingConfig instance with validated settings
    """
    return SessionLoggingConfig(
        enabled=config_dict.get("enabled", False),
        log_file=config_dict.get("log_file", "~/.code_puppy/sessions/{session_id}.md"),
        format=config_dict.get("format", "markdown"),
        include_user_prompts=config_dict.get("user_prompts", True),
        include_agent_reasoning=config_dict.get("agent_reasoning", True),
        include_agent_responses=config_dict.get("agent_responses", True),
        include_tool_calls=config_dict.get("tool_calls", True),
        include_tool_outputs=config_dict.get("tool_outputs", True),
        timestamp_format=config_dict.get("timestamp_format", "ISO8601"),
    )
