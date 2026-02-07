"""ServiceNow CMDB (Configuration Management Database) tools.

Tools for searching and viewing configuration items.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success

from ._common import (
    SERVICENOW_BASE_URL,
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# Search CMDB
# ============================================================================


def servicenow_search_cmdb(
    ctx: RunContext,
    query: str,
    ci_class: str = "cmdb_ci",
    limit: int = 25,
) -> dict:
    """Search for configuration items in the CMDB.

    Args:
        ctx: PydanticAI run context
        query: Search query (searches name and class)
        ci_class: CI class to search (default: cmdb_ci for all)
            Common classes:
            - cmdb_ci: All CIs
            - cmdb_ci_server: Servers
            - cmdb_ci_app_server: Application servers
            - cmdb_ci_database: Databases
            - cmdb_ci_appl: Applications
            - cmdb_ci_service: Services
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of CIs.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW CMDB SEARCH [/bold white on blue] "
            f"\U0001f5a5 [bold cyan]{query}[/bold cyan] in {ci_class}"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_cmdb(query=query, ci_class=ci_class, limit=limit)

        cis = []
        for ci in result.get("result", []):

            def get_display(field):
                val = ci.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            sys_id = get_display("sys_id") or ci.get("sys_id", "")
            cis.append(
                {
                    "sys_id": sys_id,
                    "name": get_display("name"),
                    "class": get_display("sys_class_name"),
                    "operational_status": get_display("operational_status"),
                    "install_status": get_display("install_status"),
                    "support_group": get_display("support_group"),
                    "owned_by": get_display("owned_by"),
                    "location": get_display("location"),
                    "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri={ci_class}.do?sys_id={sys_id}",
                }
            )

        emit_success(f"Found {len(cis)} CI(s)")

        return {
            "success": True,
            "configuration_items": cis,
            "total_count": len(cis),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_search_cmdb(agent: Any) -> Tool:
    """Register the servicenow_search_cmdb tool with a PydanticAI agent."""
    return agent.tool(servicenow_search_cmdb)


# ============================================================================
# Get CMDB Item
# ============================================================================


def servicenow_get_cmdb_item(
    ctx: RunContext,
    ci_id: str,
    ci_class: str = "cmdb_ci",
) -> dict:
    """Get configuration item details.

    Args:
        ctx: PydanticAI run context
        ci_id: CI sys_id or name
        ci_class: CI class table (default: cmdb_ci)

    Returns:
        Dict containing CI details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET CI [/bold white on blue] "
            f"\U0001f5a5 [bold cyan]{ci_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_cmdb_item(ci_id=ci_id, ci_class=ci_class)

        ci_data = result.get("result", {})

        if isinstance(ci_data, list):
            if not ci_data:
                return {
                    "success": False,
                    "error": f"CI not found: {ci_id}",
                    "error_type": "not_found",
                }
            ci_data = ci_data[0]

        def get_display(field):
            val = ci_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        sys_id = get_display("sys_id") or ci_data.get("sys_id", "")
        name = get_display("name")

        emit_success(f"Retrieved CI: {name}")

        return {
            "success": True,
            "sys_id": sys_id,
            "name": name,
            "class": get_display("sys_class_name"),
            "short_description": get_display("short_description"),
            "operational_status": get_display("operational_status"),
            "install_status": get_display("install_status"),
            "support_group": get_display("support_group"),
            "owned_by": get_display("owned_by"),
            "managed_by": get_display("managed_by"),
            "location": get_display("location"),
            "environment": get_display("u_environment"),
            "vendor": get_display("vendor"),
            "cost_center": get_display("cost_center"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri={ci_class}.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_cmdb_item(agent: Any) -> Tool:
    """Register the servicenow_get_cmdb_item tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_cmdb_item)


# ============================================================================
# Get CMDB Relationships
# ============================================================================


def servicenow_get_cmdb_relationships(
    ctx: RunContext,
    ci_id: str,
    direction: str = "both",
) -> dict:
    """Get relationships for a configuration item.

    Args:
        ctx: PydanticAI run context
        ci_id: CI sys_id
        direction: Relationship direction - 'parent', 'child', 'both' (default: both)

    Returns:
        Dict containing the relationships.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW CI RELATIONSHIPS [/bold white on blue] "
            f"\U0001f517 [bold cyan]{ci_id}[/bold cyan] ({direction})"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_cmdb_relationships(ci_id=ci_id, direction=direction)

        relationships = []
        for rel in result.get("result", []):

            def get_display(field):
                val = rel.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            parent_val = rel.get("parent", {})
            child_val = rel.get("child", {})

            relationships.append(
                {
                    "type": get_display("type"),
                    "parent_id": parent_val.get("value", "")
                    if isinstance(parent_val, dict)
                    else parent_val,
                    "parent_name": parent_val.get("display_value", "")
                    if isinstance(parent_val, dict)
                    else "",
                    "child_id": child_val.get("value", "")
                    if isinstance(child_val, dict)
                    else child_val,
                    "child_name": child_val.get("display_value", "")
                    if isinstance(child_val, dict)
                    else "",
                }
            )

        emit_success(f"Found {len(relationships)} relationship(s)")

        return {
            "success": True,
            "ci_id": ci_id,
            "direction": direction,
            "relationships": relationships,
            "total_count": len(relationships),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_cmdb_relationships(agent: Any) -> Tool:
    """Register the servicenow_get_cmdb_relationships tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_cmdb_relationships)


# ============================================================================
# List CMDB Classes
# ============================================================================


def servicenow_list_cmdb_classes(
    ctx: RunContext,
    limit: int = 50,
) -> dict:
    """List available CMDB CI classes.

    Args:
        ctx: PydanticAI run context
        limit: Maximum results (default: 50)

    Returns:
        Dict containing list of CI classes.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] SERVICENOW CMDB CLASSES [/bold white on blue] "
            "\U0001f5a5 [bold cyan]Listing...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_cmdb_classes(limit=limit)

        classes = []
        for cls in result.get("result", []):
            classes.append(
                {
                    "name": cls.get("name", ""),
                    "label": cls.get("label", ""),
                    "sys_id": cls.get("sys_id", ""),
                }
            )

        emit_success(f"Found {len(classes)} class(es)")

        return {
            "success": True,
            "classes": classes,
            "total_count": len(classes),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_cmdb_classes(agent: Any) -> Tool:
    """Register the servicenow_list_cmdb_classes tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_cmdb_classes)
