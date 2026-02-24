"""Skill Marketplace Plugin.

Browse and install community skills from the E2E Open Skills marketplace.

Commands:
    /skill-market  - Browse and install skills from the marketplace TUI
"""

from .register_callbacks import register_skill_marketplace_commands

register_skill_marketplace_commands()

__all__ = ["register_skill_marketplace_commands"]
