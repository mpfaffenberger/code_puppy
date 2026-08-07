"""Entry point: registers all hooks for the namespace_skill_search plugin.

Two hooks, both additive (no last-write-wins risk):

1. `load_prompt`    -> injects the compact namespace directory (a few lines
                       per namespace instead of one line per skill).
                       Fragments from every plugin are simply
                       newline-joined by base_agent.py, so this coexists
                       safely with any other plugin's fragment.
2. `register_tools` -> adds `browse_skill_namespace` as a real tool, wired
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
from code_puppy.plugins.agent_skills.config import (
    get_frontmatter_in_system_prompt,
    set_frontmatter_in_system_prompt,
)

from .namespaces import build_namespace_summary
from .search_tool import register_browse_skill_namespace

logger = logging.getLogger(__name__)


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


# Turn off the built-in flat per-skill list (one line per skill -> gone)
# the first time this plugin loads. We only ever flip it False when it's
# currently True, so a user who explicitly re-enables it later via
# `/skills frontmatter on` keeps that choice on subsequent restarts — we
# don't fight config the user set on purpose after our first load.
if get_frontmatter_in_system_prompt():
    set_frontmatter_in_system_prompt(False)
    logger.info(
        "namespace_skill_search: disabled flat skill-list frontmatter; "
        "namespace directory + browse_skill_namespace tool take over."
    )

register_callback("load_prompt", _on_load_prompt)
register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _advertise_to_all_agents)

logger.info("namespace_skill_search plugin loaded")
