"""Plugins Code Puppy ships on top of pydantic-ai-pax's own.

Each entry is a pax plugin declaration. ``distribution`` appends them to
pax's built-in set, so ``/plugins`` lists them as shipped and
``/plugins remove`` restores their defaults.
"""

from __future__ import annotations

from pydantic_ai_pax.config import PluginSettings

from code_puppy import personality

CLAUDE_CODE_NO_UPDATE_CHECK = "CLAUDE_CODE_NO_UPDATE_CHECK"
"""Turns off the Claude Code plugin's own update notice.

The notice tells users to reinstall the plugin as a drop-in. Here it is a
dependency of Code Puppy, so it updates with Code Puppy instead.
"""

PUPPY_PLUGINS: tuple[PluginSettings, ...] = (
    # The main agent's name, tone and opinions. See `code_puppy.personality`.
    PluginSettings(id=personality.PLUGIN_ID, factory=personality.FACTORY),
    PluginSettings(
        id="legacy_plugins", factory="code_puppy.compat.bridge:LegacyPlugins"
    ),
    # Claude Code subscription models, from the `pydantic-claude-code` package.
    # Same id as that plugin's drop-in install, so a user's own copy replaces
    # this one instead of loading beside it.
    PluginSettings(
        id="claude_code", factory="pydantic_ai_claude_code.clai2:ClaudeCodePlugin"
    ),
)
