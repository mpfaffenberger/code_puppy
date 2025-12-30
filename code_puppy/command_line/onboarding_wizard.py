"""Interactive TUI onboarding wizard for first-time Code Puppy users.

🐶 Welcome to Code Puppy! This wizard guides new users through initial setup,
model configuration, and feature discovery. Uses the same TUI patterns as
colors_menu.py and diff_menu.py for a consistent experience.

Usage:
    from code_puppy.command_line.onboarding_wizard import (
        should_show_onboarding,
        run_onboarding_wizard,
    )

    if should_show_onboarding():
        result = await run_onboarding_wizard()
        # result: "chatgpt", "claude", "completed", "skipped", or None
"""

import io
import os
import sys
import time
from typing import List, Optional, Tuple

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console

from code_puppy.config import CONFIG_DIR

from .onboarding_slides import (
    MODEL_OPTIONS,
    slide_agent_system,
    slide_api_keys,
    slide_appearance,
    slide_complete,
    slide_mcp_servers,
    slide_model_pinning,
    slide_model_settings,
    slide_model_subscription,
    slide_planning_agent,
    slide_welcome,
)

# ============================================================================
# State Tracking (like motd.py pattern)
# ============================================================================

ONBOARDING_COMPLETE_FILE = os.path.join(CONFIG_DIR, "onboarding_complete")


def has_completed_onboarding() -> bool:
    """Check if the user has already completed onboarding.

    Returns:
        True if onboarding has been completed, False otherwise.
    """
    return os.path.exists(ONBOARDING_COMPLETE_FILE)


def mark_onboarding_complete() -> None:
    """Mark onboarding as complete by creating the tracking file."""
    os.makedirs(os.path.dirname(ONBOARDING_COMPLETE_FILE), exist_ok=True)
    with open(ONBOARDING_COMPLETE_FILE, "w") as f:
        f.write("completed\n")


def should_show_onboarding() -> bool:
    """Determine if the onboarding wizard should be shown.

    Returns:
        True if onboarding should be shown, False otherwise.
    """
    return not has_completed_onboarding()


def reset_onboarding() -> None:
    """Reset onboarding state (useful for testing or re-running wizard)."""
    if os.path.exists(ONBOARDING_COMPLETE_FILE):
        os.remove(ONBOARDING_COMPLETE_FILE)


# ============================================================================
# Onboarding Wizard Class
# ============================================================================


class OnboardingWizard:
    """Interactive onboarding wizard with slide-based navigation.

    Attributes:
        current_slide: Index of the currently displayed slide (0-9)
        selected_option: Index of selected option within current slide
        trigger_oauth: OAuth provider to trigger after wizard ("chatgpt"/"claude")
        model_choice: User's model subscription selection
    """

    TOTAL_SLIDES = 10

    def __init__(self):
        """Initialize the onboarding wizard state."""
        self.current_slide = 0
        self.selected_option = 0
        self.trigger_oauth: Optional[str] = None
        self.model_choice: Optional[str] = None
        self.result: Optional[str] = None
        self._should_exit = False

    def get_progress_indicator(self) -> str:
        """Generate progress dots showing current slide position.

        Returns:
            String like "● ○ ○ ○ ○ ○ ○ ○ ○ ○" for slide 0.
        """
        dots = []
        for i in range(self.TOTAL_SLIDES):
            if i == self.current_slide:
                dots.append("●")
            else:
                dots.append("○")
        return " ".join(dots)

    def get_slide_content(self) -> str:
        """Get combined content for the current slide.

        Returns:
            Rich markup string for the slide content.
        """
        if self.current_slide == 0:
            return slide_welcome()
        elif self.current_slide == 1:
            options = self.get_options_for_slide()
            return slide_model_subscription(self.selected_option, options)
        elif self.current_slide == 2:
            return slide_api_keys(self.model_choice)
        elif self.current_slide == 3:
            return slide_mcp_servers()
        elif self.current_slide == 4:
            return slide_appearance()
        elif self.current_slide == 5:
            return slide_agent_system()
        elif self.current_slide == 6:
            return slide_model_pinning()
        elif self.current_slide == 7:
            return slide_planning_agent()
        elif self.current_slide == 8:
            return slide_model_settings()
        else:  # slide 9
            return slide_complete(self.trigger_oauth)

    def get_options_for_slide(self) -> List[Tuple[str, str]]:
        """Get selectable options for the current slide.

        Returns:
            List of (id, label) tuples for options, or empty list if no options.
        """
        if self.current_slide == 1:  # Model subscription slide
            return [(opt[0], opt[1]) for opt in MODEL_OPTIONS]
        return []

    def handle_option_select(self) -> None:
        """Handle selection of the current option."""
        if self.current_slide == 1:  # Model subscription
            options = self.get_options_for_slide()
            if 0 <= self.selected_option < len(options):
                choice_id = options[self.selected_option][0]
                self.model_choice = choice_id

                # Set OAuth trigger for ChatGPT/Claude
                if choice_id == "chatgpt":
                    self.trigger_oauth = "chatgpt"
                elif choice_id == "claude":
                    self.trigger_oauth = "claude"

    def next_slide(self) -> bool:
        """Move to the next slide.

        Returns:
            True if moved to next slide, False if at last slide.
        """
        if self.current_slide < self.TOTAL_SLIDES - 1:
            self.current_slide += 1
            self.selected_option = 0
            return True
        return False

    def prev_slide(self) -> bool:
        """Move to the previous slide.

        Returns:
            True if moved to previous slide, False if at first slide.
        """
        if self.current_slide > 0:
            self.current_slide -= 1
            self.selected_option = 0
            return True
        return False

    def next_option(self) -> None:
        """Move to the next option within the current slide."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option + 1) % len(options)

    def prev_option(self) -> None:
        """Move to the previous option within the current slide."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option - 1) % len(options)


# ============================================================================
# TUI Rendering Functions
# ============================================================================


def _get_slide_panel_content(wizard: OnboardingWizard) -> ANSI:
    """Generate the centered slide content.

    Args:
        wizard: The OnboardingWizard instance.

    Returns:
        ANSI object with formatted slide content.
    """
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        width=80,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Progress indicator
    progress = wizard.get_progress_indicator()
    console.print(f"[dim]{progress}[/dim]\n")

    # Slide number
    console.print(
        f"[dim]Slide {wizard.current_slide + 1} of {wizard.TOTAL_SLIDES}[/dim]\n\n"
    )

    # Combined slide content
    slide_content = wizard.get_slide_content()
    console.print(slide_content)

    return ANSI(buffer.getvalue())


def _get_navigation_hints(wizard: OnboardingWizard) -> FormattedText:
    """Generate navigation hints for the bottom of the screen.

    Args:
        wizard: The OnboardingWizard instance.

    Returns:
        FormattedText with navigation hints.
    """
    hints = []

    if wizard.current_slide > 0:
        hints.append(("fg:ansicyan", "← Back  "))

    if wizard.current_slide < wizard.TOTAL_SLIDES - 1:
        hints.append(("fg:ansicyan", "→ Next  "))
    else:
        hints.append(("fg:ansigreen bold", "Enter: Finish  "))

    options = wizard.get_options_for_slide()
    if options:
        hints.append(("fg:ansicyan", "↑↓ Options  "))

    hints.append(("fg:ansiyellow", "ESC: Skip"))

    return FormattedText(hints)


# ============================================================================
# Main Entry Point
# ============================================================================


async def run_onboarding_wizard() -> Optional[str]:
    """Run the interactive onboarding wizard.

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

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.1)  # Minimal delay for state sync

    try:
        # Set up key bindings
        kb = KeyBindings()

        @kb.add("right")
        @kb.add("l")
        def next_slide(event):
            if wizard.current_slide == wizard.TOTAL_SLIDES - 1:
                # On last slide, right arrow finishes
                wizard.result = "completed"
                wizard._should_exit = True
                event.app.exit()
            else:
                wizard.next_slide()
            event.app.invalidate()

        @kb.add("left")
        @kb.add("h")
        def prev_slide(event):
            wizard.prev_slide()
            event.app.invalidate()

        @kb.add("down")
        @kb.add("j")
        def next_option(event):
            wizard.next_option()
            event.app.invalidate()

        @kb.add("up")
        @kb.add("k")
        def prev_option(event):
            wizard.prev_option()
            event.app.invalidate()

        @kb.add("enter")
        def select_or_next(event):
            # Handle option selection on slides with options
            options = wizard.get_options_for_slide()
            if options:
                wizard.handle_option_select()

            # Move to next slide or finish
            if wizard.current_slide == wizard.TOTAL_SLIDES - 1:
                wizard.result = "completed"
                wizard._should_exit = True
                event.app.exit()
            else:
                wizard.next_slide()
            event.app.invalidate()

        @kb.add("escape")
        def skip_wizard(event):
            wizard.result = "skipped"
            wizard._should_exit = True
            event.app.exit()

        @kb.add("c-c")
        def cancel_wizard(event):
            wizard.result = "skipped"
            wizard._should_exit = True
            event.app.exit()

        # Create layout with single centered panel
        slide_panel = Window(
            content=FormattedTextControl(lambda: _get_slide_panel_content(wizard))
        )

        root_container = Frame(slide_panel, title="🐶 Welcome to Code Puppy!")

        layout = Layout(root_container)

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
            color_depth="DEPTH_24_BIT",
        )

        # Clear screen before running
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        # Run the application
        await app.run_async()

    except KeyboardInterrupt:
        wizard.result = "skipped"
    except Exception:
        wizard.result = None
    finally:
        set_awaiting_user_input(False)
        # Exit alternate screen buffer
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    # Mark onboarding as complete (even if skipped - they saw it)
    if wizard.result in ("completed", "skipped"):
        mark_onboarding_complete()

    # Return OAuth trigger if selected, otherwise the result
    if wizard.trigger_oauth:
        return wizard.trigger_oauth

    return wizard.result


async def run_onboarding_if_needed() -> Optional[str]:
    """Run onboarding wizard if user hasn't completed it yet.

    Returns:
        Result from run_onboarding_wizard() or None if not needed.
    """
    if should_show_onboarding():
        return await run_onboarding_wizard()
    return None
