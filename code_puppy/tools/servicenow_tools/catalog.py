"""ServiceNow Service Catalog tools.

Tools for browsing, submitting, and tracking service catalog requests.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning

from ._common import (
    SERVICENOW_BASE_URL,
    get_servicenow_client,
    handle_servicenow_error,
    convert_html_to_markdown,
    analyze_automation_feasibility,
)


# ============================================================================
# List Catalog Items
# ============================================================================


def servicenow_list_catalog_items(
    ctx: RunContext,
    query: str = "",
    category: str = "",
    limit: int = 25,
) -> dict:
    """Search or browse service catalog items.

    Args:
        ctx: PydanticAI run context
        query: Search query for catalog item names/descriptions
        category: Filter by category name
        limit: Maximum number of results (default: 25)

    Returns:
        Dict containing list of catalog items.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW CATALOG SEARCH [/bold white on purple] "
            f"\U0001f6d2 [bold cyan]{query or 'Browse all'}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_catalog_items(
            query=query,
            category=category,
            limit=limit,
        )

        items = []
        for item in result.get("result", []):
            sys_id = item.get("sys_id", "")
            items.append(
                {
                    "sys_id": sys_id,
                    "name": item.get("name", ""),
                    "short_description": item.get("short_description", ""),
                    "category": item.get("category", {}).get("title", "")
                    if isinstance(item.get("category"), dict)
                    else item.get("category", ""),
                    "price": item.get("price", ""),
                    "url": f"{SERVICENOW_BASE_URL}/sp?id=sc_cat_item&sys_id={sys_id}",
                }
            )

        emit_success(f"Found {len(items)} catalog item(s)")

        return {
            "success": True,
            "items": items,
            "total_count": len(items),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_catalog_items(agent: Any) -> Tool:
    """Register the servicenow_list_catalog_items tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_catalog_items)


# ============================================================================
# Get Catalog Item Details
# ============================================================================


def servicenow_get_catalog_item_details(
    ctx: RunContext,
    item_id: str,
) -> dict:
    """Get detailed information about a service catalog item, including its required variables.

    Use this tool BEFORE submitting a catalog request to understand what fields/variables
    are required for that specific catalog item.

    Args:
        ctx: PydanticAI run context
        item_id: The catalog item sys_id (get this from servicenow_list_catalog_items)

    Returns:
        Dict containing:
            - success (bool): Whether the item was found
            - name (str): Catalog item name
            - short_description (str): Brief description
            - description (str): Full description (markdown)
            - category (str): Item category
            - price (str): Price information
            - delivery_time (str): Expected delivery time
            - variables (list): List of required/optional variables
            - url (str): Web URL to view the catalog item
            - automation (dict): Analysis of whether the form can be automated
            - error (str, optional): Error message if lookup failed

    IMPORTANT: If automation.automatable is False, do NOT attempt to submit via API.
    Instead, provide the user with the URL and the values they need to enter manually.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW CATALOG ITEM DETAILS [/bold white on purple] "
            f"\U0001f4cb [bold cyan]{item_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_catalog_item(item_id)

        item_data = result.get("result", {})

        if not item_data:
            return {
                "success": False,
                "error": f"Catalog item not found: {item_id}",
                "error_type": "not_found",
            }

        # Extract and format variables
        variables = []
        raw_variables = item_data.get("variables", [])

        for var in raw_variables:
            var_info = {
                "name": var.get("name", ""),
                "label": var.get("label", var.get("question_text", "")),
                "type": var.get("friendly_type", var.get("display_type", "string")),
                "mandatory": var.get("mandatory", False),
                "description": var.get("help_text", var.get("instructions", "")),
                "default_value": var.get("default_value", ""),
            }

            # Include choices for select/choice fields
            choices = var.get("choices", var.get("choice_table", []))
            if choices:
                if isinstance(choices, list):
                    var_info["choices"] = [
                        {
                            "value": c.get("value", c),
                            "label": c.get("label", c.get("text", c)),
                        }
                        for c in choices
                    ]
                else:
                    var_info["choices"] = choices

            variables.append(var_info)

        # Sort variables: mandatory first, then by name
        variables.sort(key=lambda v: (not v.get("mandatory", False), v.get("name", "")))

        # Convert description HTML to markdown
        description_html = item_data.get("description", "")
        description_md = (
            convert_html_to_markdown(description_html) if description_html else ""
        )

        # Build URL
        url = f"{SERVICENOW_BASE_URL}/sp?id=sc_cat_item&sys_id={item_id}"

        # Analyze automation feasibility
        automation_analysis = analyze_automation_feasibility(item_data)

        emit_success(f"Found catalog item: {item_data.get('name', item_id)}")

        # Emit warning if form is not automatable
        if not automation_analysis["automatable"]:
            emit_warning(
                f"\u26a0\ufe0f  This form may NOT be automatable via API. "
                f"Blockers: {len(automation_analysis['blockers'])}"
            )

        return {
            "success": True,
            "sys_id": item_id,
            "name": item_data.get("name", ""),
            "short_description": item_data.get("short_description", ""),
            "description": description_md,
            "category": item_data.get("category", {}).get("name", "")
            if isinstance(item_data.get("category"), dict)
            else item_data.get("category", ""),
            "price": item_data.get("price", item_data.get("recurring_price", "")),
            "delivery_time": item_data.get("delivery_time", ""),
            "variables": variables,
            "variable_count": len(variables),
            "mandatory_variable_count": sum(1 for v in variables if v.get("mandatory")),
            "url": url,
            "automation": automation_analysis,
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_catalog_item_details(agent: Any) -> Tool:
    """Register the servicenow_get_catalog_item_details tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_catalog_item_details)


# ============================================================================
# Submit Catalog Request
# ============================================================================


def servicenow_submit_catalog_request(
    ctx: RunContext,
    item_id: str,
    variables: dict | None = None,
    quantity: int = 1,
    special_instructions: str = "",
    dry_run: bool = False,
) -> dict:
    """Submit a service catalog request.

    Args:
        ctx: PydanticAI run context
        item_id: The catalog item sys_id
        variables: Dictionary of variable values required by the catalog item
        quantity: Quantity to order (default: 1)
        special_instructions: Additional instructions for the request
        dry_run: If True, preview without submitting

    Returns:
        Dict containing request details or error.
    """
    mode_label = "DRY RUN" if dry_run else "SUBMIT REQUEST"
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW {mode_label} [/bold white on purple] "
            f"\U0001f4e6 [bold cyan]Item: {item_id[:20]}...[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - request NOT submitted")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually submit the request.",
            "preview": {
                "item_id": item_id,
                "variables": variables or {},
                "quantity": quantity,
                "special_instructions": special_instructions or "(none)",
            },
        }

    try:
        client = get_servicenow_client()
        result = client.submit_catalog_request(
            item_id=item_id,
            variables=variables,
            quantity=quantity,
            special_instructions=special_instructions,
        )

        request_data = result.get("result", {})
        request_number = request_data.get(
            "number", request_data.get("request_number", "")
        )
        sys_id = request_data.get("sys_id", request_data.get("request_id", ""))

        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=sc_request.do?sys_id={sys_id}"

        emit_success(f"Submitted request: {request_number}")

        return {
            "success": True,
            "dry_run": False,
            "request_number": request_number,
            "sys_id": sys_id,
            "url": url,
            "message": f"Successfully submitted catalog request {request_number}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_submit_catalog_request(agent: Any) -> Tool:
    """Register the servicenow_submit_catalog_request tool with a PydanticAI agent."""
    return agent.tool(servicenow_submit_catalog_request)


# ============================================================================
# Get Request Status
# ============================================================================


def servicenow_get_request_status(
    ctx: RunContext,
    request_id: str,
) -> dict:
    """Get the status of a service catalog request.

    Args:
        ctx: PydanticAI run context
        request_id: Request number (REQ0012345) or sys_id

    Returns:
        Dict containing request status and details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW REQUEST STATUS [/bold white on purple] "
            f"\U0001f4cb [bold cyan]{request_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_request_status(request_id)

        request_data = result.get("result", {})

        if isinstance(request_data, list):
            if not request_data:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}",
                    "error_type": "not_found",
                }
            request_data = request_data[0]

        def get_display(field):
            val = request_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = request_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved request: {number}")

        return {
            "success": True,
            "sys_id": sys_id,
            "number": number,
            "state": get_display("request_state") or get_display("state"),
            "stage": get_display("stage"),
            "short_description": get_display("short_description"),
            "requested_for": get_display("requested_for"),
            "opened_at": get_display("opened_at"),
            "updated_at": get_display("sys_updated_on"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=sc_request.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_request_status(agent: Any) -> Tool:
    """Register the servicenow_get_request_status tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_request_status)
