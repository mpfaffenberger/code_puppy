"""Mail rules management for Microsoft Graph.

This module provides CRUD operations for Outlook mail rules (messageRules),
enabling automated email organization, filtering, and inbox zero strategies.

Key capabilities:
- List existing mail rules
- Create new rules (move, delete, forward, flag, categorize)
- Update existing rules
- Delete rules
- Common rule templates for quick setup

MS Graph API Reference:
https://learn.microsoft.com/en-us/graph/api/resources/messagerule
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_rule(rule: dict) -> dict:
    """Format a mail rule for display."""
    actions = rule.get("actions", {})
    conditions = rule.get("conditions", {})

    # Extract action type
    action_types = []
    if actions.get("delete"):
        action_types.append("delete")
    if actions.get("moveToFolder"):
        action_types.append("move")
    if actions.get("copyToFolder"):
        action_types.append("copy")
    if actions.get("forwardTo"):
        action_types.append("forward")
    if actions.get("markImportance"):
        action_types.append(f"mark_{actions['markImportance']}")
    if actions.get("markAsRead"):
        action_types.append("mark_read")
    if actions.get("stopProcessingRules"):
        action_types.append("stop_processing")

    # Extract condition summary
    condition_summary = []
    if conditions.get("fromAddresses"):
        addrs = [
            a.get("emailAddress", {}).get("address", "")
            for a in conditions["fromAddresses"]
        ]
        condition_summary.append(f"from: {', '.join(addrs[:2])}")
    if conditions.get("subjectContains"):
        condition_summary.append(f"subject contains: {conditions['subjectContains']}")
    if conditions.get("senderContains"):
        condition_summary.append(f"sender contains: {conditions['senderContains']}")
    if conditions.get("headerContains"):
        condition_summary.append(f"header contains: {conditions['headerContains']}")

    return {
        "id": rule.get("id"),
        "name": rule.get("displayName", "Unnamed Rule"),
        "sequence": rule.get("sequence", 0),
        "is_enabled": rule.get("isEnabled", True),
        "actions": action_types or ["unknown"],
        "conditions": condition_summary or ["unknown"],
        "raw_actions": actions,
        "raw_conditions": conditions,
    }


# =============================================================================
# LIST MAIL RULES
# =============================================================================


def msgraph_list_mail_rules(
    ctx: RunContext[Any],
) -> dict:
    """List all mail rules in the inbox.

    Returns:
        Dict with success and list of rules with their conditions and actions.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📋 [bold cyan]Listing mail rules...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get("/me/mailFolders/inbox/messageRules")
        rules = response.get("value", [])

        formatted_rules = [_format_rule(r) for r in rules]

        # Group by action type for summary
        by_action = {}
        for rule in formatted_rules:
            for action in rule["actions"]:
                by_action.setdefault(action, []).append(rule["name"])

        emit_success(f"Found {len(rules)} mail rules")

        return {
            "success": True,
            "count": len(rules),
            "rules": formatted_rules,
            "by_action": by_action,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_mail_rules(agent: Any) -> Tool:
    """Register the list mail rules tool."""
    return agent.tool()(msgraph_list_mail_rules)


# =============================================================================
# GET MAIL RULE
# =============================================================================


def msgraph_get_mail_rule(
    ctx: RunContext[Any],
    *,
    rule_id: str,
) -> dict:
    """Get details of a specific mail rule.

    Args:
        rule_id: The ID of the rule to retrieve.

    Returns:
        Dict with success and full rule details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Getting mail rule: {rule_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        rule = client.get(f"/me/mailFolders/inbox/messageRules/{rule_id}")
        formatted = _format_rule(rule)

        emit_success(f"Retrieved rule: {formatted['name']}")

        return {
            "success": True,
            "rule": formatted,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_mail_rule(agent: Any) -> Tool:
    """Register the get mail rule tool."""
    return agent.tool()(msgraph_get_mail_rule)


# =============================================================================
# CREATE MAIL RULE
# =============================================================================


def msgraph_create_mail_rule(
    ctx: RunContext[Any],
    *,
    name: str,
    conditions: dict,
    actions: dict,
    is_enabled: bool = True,
    stop_processing: bool = True,
) -> dict:
    """Create a new mail rule.

    Args:
        name: Display name for the rule.
        conditions: Rule conditions dict. Supported keys:
            - fromAddresses: [{"emailAddress": {"address": "email@example.com"}}]
            - subjectContains: ["word1", "word2"]
            - senderContains: ["domain.com"]
            - headerContains: ["header-value"]
            - bodyContains: ["keyword"]
            - importance: "low" | "normal" | "high"
            - hasAttachments: True/False
            - isAutomaticForward: True/False
        actions: Rule actions dict. Supported keys:
            - delete: True (move to deleted items)
            - moveToFolder: "folder_id" (move to specific folder)
            - copyToFolder: "folder_id"
            - markAsRead: True
            - markImportance: "low" | "normal" | "high"
            - forwardTo: [{"emailAddress": {"address": "email@example.com"}}]
            - assignCategories: ["category1", "category2"]
        is_enabled: Whether the rule is active (default True).
        stop_processing: Stop processing more rules after this one (default True).

    Returns:
        Dict with success and the created rule.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"➕ [bold cyan]Creating mail rule: {name}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build the rule payload
        rule_payload = {
            "displayName": name,
            "isEnabled": is_enabled,
            "conditions": conditions,
            "actions": {
                **actions,
                "stopProcessingRules": stop_processing,
            },
        }

        response = client.post(
            "/me/mailFolders/inbox/messageRules",
            json=rule_payload,
        )

        formatted = _format_rule(response)

        emit_success(f"Created rule: {name}")

        return {
            "success": True,
            "rule": formatted,
            "message": f"Mail rule '{name}' created successfully",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_mail_rule(agent: Any) -> Tool:
    """Register the create mail rule tool."""
    return agent.tool()(msgraph_create_mail_rule)


# =============================================================================
# UPDATE MAIL RULE
# =============================================================================


def msgraph_update_mail_rule(
    ctx: RunContext[Any],
    *,
    rule_id: str,
    name: str | None = None,
    conditions: dict | None = None,
    actions: dict | None = None,
    is_enabled: bool | None = None,
) -> dict:
    """Update an existing mail rule.

    Args:
        rule_id: The ID of the rule to update.
        name: New display name (optional).
        conditions: New conditions dict (optional, replaces existing).
        actions: New actions dict (optional, replaces existing).
        is_enabled: Enable/disable the rule (optional).

    Returns:
        Dict with success and the updated rule.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✏️ [bold cyan]Updating mail rule: {rule_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build update payload with only provided fields
        update_payload = {}
        if name is not None:
            update_payload["displayName"] = name
        if conditions is not None:
            update_payload["conditions"] = conditions
        if actions is not None:
            update_payload["actions"] = actions
        if is_enabled is not None:
            update_payload["isEnabled"] = is_enabled

        if not update_payload:
            return {
                "success": False,
                "error": "No updates provided. Specify at least one field to update.",
            }

        response = client.patch(
            f"/me/mailFolders/inbox/messageRules/{rule_id}",
            json=update_payload,
        )

        formatted = _format_rule(response)

        emit_success(f"Updated rule: {formatted['name']}")

        return {
            "success": True,
            "rule": formatted,
            "message": "Mail rule updated successfully",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_update_mail_rule(agent: Any) -> Tool:
    """Register the update mail rule tool."""
    return agent.tool()(msgraph_update_mail_rule)


# =============================================================================
# DELETE MAIL RULE
# =============================================================================


def msgraph_delete_mail_rule(
    ctx: RunContext[Any],
    *,
    rule_id: str,
) -> dict:
    """Delete a mail rule.

    Args:
        rule_id: The ID of the rule to delete.

    Returns:
        Dict with success status.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🗑️ [bold cyan]Deleting mail rule: {rule_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        client.delete(f"/me/mailFolders/inbox/messageRules/{rule_id}")

        emit_success("Mail rule deleted")

        return {
            "success": True,
            "message": "Mail rule deleted successfully",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_mail_rule(agent: Any) -> Tool:
    """Register the delete mail rule tool."""
    return agent.tool()(msgraph_delete_mail_rule)


# =============================================================================
# TEMPLATE: CREATE NOISE FILTER RULE
# =============================================================================


def msgraph_create_noise_filter_rule(
    ctx: RunContext[Any],
    *,
    name: str,
    from_addresses: list[str] | None = None,
    subject_contains: list[str] | None = None,
    sender_contains: list[str] | None = None,
    action: str = "move",
    target_folder: str | None = None,
    mark_as_read: bool = True,
) -> dict:
    """Create a rule to filter noise/low-priority emails.

    This is a simplified wrapper for common noise filtering use cases.

    Args:
        name: Display name for the rule.
        from_addresses: List of email addresses to match.
        subject_contains: List of subject keywords to match.
        sender_contains: List of sender domain/name fragments to match.
        action: "move", "delete", or "archive" (default "move").
        target_folder: Folder ID to move to (required if action="move").
        mark_as_read: Mark matching emails as read (default True).

    Returns:
        Dict with success and the created rule.

    Example:
        Create a rule to filter SharePoint access requests:
        ```
        msgraph_create_noise_filter_rule(
            name="SharePoint Access Requests",
            from_addresses=["do-not-reply@walmart.com"],
            subject_contains=["wants to access", "asked to edit"],
            action="move",
            target_folder="<folder_id>"
        )
        ```
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔇 [bold cyan]Creating noise filter: {name}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build conditions
        conditions: dict = {}
        if from_addresses:
            conditions["fromAddresses"] = [
                {"emailAddress": {"address": addr}} for addr in from_addresses
            ]
        if subject_contains:
            conditions["subjectContains"] = subject_contains
        if sender_contains:
            conditions["senderContains"] = sender_contains

        if not conditions:
            return {
                "success": False,
                "error": "At least one condition (from_addresses, subject_contains, or sender_contains) is required.",
            }

        # Build actions
        actions: dict = {
            "stopProcessingRules": True,
        }
        if mark_as_read:
            actions["markAsRead"] = True

        if action == "delete":
            actions["delete"] = True
        elif action == "archive":
            # Get Archive folder ID
            try:
                archive = client.get("/me/mailFolders/archive")
                actions["moveToFolder"] = archive.get("id")
            except Exception:
                emit_warning("Could not find Archive folder, using delete instead")
                actions["delete"] = True
        elif action == "move":
            if not target_folder:
                # Create a folder for this noise category if not specified
                try:
                    # Try to find or create the folder
                    folder_name = name.replace(" ", "_")[:30]
                    folders = client.get(
                        "/me/mailFolders",
                        params={"$filter": f"displayName eq '{folder_name}'"},
                    )
                    if folders.get("value"):
                        target_folder = folders["value"][0]["id"]
                    else:
                        new_folder = client.post(
                            "/me/mailFolders",
                            json={"displayName": folder_name},
                        )
                        target_folder = new_folder.get("id")
                except Exception as e:
                    emit_warning(f"Could not create folder: {e}. Using delete action.")
                    actions["delete"] = True
                    target_folder = None

            if target_folder:
                actions["moveToFolder"] = target_folder

        # Create the rule
        rule_payload = {
            "displayName": name,
            "isEnabled": True,
            "conditions": conditions,
            "actions": actions,
        }

        response = client.post(
            "/me/mailFolders/inbox/messageRules",
            json=rule_payload,
        )

        formatted = _format_rule(response)

        emit_success(f"Created noise filter: {name}")

        return {
            "success": True,
            "rule": formatted,
            "message": f"Noise filter '{name}' created. Matching emails will be {action}d.",
            "folder_created": target_folder is not None and action == "move",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_noise_filter_rule(agent: Any) -> Tool:
    """Register the create noise filter rule tool."""
    return agent.tool()(msgraph_create_noise_filter_rule)


# =============================================================================
# LIST MAIL FOLDERS
# =============================================================================


def msgraph_list_mail_folders(
    ctx: RunContext[Any],
    *,
    include_children: bool = False,
) -> dict:
    """List mail folders.

    Args:
        include_children: Include child folders (default False).

    Returns:
        Dict with success and list of folders.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📁 [bold cyan]Listing mail folders...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get("/me/mailFolders", params={"$top": 100})
        folders = response.get("value", [])

        formatted = []
        for folder in folders:
            f = {
                "id": folder.get("id"),
                "name": folder.get("displayName"),
                "unread_count": folder.get("unreadItemCount", 0),
                "total_count": folder.get("totalItemCount", 0),
            }
            formatted.append(f)

            # Get child folders if requested
            if include_children and folder.get("childFolderCount", 0) > 0:
                try:
                    children = client.get(
                        f"/me/mailFolders/{folder['id']}/childFolders"
                    )
                    for child in children.get("value", []):
                        formatted.append(
                            {
                                "id": child.get("id"),
                                "name": f"{folder.get('displayName')}/{child.get('displayName')}",
                                "unread_count": child.get("unreadItemCount", 0),
                                "total_count": child.get("totalItemCount", 0),
                                "parent": folder.get("displayName"),
                            }
                        )
                except Exception:
                    pass

        emit_success(f"Found {len(formatted)} folders")

        return {
            "success": True,
            "count": len(formatted),
            "folders": formatted,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_mail_folders(agent: Any) -> Tool:
    """Register the list mail folders tool."""
    return agent.tool()(msgraph_list_mail_folders)
