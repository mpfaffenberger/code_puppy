"""Monkey-patch ``get_prompt_with_active_model`` to render the status line.

Same proven seam the ``context_indicator`` plugin uses. The status command's
stdout may contain ANSI color codes, so we convert it to prompt_toolkit
``FormattedText`` via ``ANSI``.

Three modes (config ``statusline_mode``):

* ``replace`` (default): the custom status line **replaces** Code Puppy's
  default prompt content (puppy/agent/model/cwd), keeping only the trailing
  arrow. No duplicated info, no extra stacked line.
* ``above``: the custom status line is shown on its own line *above* the
  unchanged default prompt.
* ``newline``: like ``replace`` but the trailing arrow is pushed to its own
  line, so the user types below the status line::

       [model] code-puppy (main) 0.9%ctx
      >>> typed text
"""

from __future__ import annotations

import logging

from .config import get_mode
from .runner import get_status_text

logger = logging.getLogger(__name__)

_PATCH_ATTR = "_statusline_original_prompt_fn"
_DEFAULT_ARROW = ">>> "


def _render(formatted_text, base: str):
    from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text

    text = get_status_text()
    if not text:
        return formatted_text

    try:
        status_fragments = list(to_formatted_text(ANSI(text)))
    except Exception:
        logger.debug("statusline: failed to parse status text", exc_info=True)
        return formatted_text

    mode = get_mode()

    if mode == "above":
        # Status line on its own line, default prompt unchanged below it.
        return FormattedText(status_fragments + [("", "\n")] + list(formatted_text))

    if mode == "newline":
        # Status line on its own line, arrow on the next line.
        arrow = base if base else _DEFAULT_ARROW
        return FormattedText(status_fragments + [("", "\n"), ("class:arrow", arrow)])

    # replace mode (default): status line + trailing arrow on same line.
    arrow = base if base else _DEFAULT_ARROW
    return FormattedText(status_fragments + [("class:arrow", " " + arrow)])


def install_prompt_patch() -> None:
    """Wrap ``get_prompt_with_active_model`` exactly once."""
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return  # already patched

    original = ptc.get_prompt_with_active_model
    setattr(ptc, _PATCH_ATTR, original)

    def patched(base: str = ">>> "):
        return _render(original(base), base)

    ptc.get_prompt_with_active_model = patched
