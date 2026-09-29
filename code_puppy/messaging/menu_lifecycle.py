"""Compatibility policy for legacy menus that still emit closing notices.

Menu navigation belongs on the alternate screen, never in the transcript.
Keep this list exact: broad 'cancelled'/'exited' matching would hide real
command results. New menus should simply return without emitting a notice.
"""

import re

from code_puppy.i18n import t

_LEGACY_CLOSE_NOTICES = frozenset(
    {
        "\u2713 Exited tutorial",
        "Exited custom server form",
        "Exited config settings menu",
        "Exited MCP server browser",
        "Exited UC tool browser",
        "Queue is empty",
        "\U0001f3a8 Theme unchanged.",
        "Exited skills install browser",
        "\u2713 Exited judges menu",
    }
)


def is_menu_close_notice(content: object) -> bool:
    return isinstance(content, str) and (
        content in _LEGACY_CLOSE_NOTICES
        or content == t("model_menu.browser.exited")
        or content == t("cmd.model_settings.agent_reloaded")
        or re.fullmatch(
            re.escape(t("cmd.model.success", model="__MODEL__")).replace(
                "__MODEL__", ".+"
            ),
            content,
        )
        is not None
        or re.fullmatch(r"\u23ed \d+ prompt\(s\) queued", content) is not None
    )
