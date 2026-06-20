"""Cache-aware system prompt composition.

The marker is intentionally an HTML comment: providers that do not expose
structured system blocks receive a harmless separator, while Anthropic wire
adapters split it into independently cacheable content blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

DYNAMIC_PROMPT_BOUNDARY = "<!-- mist:dynamic-context -->"


@dataclass(frozen=True)
class PromptSections:
    """Stable and volatile portions of an agent system prompt."""

    static: str
    dynamic: str = ""

    def render(self) -> str:
        static = self.static.rstrip()
        dynamic = self.dynamic.strip()
        if not dynamic:
            return static
        return f"{static}\n\n{DYNAMIC_PROMPT_BOUNDARY}\n\n{dynamic}"


def split_prompt_sections(prompt: str) -> PromptSections:
    """Split a rendered prompt, treating legacy prompts as entirely stable."""
    if DYNAMIC_PROMPT_BOUNDARY not in prompt:
        return PromptSections(static=prompt)
    static, dynamic = prompt.split(DYNAMIC_PROMPT_BOUNDARY, 1)
    return PromptSections(static=static.rstrip(), dynamic=dynamic.lstrip())
