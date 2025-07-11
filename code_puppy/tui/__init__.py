"""
Code Puppy TUI package.

This package provides a modern Text User Interface for Code Puppy using the Textual framework.
It maintains compatibility with existing functionality while providing an enhanced user experience.
"""

from .app import CodePuppyTUI, run_textual_ui

__all__ = ["CodePuppyTUI", "run_textual_ui"]
