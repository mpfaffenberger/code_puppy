from code_puppy.callbacks import register_callback

from .manager import get_manager, load_configs
from .tools import TOOL_DEFINITIONS, register_tools_callback


def _advertise(_agent_name=None):
    if not load_configs():
        return []
    return [definition["name"] for definition in TOOL_DEFINITIONS]


async def _shutdown():
    await get_manager().close()


def _help():
    return [
        (
            "/lsp status",
            "Show configured language servers from ~/.mist/lsp_servers.json",
        )
    ]


def _command(command: str, name: str):
    if name != "lsp":
        return None
    from code_puppy.messaging import emit_info

    configs = load_configs()
    emit_info(
        "Configured language servers: "
        + (", ".join(config.name for config in configs) if configs else "none")
    )
    return True


register_callback("register_tools", register_tools_callback)
register_callback("register_agent_tools", _advertise)
register_callback("shutdown", _shutdown)
register_callback("custom_command", _command)
register_callback("custom_command_help", _help)
