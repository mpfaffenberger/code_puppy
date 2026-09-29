"""Prompt-toolkit completion for `/skills` subcommands.

Mirrors MCPCompleter but simpler: it only completes the subcommand name.
Skills are local-only, so completion never consults a provider or the network.
"""

from __future__ import annotations

from typing import Iterable

from termflow.tui.completion import Completer, Completion, Document


class SkillsCompleter(Completer):
    """Completer for /skills subcommands."""

    def __init__(self, trigger: str = "/skills"):
        """Initialize the skills completer.

        Args:
            trigger: The slash command prefix to trigger completion.
        """

        self.trigger = trigger
        self.subcommands = {
            "list": "List all installed skills",
            "enable": "Enable skills integration globally",
            "disable": "Disable skills integration globally",
            "toggle": "Toggle skills system on/off",
            "refresh": "Refresh skill cache",
            "help": "Show skills help",
        }

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        """Yield completions for /skills subcommands."""

        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /skills is at the very beginning of the line
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger):
            return

        # Find where /skills starts (after any leading whitespace)
        skills_pos = text_before_cursor.find(self.trigger)
        skills_end = skills_pos + len(self.trigger)

        # Require a space after /skills before showing completions
        if (
            skills_end >= len(text_before_cursor)
            or text_before_cursor[skills_end] != " "
        ):
            return

        # Everything after /skills (after the space)
        after_skills = text_before_cursor[skills_end + 1 :].strip()

        # If nothing after /skills, show all subcommands
        if not after_skills:
            for subcommand, description in sorted(self.subcommands.items()):
                yield Completion(
                    subcommand,
                    start_position=0,
                    display=subcommand,
                    display_meta=description,
                )
            return

        parts = after_skills.split()

        # If we only have one part and no trailing space, complete subcommands
        if len(parts) == 1 and not text.endswith(" "):
            partial = parts[0]
            for subcommand, description in sorted(self.subcommands.items()):
                if subcommand.startswith(partial):
                    yield Completion(
                        subcommand,
                        start_position=-(len(partial)),
                        display=subcommand,
                        display_meta=description,
                    )
            return

        # Otherwise, no further completion.
        return
