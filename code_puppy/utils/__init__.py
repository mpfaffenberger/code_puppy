"""Code Puppy utilities package.

Provides various utility functions and helpers for Code Puppy.
"""

from code_puppy.utils.windows_check import (
    check_long_paths_enabled,
    get_long_paths_warning,
    is_path_too_long,
    is_windows,
    warn_if_long_paths_disabled,
)

__all__ = [
    "is_windows",
    "check_long_paths_enabled",
    "get_long_paths_warning",
    "warn_if_long_paths_disabled",
    "is_path_too_long",
]
