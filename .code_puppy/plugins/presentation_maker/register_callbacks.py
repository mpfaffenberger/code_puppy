"""Register the presentation-maker agent, skill, and tools."""

from pathlib import Path

from code_puppy.callbacks import register_callback

from .tools import register_build_presentation, register_render_presentation

PLUGIN_DIR = Path(__file__).parent
AGENT_NAME = "presentation-maker"


def _register_agents() -> list[dict]:
    return [
        {
            "name": AGENT_NAME,
            "json_path": str(PLUGIN_DIR / "agent.json"),
        }
    ]


def _register_tools() -> list[dict]:
    return [
        {
            "name": "build_presentation",
            "register_func": register_build_presentation,
        },
        {
            "name": "render_presentation",
            "register_func": register_render_presentation,
        },
    ]


def _register_agent_tools(agent_name: str | None) -> list[str]:
    if agent_name != AGENT_NAME:
        return []
    return ["build_presentation", "render_presentation"]


def _register_skills() -> list[dict]:
    return [
        {
            "name": "presentation-design",
            "description": (
                "Plan, create, render, inspect, and revise editable Microsoft "
                "PowerPoint presentations."
            ),
            "skill_md_path": PLUGIN_DIR / "presentation_skill" / "SKILL.md",
            "tags": ["powerpoint", "pptx", "slides", "presentations"],
            "version": "0.1.0",
        }
    ]


register_callback("register_agents", _register_agents)
register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _register_agent_tools)
register_callback("register_skills", _register_skills)
