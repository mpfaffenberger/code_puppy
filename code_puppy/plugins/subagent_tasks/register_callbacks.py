from code_puppy.callbacks import register_callback

from .tools import TOOL_DEFINITIONS


def _register_tools():
    return TOOL_DEFINITIONS


def _advertise(_agent_name=None):
    return [definition["name"] for definition in TOOL_DEFINITIONS]


register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _advertise)
