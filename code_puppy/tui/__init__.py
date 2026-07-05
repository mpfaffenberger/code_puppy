"""Code Puppy's Textual UI (the TUI rebuild).

See docs/TUI_REBUILD_PLAN.md for the phased roadmap. Activated via the
``ui_mode`` setting (config / CODE_PUPPY_UI env / /ui command). Defaults off
(``classic``) until parity is reached.
"""

from .launcher import run_textual_ui

__all__ = ["run_textual_ui"]
