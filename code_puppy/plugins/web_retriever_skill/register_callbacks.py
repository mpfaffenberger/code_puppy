"""Register the built-in ``web-retriever`` skill."""

from pathlib import Path

from code_puppy.callbacks import register_callback

_SKILL_PATH = Path(__file__).with_name("SKILL.md")


def _register_web_retriever_skill() -> list[dict[str, str]]:
    """Expose Web Retriever delegation guidance through the skills system."""
    return [
        {
            "name": "web-retriever",
            "skill_md_path": str(_SKILL_PATH),
        }
    ]


register_callback("register_skills", _register_web_retriever_skill)
