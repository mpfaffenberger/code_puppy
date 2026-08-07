"""Register the built-in ``code-puppy-agent`` skill.

The skill's SKILL.md lives alongside this file and is an *index* into a
set of topic-specific reference files (``AGENTS_AND_TOOLS.md``,
``PLUGINS_AND_CALLBACKS.md``, ``MODELS_AND_MCP.md``,
``SESSIONS_AND_HISTORY.md``, ``SKILLS_SYSTEM.md``,
``SYSTEM_PROMPT_CONFIG_AND_I18N.md``) in the same directory. This keeps
any single activation cheap while still covering the full internals
surface -- see SKILL.md's "Reference Map" for which file answers which
question.

We register it via the ``register_skills`` callback so the agent_skills
plugin materializes it into the plugin-skill cache and it shows up in
``/skills list``, ``activate_skill``, and the system-prompt skill block --
just like any user-installed skill.

Note: only ``skill_md_path`` is registered below, not the reference
files. Plugin-registered skills (``skill_md_path``/``skill_md``/
``frontmatter``+``body``) only ever materialize ``SKILL.md`` itself into
the runtime cache -- sibling files are NOT auto-discovered as
``resources`` the way they would be for a real filesystem skill
directory. That's why SKILL.md references the other files by their real
repo paths in prose (for the model to ``read_file`` on demand) rather
than relying on the ``resources`` field ``activate_skill`` returns.
"""

from pathlib import Path

from code_puppy.callbacks import register_callback

_SKILL_DIR = Path(__file__).resolve().parent


def _register_builtin_skills() -> list[dict]:
    # This "name" MUST match the SKILL.md frontmatter ``name:`` field.
    # SkillInfo.name (driven by this key) governs dedup + the disable-set,
    # while the frontmatter name drives display & ``/activate_skill``. A
    # mismatch would silently break ``/skills enable|disable`` and the alias.
    return [
        {
            "name": "code-puppy-agent",
            "skill_md_path": str(_SKILL_DIR / "SKILL.md"),
        }
    ]


register_callback("register_skills", _register_builtin_skills)
