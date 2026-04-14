"""Tab-completion for ``/ollama-setup <model>``."""

from __future__ import annotations

from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from code_puppy.plugins.ollama_setup.register_callbacks import CLOUD_MODELS


class OllamaSetupCompleter(Completer):
    """Completes cloud model names after ``/ollama-setup ``."""

    trigger = "/ollama-setup"

    def get_completions(
        self, document: Document, complete_event: object
    ) -> Iterable[Completion]:
        text = document.text_before_cursor.lstrip()

        if not text.startswith(self.trigger + " "):
            return

        # Everything after "/ollama-setup "
        after = text[len(self.trigger) + 1 :]
        partial = after.strip().lower()
        start_pos = -len(after) if after else 0

        for tag, meta in CLOUD_MODELS.items():
            if not partial or tag.lower().startswith(partial):
                yield Completion(
                    tag,
                    start_position=start_pos,
                    display=tag,
                    display_meta=meta["description"],
                )
