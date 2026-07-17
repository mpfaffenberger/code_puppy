"""Register the built-in ``mist-agent`` skill.

The skill's full SKILL.md lives alongside this file.  We register it via
the ``register_skills`` callback so the agent_skills plugin materializes
it into the plugin-skill cache and it shows up in ``/skills list``,
``activate_skill``, and the system-prompt skill block — just like any
user-installed skill.
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
            "name": "mist-agent",
            "skill_md_path": str(_SKILL_DIR / "SKILL.md"),
        }
    ]


register_callback("register_skills", _register_builtin_skills)
