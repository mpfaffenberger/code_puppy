"""Session logging system for recording interactive sessions.

This module provides configurable logging of interactive code_puppy sessions,
capturing user prompts, agent reasoning, responses, tool calls, and outputs.
Logs can be stored in markdown or JSON format.
"""

from typing import Optional

from code_puppy.session_logging.logger import SessionLogger

# Global session logger instance
_global_session_logger: Optional[SessionLogger] = None


def set_global_session_logger(logger: Optional[SessionLogger]) -> None:
    """Set the global session logger instance."""
    global _global_session_logger
    _global_session_logger = logger


def get_global_session_logger() -> Optional[SessionLogger]:
    """Get the global session logger instance."""
    return _global_session_logger


__all__ = ["SessionLogger", "set_global_session_logger", "get_global_session_logger"]
