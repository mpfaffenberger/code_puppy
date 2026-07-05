"""User-facing startup notice for project plugins held back by the trust gate.

Kept separate from the loader (``plugins/__init__``) and the trust store
(``plugins/trust``) — this is presentation, they are policy.

Called from plugin_list's ``startup`` callback, which fires AFTER the
renderers are live — so the banner prints inline with the version/help
startup text. Do NOT emit this at plugin-load (import) time: the legacy
message queue buffers pre-renderer emits and never replays them.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Match the renderer's standard WARNING style (_classify_style -> "yellow")
# so the banner reads as one of the family; bold spans give it the pop.
_STYLE = "yellow"
_STYLE_BOLD = "bold yellow"

_REASONS = {
    "untrusted": "never enabled",
    "changed": "changed since you accepted it",
}


def emit_skipped_plugin_notice(statuses: dict[str, str]) -> None:
    """Emit one orange banner listing project plugins that were NOT loaded.

    *statuses* is the full ``get_project_plugin_status()`` map; only
    ``untrusted``/``changed`` entries need the user's attention (``disabled``
    was their own choice, ``loaded``/``error`` are handled elsewhere).
    Never raises — a broken banner must not break startup (rule 4).
    """
    skipped = {n: s for n, s in statuses.items() if s in _REASONS}
    if not skipped:
        return
    try:
        from rich.text import Text

        from code_puppy.messaging import emit_warning

        text = Text()
        text.append(
            "Project plugins found but NOT loaded (disabled by default):\n",
            style=_STYLE_BOLD,
        )
        # Name the project explicitly — trust is scoped per project path,
        # so "which project am I in?" must never be a guessing game.
        from code_puppy.plugins import get_project_plugins_directory

        project_dir = get_project_plugins_directory()
        if project_dir is not None:
            text.append(f"  in {project_dir.as_posix()}\n", style=_STYLE)
        for name, status in sorted(skipped.items()):
            reason = _REASONS.get(status, status)
            text.append(f"  - {name}  ({reason})\n", style=_STYLE)
        text.append("Review and enable in ", style=_STYLE)
        text.append("/plugins", style=_STYLE_BOLD)
        text.append(
            " (select the plugin, press Enter) -- project plugins run "
            "arbitrary code; only enable ones you trust.",
            style=_STYLE,
        )
        emit_warning(text)
    except Exception as exc:
        logger.debug(f"Could not emit skipped-plugin notice: {exc}")
