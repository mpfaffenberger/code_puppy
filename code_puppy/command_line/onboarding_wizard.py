"""Interactive TUI onboarding wizard for first-time Code Puppy users.

🐶 Quick 5-slide tutorial. ADHD-friendly!

Usage:
    from code_puppy.command_line.onboarding_wizard import (
        run_onboarding_wizard,
        reset_onboarding,
    )

    result = await run_onboarding_wizard()
    # result: "chatgpt", "claude", "completed", "skipped", or None
"""

import asyncio
import os
from typing import Callable, List, Optional, TextIO, Tuple

from code_puppy.config import CONFIG_DIR

from .onboarding_slides import (
    MODEL_OPTIONS,
    SlideContent,
    slide_done,
    slide_mcp,
    slide_models,
    slide_use_cases,
    slide_welcome,
)

# ============================================================================
# State Tracking
# ============================================================================

ONBOARDING_COMPLETE_FILE = os.path.join(CONFIG_DIR, "onboarding_complete")


def has_completed_onboarding() -> bool:
    """Check if the user has already completed onboarding."""
    return os.path.exists(ONBOARDING_COMPLETE_FILE)


def mark_onboarding_complete() -> None:
    """Mark onboarding as complete."""
    os.makedirs(os.path.dirname(ONBOARDING_COMPLETE_FILE), exist_ok=True)
    with open(ONBOARDING_COMPLETE_FILE, "w") as f:
        f.write("completed\n")


def should_show_onboarding() -> bool:
    """Determine if the onboarding wizard should be shown.

    Returns False if:
    - User has already completed onboarding
    - CODE_PUPPY_SKIP_TUTORIAL env var is set to '1' or 'true'
    """
    # Allow skipping tutorial via environment variable (useful for testing)
    skip_env = os.environ.get("CODE_PUPPY_SKIP_TUTORIAL", "").lower()
    if skip_env in ("1", "true", "yes"):
        return False
    return not has_completed_onboarding()


def reset_onboarding() -> None:
    """Reset onboarding state (for re-running with /tutorial)."""
    if os.path.exists(ONBOARDING_COMPLETE_FILE):
        os.remove(ONBOARDING_COMPLETE_FILE)


# ============================================================================
# Onboarding Wizard Class
# ============================================================================


class OnboardingWizard:
    """5-slide interactive tutorial.

    Slides:
        0: Welcome
        1: Model selection
        2: MCP servers
        3: Use cases (Planning vs Coding)
        4: Done!
    """

    TOTAL_SLIDES = 5

    def __init__(self):
        """Initialize wizard state."""
        self.current_slide = 0
        self.selected_option = 0
        self.trigger_oauth: Optional[str] = None
        self.model_choice: Optional[str] = None
        self.result: Optional[str] = None
        self._should_exit = False

    def get_progress_indicator(self) -> str:
        """Progress dots: ● ○ ○ ○ ○"""
        return " ".join(
            "●" if i == self.current_slide else "○" for i in range(self.TOTAL_SLIDES)
        )

    def get_slide_content(self) -> SlideContent:
        """Get content for current slide."""
        if self.current_slide == 0:
            return slide_welcome()
        elif self.current_slide == 1:
            options = self.get_options_for_slide()
            return slide_models(self.selected_option, options)
        elif self.current_slide == 2:
            return slide_mcp()
        elif self.current_slide == 3:
            return slide_use_cases()
        else:  # slide 4
            return slide_done(self.trigger_oauth)

    def get_options_for_slide(self) -> List[Tuple[str, str]]:
        """Get selectable options for current slide."""
        if self.current_slide == 1:  # Model selection
            return [(opt[0], opt[1]) for opt in MODEL_OPTIONS]
        return []

    def handle_option_select(self) -> None:
        """Handle option selection."""
        if self.current_slide == 1:  # Model selection
            options = self.get_options_for_slide()
            if 0 <= self.selected_option < len(options):
                choice_id = options[self.selected_option][0]
                self.model_choice = choice_id
                if choice_id == "chatgpt":
                    self.trigger_oauth = "chatgpt"
                elif choice_id == "claude":
                    self.trigger_oauth = "claude"

    def next_slide(self) -> bool:
        """Move to next slide."""
        if self.current_slide < self.TOTAL_SLIDES - 1:
            self.current_slide += 1
            self.selected_option = 0
            return True
        return False

    def prev_slide(self) -> bool:
        """Move to previous slide."""
        if self.current_slide > 0:
            self.current_slide -= 1
            self.selected_option = 0
            return True
        return False

    def next_option(self) -> None:
        """Move to next option."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option + 1) % len(options)

    def prev_option(self) -> None:
        """Move to previous option."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option - 1) % len(options)


# ============================================================================
# TUI Rendering (termflow)
# ============================================================================


def _sgr_for(style_class: str) -> tuple[str, str]:
    """Map a semantic ``class:tui.*`` name to (SGR prefix, SGR suffix)."""
    from termflow.ansi.codes import BOLD_ON, DIM_ON, RESET
    from termflow.ansi.color import fg_color
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    s = menu_style() or RenderStyle.default()
    name = style_class.removeprefix("class:tui.")
    mapping = {
        "title": f"{fg_color(s.bright)}{BOLD_ON}",
        "header": f"{fg_color(s.bright)}{BOLD_ON}",
        "selected": f"{fg_color(s.head)}{BOLD_ON}",
        "success": fg_color(s.head),
        "warning": fg_color(s.error),
        "muted": f"{fg_color(s.grey)}{DIM_ON}",
        "help": f"{fg_color(s.grey)}{DIM_ON}",
        "help-key": f"{fg_color(s.head)}{BOLD_ON}",
    }
    prefix = mapping.get(name, "")
    return (prefix, RESET if prefix else "")


def _get_slide_panel_content(wizard: OnboardingWizard) -> SlideContent:
    """Generate semantically styled slide content for display."""
    progress = wizard.get_progress_indicator()
    content: SlideContent = [
        ("class:tui.muted", f"{progress}\n"),
        (
            "class:tui.muted",
            f"Slide {wizard.current_slide + 1} of {wizard.TOTAL_SLIDES}\n\n",
        ),
    ]
    content.extend(wizard.get_slide_content())
    return content


def _fragments_to_lines(fragments: SlideContent) -> list[str]:
    """Flatten (style, text) fragments into per-line ANSI strings.

    Each fragment is colored piecewise per line so styling never bleeds
    across the newline boundaries that repaints rely on.
    """
    lines: list[str] = [""]
    for style_class, text in fragments:
        prefix, suffix = _sgr_for(style_class)
        for i, part in enumerate(text.split("\n")):
            if i:
                lines.append("")
            if part:
                lines[-1] += f"{prefix}{part}{suffix}"
    return lines


class OnboardingTUI:
    """Slide-deck widget on termflow primitives (headless-testable)."""

    def __init__(
        self,
        wizard: OnboardingWizard,
        *,
        key_source: Optional[Callable[[], str]] = None,
        output: Optional[TextIO] = None,
        size: Optional[Callable[[], tuple[int, int]]] = None,
        use_alt_screen: bool = True,
    ) -> None:
        import sys

        from termflow.tui.keys import read_key
        from termflow.tui.menu import RESIZE_POLL_S
        from termflow.tui.terminal import terminal_size

        self._wizard = wizard
        self._read_key = key_source or (lambda: read_key(timeout=RESIZE_POLL_S))
        self._output = output if output is not None else sys.__stdout__
        self._size = size or terminal_size
        self._use_alt_screen = use_alt_screen

    def _paint(self) -> None:
        from termflow.ansi.codes import BOLD_ON, RESET
        from termflow.ansi.color import fg_color
        from termflow.render.style import RenderStyle
        from termflow.tui.layout import truncate

        from code_puppy.command_line.tui_style import menu_style

        width, height = self._size()
        width = max(10, width - 1)
        s = menu_style() or RenderStyle.default()
        lines = [
            f"{fg_color(s.bright)}{BOLD_ON}Code Puppy Tutorial{RESET}",
            "",
            *_fragments_to_lines(_get_slide_panel_content(self._wizard)),
        ]
        frame = [truncate(line, width) for line in lines[: max(1, height)]]
        payload = "\x1b[H" + "".join(f"{line}\x1b[K\r\n" for line in frame) + "\x1b[J"
        self._output.write(payload)
        self._output.flush()

    def _advance_or_complete(self) -> bool:
        """Shared Enter/right behavior. True when the wizard is done."""
        wizard = self._wizard
        if wizard.current_slide == wizard.TOTAL_SLIDES - 1:
            wizard.result = "completed"
            return True
        wizard.next_slide()
        return False

    def _handle_key(self, key: str) -> bool:
        """Dispatch one key. True exits the loop."""
        from termflow.tui.keys import Key

        wizard = self._wizard
        if key in (Key.ESCAPE, "ctrl-c"):
            wizard.result = "skipped"
            return True
        if key in (Key.RIGHT, "l"):
            return self._advance_or_complete()
        if key in (Key.LEFT, "h"):
            wizard.prev_slide()
        elif key in (Key.DOWN, "j", "ctrl-n"):
            wizard.next_option()
        elif key in (Key.UP, "k", "ctrl-p"):
            wizard.prev_option()
        elif key == Key.ENTER:
            if wizard.get_options_for_slide():
                wizard.handle_option_select()
            return self._advance_or_complete()
        return False

    def _loop(self) -> None:
        self._paint()
        last_size = self._size()
        while True:
            key = self._read_key()
            if key == "":
                size = self._size()
                if size != last_size:
                    last_size = size
                    self._paint()
                continue
            if self._handle_key(key):
                return
            self._paint()

    def run(self) -> None:
        """Run the wizard TUI; mutates the wizard's result state."""
        if self._use_alt_screen:
            from termflow.tui.terminal import alt_screen, raw_mode

            with raw_mode(), alt_screen(self._output):
                self._loop()
        else:
            self._loop()


# ============================================================================
# Main Entry Point
# ============================================================================


async def run_onboarding_wizard() -> Optional[str]:
    """Run the interactive tutorial.

    Returns:
        - "chatgpt" if user wants ChatGPT OAuth
        - "claude" if user wants Claude OAuth
        - "completed" if finished normally
        - "skipped" if user pressed ESC
        - None on error
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    wizard = OnboardingWizard()
    set_awaiting_user_input(True)

    try:
        # The widget owns raw mode + the alt screen; run it off-loop so
        # the blocking key reads never stall the event loop.
        await asyncio.to_thread(OnboardingTUI(wizard).run)
    except KeyboardInterrupt:
        wizard.result = "skipped"
    except Exception:
        wizard.result = None
    finally:
        set_awaiting_user_input(False)

    # Clear exit message
    from code_puppy.messaging import emit_info

    if wizard.result == "skipped":
        emit_info("✓ Tutorial skipped")
    elif wizard.result == "completed":
        emit_info("✓ Tutorial completed! Welcome to Code Puppy! 🐶")
    else:
        emit_info("✓ Exited tutorial")

    if wizard.result in ("completed", "skipped"):
        mark_onboarding_complete()

    if wizard.trigger_oauth:
        return wizard.trigger_oauth

    return wizard.result


async def run_onboarding_if_needed() -> Optional[str]:
    """Run tutorial if user hasn't seen it yet."""
    if should_show_onboarding():
        return await run_onboarding_wizard()
    return None


def require_model_setup_if_needed(wizard_result: Optional[str]) -> None:
    """Require an explicit model choice when the user skipped OAuth.

    Claude Code and ChatGPT OAuth flows set a model for you. For every other
    path (API keys, OpenRouter, "skip for now", or a plain completed/skipped
    tutorial) there is no bundled default model anymore, so the user *must*
    run ``/add_model`` before they can do anything useful. Surface a loud,
    unmissable instruction instead of letting them hit a silent [None] model.
    """
    # OAuth paths already wired up a model - nothing to nag about.
    if wizard_result in ("chatgpt", "claude"):
        return

    from code_puppy import config as cp_config
    from code_puppy.messaging import emit_warning

    # Pre-arm the generic "no model" warning before resolving, so it doesn't
    # double up with our more specific tutorial message (harmless if a model
    # is configured).
    cp_config._warned_no_model = True

    # If a model somehow is already configured, don't be annoying.
    if cp_config.get_global_model_name():
        return

    emit_warning(
        "\U0001f6a8 No model configured yet!\n"
        "   Code Puppy ships with an empty model list, so you need to add one:\n"
        "   \u2022 Run /add_model to browse + add a model (API key required), or\n"
        "   \u2022 Run /tutorial again and pick Claude Code or ChatGPT OAuth."
    )
