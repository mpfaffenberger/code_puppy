"""Prompt-toolkit completion for `/skills`.

Mirrors MCPCompleter but simpler:
- Completes subcommands for `/skills ...`
- For `/skills install ...`, completes skill ids from the remote catalog

This module is intentionally defensive: if the remote catalog isn't available,
completion simply returns no skill ids.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable, List

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

logger = logging.getLogger(__name__)


def load_catalog_skill_ids() -> List[str]:
    """Load skill ids from the remote catalog (lazy, cached)."""

    try:
        from code_puppy.plugins.agent_skills.skill_catalog import catalog

        return [entry.id for entry in catalog.get_all()]
    except Exception as e:
        logger.debug(f"Could not load skill ids: {e}")
        return []


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
            "install": "Browse & install from catalog",
            "enable": "Enable skills integration globally",
            "disable": "Disable skills integration globally",
            "toggle": "Toggle skills system on/off",
            "refresh": "Refresh skill cache",
            "help": "Show skills help",
        }

        self._skill_ids_cache: List[str] | None = None
        self._cache_timestamp: float | None = None

    def _get_skill_ids(self) -> List[str]:
        """Get skill ids with 30-second cache."""

        current_time = time.time()
        if (
            self._skill_ids_cache is None
            or self._cache_timestamp is None
            or current_time - self._cache_timestamp > 30
        ):
            self._skill_ids_cache = load_catalog_skill_ids()
            self._cache_timestamp = current_time

        return self._skill_ids_cache or []

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        """Yield completions for /skills subcommands and skill ids."""

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

        # Special-case: /skills install <skill-id>
        if len(parts) >= 1:
            subcommand = parts[0].lower()

            if subcommand == "install":
                # Case 1: exactly `install ` -> show all ids
                if len(parts) == 1 and text.endswith(" "):
                    for skill_id in sorted(self._get_skill_ids()):
                        yield Completion(
                            skill_id,
                            start_position=0,
                            display=skill_id,
                            display_meta="Skill",
                        )
                    return

                # Case 2: `install <partial>` -> filter ids
                if len(parts) == 2 and cursor_position > (
                    skills_end + 1 + len(subcommand) + 1
                ):
                    partial = parts[1]
                    start_position = -len(partial)
                    for skill_id in sorted(self._get_skill_ids()):
                        if skill_id.lower().startswith(partial.lower()):
                            yield Completion(
                                skill_id,
                                start_position=start_position,
                                display=skill_id,
                                display_meta="Skill",
                            )
                    return

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
