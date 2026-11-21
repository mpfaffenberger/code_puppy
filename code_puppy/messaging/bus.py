"""0.0.x import path for the ``emit_*`` functions."""

from code_puppy.messaging import (
    emit_debug,
    emit_error,
    emit_info,
    emit_success,
    emit_system_message,
    emit_warning,
)

__all__ = [
    "emit_debug",
    "emit_error",
    "emit_info",
    "emit_success",
    "emit_system_message",
    "emit_warning",
]
