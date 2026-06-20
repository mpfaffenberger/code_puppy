"""Show the active mode in Mist's default prompt."""

from __future__ import annotations

_PATCH_ATTR = "_agent_modes_original_prompt_fn"


def install_prompt_patch() -> None:
    from prompt_toolkit.formatted_text import FormattedText, to_formatted_text

    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return
    original = ptc.get_prompt_with_active_model
    setattr(ptc, _PATCH_ATTR, original)

    def patched(base: str = ">>> "):
        from .state import get_agent_mode

        fragments = list(to_formatted_text(original(base)))
        arrow_index = next(
            (index for index, item in enumerate(fragments) if item[0] == "class:arrow"),
            len(fragments),
        )
        fragments.insert(
            arrow_index,
            ("class:agent", f"[{get_agent_mode().value.upper()}] "),
        )
        return FormattedText(fragments)

    ptc.get_prompt_with_active_model = patched
