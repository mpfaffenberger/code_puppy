"""Entry point: registers all hooks for the namespace_skill_search plugin.

Three hooks:

1. `startup`        -> one-time migration that turns off the built-in flat
                       skill list (see `_maybe_disable_frontmatter` below).
2. `load_prompt`    -> injects the compact namespace directory (a few lines
                       per namespace instead of one line per skill).
                       Fragments from every plugin are simply
                       newline-joined by base_agent.py, so this coexists
                       safely with any other plugin's fragment.
3. `register_tools` -> adds `browse_skill_namespace` as a real tool, wired
                       to every agent automatically via
                       `register_agent_tools`.

We deliberately do NOT touch `get_model_system_prompt` (that's where the
built-in flat skill list gets injected, and where a *second* callback on
that same phase would silently clobber the first one's output — see
`model_utils.prepare_prompt_for_model`: augmenter results are threaded
through sequentially and the *last* one processed wins on any key they
both set). Instead we turn the flat list off via the public config API
and let our `load_prompt` fragment be the only skills-summary content in
the prompt.
"""

import logging

from code_puppy.callbacks import register_callback
from code_puppy.config import get_value, set_config_value
from code_puppy.plugins.agent_skills.config import (
    get_frontmatter_in_system_prompt,
    set_frontmatter_in_system_prompt,
)

from .namespaces import build_namespace_summary
from .search_tool import register_browse_skill_namespace

logger = logging.getLogger(__name__)

# Own marker distinguishes this plugin's one-time migration from a user's later
# `/skills frontmatter on`; flip the shared flag once, then never override it.
_MIGRATION_MARKER_KEY = "namespace_skill_search_frontmatter_migrated"


def _maybe_disable_frontmatter() -> None:
    """One-time migration: turn off the built-in flat per-skill list.

    Runs on the `startup` callback (not at import time) so it is:
    - testable in isolation (call this function directly with mocked
      config, same pattern as `theme._apply_default_theme_on_first_run`);
    - not repeated on every module import (`startup` callbacks fire once
      per process, same as any other plugin);
    - a single, auditable point of config mutation rather than an
      import-time side effect.

    Only ever flips the shared `frontmatter_in_system_prompt` flag from
    True -> False, and only the first time this plugin ever starts up. A
    user who runs `/skills frontmatter on` afterwards keeps that choice
    forever — the marker means we never re-evaluate `get_value` for this
    decision again.
    """
    if get_value(_MIGRATION_MARKER_KEY):
        return

    if get_frontmatter_in_system_prompt():
        set_frontmatter_in_system_prompt(False)
        logger.info(
            "namespace_skill_search: disabled flat skill-list frontmatter "
            "(one-time migration); namespace directory + "
            "browse_skill_namespace tool take over. Run `/skills "
            "frontmatter on` to restore the flat list."
        )

    set_config_value(_MIGRATION_MARKER_KEY, "true")


def _on_load_prompt():
    return build_namespace_summary()


def _register_tools():
    return [
        {
            "name": "browse_skill_namespace",
            "register_func": register_browse_skill_namespace,
        }
    ]


def _advertise_to_all_agents(agent_name=None):
    return ["browse_skill_namespace"]


register_callback("startup", _maybe_disable_frontmatter)
register_callback("load_prompt", _on_load_prompt)
register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _advertise_to_all_agents)

logger.info("namespace_skill_search plugin loaded")
