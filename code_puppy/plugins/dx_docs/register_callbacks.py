"""Register DX Documentation plugin with Code Puppy's callback system.

This module hooks into the plugin lifecycle to register:
- The DXDocsAgent via the 'register_agents' callback
- All DX tools via the 'register_tools' callback

The plugin loader auto-discovers this file and calls it at startup.
"""

from typing import Any, Dict, List

from code_puppy.callbacks import register_callback


def _get_dx_agents() -> List[Dict[str, Any]]:
    """Return DX agent definitions for plugin registration.

    Lazy-imports the agent class to avoid loading dependencies
    until the agent is actually needed.

    Returns:
        List of agent definitions with 'name' and 'class' keys.
    """
    from code_puppy.plugins.dx_docs.agent import DXDocsAgent

    return [
        {
            "name": "dx-docs",
            "class": DXDocsAgent,
        }
    ]


def _get_dx_tools() -> List[Dict[str, Any]]:
    """Return DX tool definitions for plugin registration.

    Lazy-imports tool registration functions to avoid loading
    heavy dependencies (httpx, etc.) until tools are first used.

    Returns:
        List of tool definitions with 'name' and 'register_func' keys.
    """
    from code_puppy.plugins.dx_docs.tools import (
        register_dx_authenticate,
        register_dx_get_page_content,
        register_dx_get_tags,
        register_dx_search,
        register_dx_semantic_search,
    )

    return [
        {"name": "dx_search", "register_func": register_dx_search},
        {"name": "dx_semantic_search", "register_func": register_dx_semantic_search},
        {"name": "dx_get_page_content", "register_func": register_dx_get_page_content},
        {"name": "dx_get_tags", "register_func": register_dx_get_tags},
        {"name": "dx_authenticate", "register_func": register_dx_authenticate},
    ]


# Register with the callback system
register_callback("register_agents", _get_dx_agents)
register_callback("register_tools", _get_dx_tools)
