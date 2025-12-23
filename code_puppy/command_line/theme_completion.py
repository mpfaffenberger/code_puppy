"""Tab completion for /theme command.

Provides intelligent tab completion for theme subcommands and theme names.
"""

from typing import Iterable

from prompt_toolkit.completion import Completer, Completion

from code_puppy.theming import get_available_themes


class ThemeCompleter(Completer):
    """Provides tab completion for theme commands.

    Handles completion for:
    - Theme subcommands: list, set, current, reset
    - Theme names for the 'set' subcommand
    """

    def __init__(self, trigger: str = "/theme"):
        """Initialize the theme completer.

        Args:
            trigger: The command prefix that triggers this completer.
        """
        self.trigger = trigger

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor

        # Only complete for /theme commands
        if not text.startswith(self.trigger):
            return []

        trigger_with_space = self.trigger + " "
        trigger_len = len(self.trigger)

        # Handle subcommands
        if text == self.trigger or text == trigger_with_space:
            # Suggest subcommands
            subcommands = ["list", "set", "current", "reset"]
            for cmd in subcommands:
                yield Completion(cmd, display=cmd, display_meta=f"{self.trigger} {cmd}")

        elif text.startswith(trigger_with_space):
            remaining = text[trigger_len + 1 :]  # After trigger + space

            # No space yet - completing subcommands
            if " " not in remaining:
                subcommands = ["list", "set", "current", "reset"]
                for cmd in subcommands:
                    if cmd.startswith(remaining):
                        yield Completion(
                            cmd,
                            display=cmd,
                            display_meta=f"{self.trigger} {cmd}",
                            start_position=-len(remaining),
                        )

            # Space present - handle subcommand-specific completion
            elif remaining.startswith("set "):
                # Complete theme names after "set "
                theme_part = remaining[4:]  # After "set "
                available_themes = get_available_themes()

                for theme_name in available_themes:
                    if theme_name.startswith(theme_part):
                        yield Completion(
                            theme_name,
                            display=theme_name,
                            display_meta=f"Theme: {theme_name}",
                            start_position=-len(theme_part),
                        )
            # No completion needed for other subcommands
