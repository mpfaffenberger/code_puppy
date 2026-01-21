"""Universal Constructor - Dynamic tool creation and management plugin.

This plugin enables users to create, manage, and deploy custom tools
that extend Code Puppy's capabilities. Tools are stored in the user's
config directory and can be organized into namespaces via subdirectories.
"""

from pathlib import Path

# User tools directory - where user-created UC tools live
USER_UC_DIR = Path.home() / ".code_puppy" / "plugins" / "universal_constructor"

__all__ = ["USER_UC_DIR"]
