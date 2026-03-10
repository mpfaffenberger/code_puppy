"""
Tab-completion for the /profile command.

Provides context-aware completions:
  /profile               → subcommands + agent role shortcuts
  /profile set           → agent role names (compaction, subagent, …)
  /profile set <role>    → model names with provider hints
  /profile reset         → agent role names
  /profile load|delete   → saved profile names
"""

from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# ── Agent roles that can be configured ────────────────────────────────────────
# These match Task enum member names (lowercase) from task_models.py,
# excluding MAIN (the global default which isn't set through /profile).
AGENT_ROLES: dict[str, str] = {
    "compaction": "Summarization / context-compaction model",
    "subagent": "Sub-agent dispatch model",
}

# ── /profile subcommands ───────────────────────────────────────────────────────
PROFILE_SUBCOMMANDS: dict[str, str] = {
    "set": "Set model for an agent role",
    "reset": "Reset an agent role to its default",
    "save": "Save current config as a named profile",
    "load": "Load a named profile",
    "list": "List all saved profiles",
    "delete": "Delete a named profile",
    "guide": "Show configuration reference",
}


# ── Lazy data loaders (never raise) ───────────────────────────────────────────


def _load_profile_names() -> list[str]:
    try:
        from code_puppy.task_models import list_profiles

        return [p["name"] for p in list_profiles()]
    except Exception:
        return []


def _load_model_names() -> list[str]:
    try:
        from code_puppy.command_line.model_picker_completion import load_model_names

        return load_model_names()
    except Exception:
        return []


def _model_provider_hint(model_name: str) -> str:
    """Short provider label derived from the model name."""
    lower = model_name.lower()
    if (
        model_name.startswith("openai:")
        or "gpt" in lower
        or "o1" in lower
        or "o3" in lower
    ):
        return "OpenAI"
    if model_name.startswith("anthropic:") or "claude" in lower:
        return "Anthropic"
    if model_name.startswith("google-gla:") or "gemini" in lower:
        return "Google"
    if model_name.startswith("groq:") or "llama" in lower or "mixtral" in lower:
        return "Groq"
    if model_name.startswith("mistral:"):
        return "Mistral"
    if model_name.startswith("cerebras:") or "cerebras" in lower or "glm" in lower:
        return "Cerebras"
    if model_name.startswith("xai:") or "grok" in lower:
        return "xAI"
    if ":" in model_name:
        return model_name.split(":", 1)[0].title()
    return "model"


# ── Completer ─────────────────────────────────────────────────────────────────


class ProfileCompleter(Completer):
    """
    Context-aware tab-completion for ``/profile``.

    Plugs into the prompt_toolkit completion pipeline alongside the existing
    SlashCommandCompleter and ModelNameCompleter.
    """

    TRIGGER = "/profile"

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        stripped = text.lstrip()

        if not stripped.startswith(self.TRIGGER):
            return

        # Slice off everything before and including "/profile"
        trigger_pos = text.find(self.TRIGGER)
        after = text[trigger_pos + len(self.TRIGGER) :]

        # Nothing typed yet (cursor right after "/profile") — don't complete
        if not after:
            return

        tokens = after.split()
        ends_with_space = after.endswith(" ")

        # ── /profile <partial>  →  subcommands + role shortcuts ───────────────
        if len(tokens) == 0 or (len(tokens) == 1 and not ends_with_space):
            partial = tokens[0] if tokens else ""
            # Agent role shortcuts (e.g. /profile compaction gpt-4o)
            for name, meta in AGENT_ROLES.items():
                if name.startswith(partial):
                    yield Completion(
                        name,
                        start_position=-len(partial),
                        display_meta=meta,
                    )
            # Subcommands
            for name, meta in PROFILE_SUBCOMMANDS.items():
                if name.startswith(partial):
                    yield Completion(
                        name,
                        start_position=-len(partial),
                        display_meta=meta,
                    )
            return

        sub = tokens[0]

        # ── /profile set … ────────────────────────────────────────────────────
        if sub == "set":
            if len(tokens) == 1 and ends_with_space:
                # /profile set <TAB>  → agent roles
                for name, meta in AGENT_ROLES.items():
                    yield Completion(name, display_meta=meta)

            elif len(tokens) == 2 and not ends_with_space:
                # /profile set comp<TAB>
                partial = tokens[1]
                for name, meta in AGENT_ROLES.items():
                    if name.startswith(partial):
                        yield Completion(
                            name,
                            start_position=-len(partial),
                            display_meta=meta,
                        )

            elif (len(tokens) == 2 and ends_with_space) or (
                len(tokens) == 3 and not ends_with_space
            ):
                # /profile set compaction <TAB|partial>  → model names
                partial = tokens[2] if len(tokens) == 3 else ""
                yield from _model_completions(partial)

            return

        # ── /profile <role> …  (shorthand: /profile compaction gpt-4o) ───────
        if sub in AGENT_ROLES:
            if len(tokens) == 1 and ends_with_space:
                yield from _model_completions("")
            elif len(tokens) == 2 and not ends_with_space:
                yield from _model_completions(tokens[1])
            return

        # ── /profile reset <TAB|partial>  → agent roles ───────────────────────
        if sub == "reset":
            if len(tokens) == 1 and ends_with_space:
                for name, meta in AGENT_ROLES.items():
                    yield Completion(name, display_meta=meta)
            elif len(tokens) == 2 and not ends_with_space:
                partial = tokens[1]
                for name, meta in AGENT_ROLES.items():
                    if name.startswith(partial):
                        yield Completion(
                            name,
                            start_position=-len(partial),
                            display_meta=meta,
                        )
            return

        # ── /profile load|delete <TAB|partial>  → saved profile names ─────────
        if sub in ("load", "delete"):
            profiles = _load_profile_names()
            if len(tokens) == 1 and ends_with_space:
                for name in profiles:
                    yield Completion(name, display_meta="saved profile")
            elif len(tokens) == 2 and not ends_with_space:
                partial = tokens[1]
                for name in profiles:
                    if name.startswith(partial):
                        yield Completion(
                            name,
                            start_position=-len(partial),
                            display_meta="saved profile",
                        )


def _model_completions(partial: str) -> Iterable[Completion]:
    """Yield model name completions filtered by *partial*, with provider hints."""
    models = _load_model_names()
    partial_lower = partial.lower()
    for model in models:
        model_lower = model.lower()
        if (
            not partial
            or model_lower.startswith(partial_lower)
            or partial_lower in model_lower
        ):
            yield Completion(
                model,
                start_position=-len(partial),
                display_meta=_model_provider_hint(model),
            )
