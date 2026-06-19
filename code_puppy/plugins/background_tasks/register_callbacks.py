from code_puppy.callbacks import register_callback

from .manager import get_background_manager
from .tools import TOOL_DEFINITIONS


def _register_tools():
    return TOOL_DEFINITIONS


def _advertise(_agent_name=None):
    return [definition["name"] for definition in TOOL_DEFINITIONS]


async def _shutdown():
    await get_background_manager().shutdown()


register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _advertise)
register_callback("shutdown", _shutdown)
