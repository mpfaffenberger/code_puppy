"""ServiceNow Attachment tools.

Tools for viewing and managing attachments on records.
"""

import base64
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning

from ._common import (
    SERVICENOW_BASE_URL,
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# List Attachments
# ============================================================================


def servicenow_list_attachments(
    ctx: RunContext,
    table_name: str,
    record_sys_id: str,
) -> dict:
    """List attachments on a record.

    Args:
        ctx: PydanticAI run context
        table_name: Table name (e.g., 'incident', 'change_request', 'problem')
        record_sys_id: Record sys_id

    Returns:
        Dict containing list of attachments.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW LIST ATTACHMENTS [/bold white on blue] "
            f"\U0001f4ce [bold cyan]{table_name}/{record_sys_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_attachments(
            table_name=table_name, record_sys_id=record_sys_id
        )

        attachments = []
        for att in result.get("result", []):

            def get_display(field):
                val = att.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            sys_id = get_display("sys_id") or att.get("sys_id", "")
            attachments.append(
                {
                    "sys_id": sys_id,
                    "file_name": get_display("file_name"),
                    "content_type": get_display("content_type"),
                    "size_bytes": get_display("size_bytes"),
                    "created_by": get_display("sys_created_by"),
                    "created_on": get_display("sys_created_on"),
                    "download_url": f"{SERVICENOW_BASE_URL}/api/now/attachment/{sys_id}/file",
                }
            )

        emit_success(f"Found {len(attachments)} attachment(s)")

        return {
            "success": True,
            "table_name": table_name,
            "record_sys_id": record_sys_id,
            "attachments": attachments,
            "total_count": len(attachments),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_attachments(agent: Any) -> Tool:
    """Register the servicenow_list_attachments tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_attachments)


# ============================================================================
# Download Attachment
# ============================================================================


def servicenow_download_attachment(
    ctx: RunContext,
    attachment_sys_id: str,
    save_path: str = "",
) -> dict:
    """Download an attachment.

    Args:
        ctx: PydanticAI run context
        attachment_sys_id: Attachment sys_id
        save_path: Path to save the file (optional - if not provided, returns base64 content)

    Returns:
        Dict containing download result.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW DOWNLOAD ATTACHMENT [/bold white on blue] "
            f"\U0001f4e5 [bold cyan]{attachment_sys_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        content = client.get_attachment(attachment_sys_id)

        if save_path:
            # Save to file
            path = Path(save_path)
            path.write_bytes(content)
            emit_success(f"Downloaded to: {save_path}")
            return {
                "success": True,
                "attachment_sys_id": attachment_sys_id,
                "saved_to": str(path.absolute()),
                "size_bytes": len(content),
            }
        else:
            # Return as base64
            content_b64 = base64.b64encode(content).decode("utf-8")
            emit_success(f"Downloaded {len(content)} bytes")
            return {
                "success": True,
                "attachment_sys_id": attachment_sys_id,
                "content_base64": content_b64,
                "size_bytes": len(content),
                "note": "Content returned as base64. Provide save_path to save directly to file.",
            }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_download_attachment(agent: Any) -> Tool:
    """Register the servicenow_download_attachment tool with a PydanticAI agent."""
    return agent.tool(servicenow_download_attachment)


# ============================================================================
# Upload Attachment
# ============================================================================


def servicenow_upload_attachment(
    ctx: RunContext,
    table_name: str,
    record_sys_id: str,
    file_path: str,
    dry_run: bool = False,
) -> dict:
    """Upload an attachment to a record.

    Args:
        ctx: PydanticAI run context
        table_name: Table name (e.g., 'incident', 'change_request')
        record_sys_id: Record sys_id
        file_path: Path to the file to upload
        dry_run: If True, preview without uploading

    Returns:
        Dict with upload result.
    """
    mode_label = "DRY RUN" if dry_run else "UPLOAD ATTACHMENT"
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW {mode_label} [/bold white on green] "
            f"\U0001f4e4 [bold cyan]{file_path}[/bold cyan]"
        )
    )

    path = Path(file_path)

    if not path.exists():
        emit_warning(f"File not found: {file_path}")
        return {
            "success": False,
            "error": f"File not found: {file_path}",
            "error_type": "file_not_found",
        }

    if dry_run:
        emit_success("Dry run complete - file NOT uploaded")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually upload.",
            "preview": {
                "table_name": table_name,
                "record_sys_id": record_sys_id,
                "file_name": path.name,
                "file_size_bytes": path.stat().st_size,
            },
        }

    try:
        # Determine content type from file extension
        content_type_map = {
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xml": "application/xml",
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".zip": "application/zip",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        content_type = content_type_map.get(
            path.suffix.lower(), "application/octet-stream"
        )

        file_content = path.read_bytes()

        client = get_servicenow_client()
        result = client.upload_attachment(
            table_name=table_name,
            record_sys_id=record_sys_id,
            file_name=path.name,
            file_content=file_content,
            content_type=content_type,
        )

        attachment_data = result.get("result", {})
        attachment_sys_id = attachment_data.get("sys_id", "")

        emit_success(f"Uploaded: {path.name}")

        return {
            "success": True,
            "dry_run": False,
            "attachment_sys_id": attachment_sys_id,
            "file_name": path.name,
            "size_bytes": len(file_content),
            "message": f"Successfully uploaded {path.name}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_upload_attachment(agent: Any) -> Tool:
    """Register the servicenow_upload_attachment tool with a PydanticAI agent."""
    return agent.tool(servicenow_upload_attachment)
