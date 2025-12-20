"""MS Graph Batch Request operations.

This module provides batch request capabilities for MS Graph API,
allowing up to 20 operations per batch for dramatically faster bulk operations.

The $batch endpoint is UNIVERSAL - it can batch ANY MS Graph operation:
- GET: Fetch multiple items (users, messages, events)
- POST: Create multiple items, move emails, etc.
- PATCH: Update multiple items (flag emails, mark read)
- DELETE: Delete multiple items

You can even MIX different operations in a single batch!

Example batch that does 3 different things in one API call:
```python
msgraph_batch_request(ctx, [
    {"id": "1", "method": "GET", "url": "/me/messages?$top=5"},
    {"id": "2", "method": "POST", "url": "/me/messages/abc/move", "body": {"destinationId": "archive"}},
    {"id": "3", "method": "PATCH", "url": "/me/messages/def", "body": {"isRead": true}},
])
```
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


MAX_BATCH_SIZE = 20  # MS Graph limit per batch call


def msgraph_batch_request(
    ctx: RunContext[Any],
    requests: list[dict],
) -> dict:
    """Execute multiple MS Graph requests in a single batch call.

    This dramatically speeds up bulk operations by sending up to 20 requests
    at once. For larger batches, this tool automatically chunks into multiple
    batch calls.

    The batch endpoint is UNIVERSAL - it works with ANY MS Graph operation.

    Args:
        requests: List of request objects, each containing:
            - id: Unique identifier for this request (e.g., "1", "2", "msg-123")
            - method: HTTP method (GET, POST, PATCH, DELETE)
            - url: Relative URL (e.g., "/me/messages/{id}", "/me/todo/lists")
            - body: Optional request body (for POST/PATCH) - will be JSON encoded
            - headers: Optional headers dict (Content-Type auto-added for body)

    Returns:
        Dict with:
            - success: True if batch completed (even if some requests failed)
            - responses: List of response objects, each with:
                - id: Matches the request id
                - status: HTTP status code (200, 201, 204, 400, 404, etc.)
                - body: Response body (if any)
            - succeeded: Count of successful requests (2xx status)
            - failed: Count of failed requests (4xx, 5xx status)
            - total: Total requests processed

    Common Batch Patterns:

    1. MOVE MULTIPLE EMAILS TO ARCHIVE:
       [{"id": "1", "method": "POST", "url": "/me/messages/{msgId}/move",
         "body": {"destinationId": "archive"}}]

    2. FLAG MULTIPLE EMAILS (creates To Do tasks!):
       [{"id": "1", "method": "PATCH", "url": "/me/messages/{msgId}",
         "body": {"flag": {"flagStatus": "flagged"}}}]

    3. MARK MULTIPLE AS READ:
       [{"id": "1", "method": "PATCH", "url": "/me/messages/{msgId}",
         "body": {"isRead": true}}]

    4. DELETE MULTIPLE:
       [{"id": "1", "method": "DELETE", "url": "/me/messages/{msgId}"}]

    5. CREATE MULTIPLE TASKS:
       [{"id": "1", "method": "POST", "url": "/me/todo/lists/{listId}/tasks",
         "body": {"title": "Task 1"}}]

    6. CREATE FOLDER:
       [{"id": "1", "method": "POST", "url": "/me/mailFolders",
         "body": {"displayName": "My Folder"}}]

    7. MIXED OPERATIONS (all in one call!):
       [
         {"id": "1", "method": "POST", "url": "/me/messages/a/move", "body": {...}},
         {"id": "2", "method": "PATCH", "url": "/me/messages/b", "body": {...}},
         {"id": "3", "method": "DELETE", "url": "/me/messages/c"},
       ]
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📦 [bold cyan]Executing batch of {len(requests)} requests...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    if not requests:
        return {
            "success": True,
            "responses": [],
            "succeeded": 0,
            "failed": 0,
            "total": 0,
            "message": "No requests to execute",
        }

    all_responses = []
    succeeded = 0
    failed = 0

    # Process in chunks of MAX_BATCH_SIZE
    for i in range(0, len(requests), MAX_BATCH_SIZE):
        chunk = requests[i : i + MAX_BATCH_SIZE]
        chunk_num = (i // MAX_BATCH_SIZE) + 1
        total_chunks = (len(requests) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE

        if total_chunks > 1:
            emit_info(f"  Processing chunk {chunk_num}/{total_chunks}...")

        # Format requests for batch API
        batch_requests = []
        for j, req in enumerate(chunk):
            batch_req = {
                "id": str(req.get("id", f"{i + j}")),
                "method": req.get("method", "GET").upper(),
                "url": req.get("url"),
            }
            if req.get("body"):
                batch_req["body"] = req["body"]
                batch_req["headers"] = {"Content-Type": "application/json"}
            if req.get("headers"):
                batch_req["headers"] = {
                    **batch_req.get("headers", {}),
                    **req["headers"],
                }
            batch_requests.append(batch_req)

        try:
            # Execute batch
            response = client.post(
                "/$batch",
                json={"requests": batch_requests},
            )

            # Process responses
            for resp in response.get("responses", []):
                status = resp.get("status", 0)
                if 200 <= status < 300:
                    succeeded += 1
                else:
                    failed += 1
                all_responses.append(resp)

        except Exception as e:
            # If batch fails entirely, mark all as failed
            failed += len(chunk)
            emit_warning(f"Batch chunk failed: {str(e)[:50]}")
            for j, req in enumerate(chunk):
                all_responses.append(
                    {
                        "id": str(req.get("id", f"{i + j}")),
                        "status": 500,
                        "body": {"error": str(e)[:100]},
                    }
                )

    # Summary
    if failed > 0:
        emit_warning(f"Batch complete: {succeeded} succeeded, {failed} failed")
    else:
        emit_success(f"Batch complete: {succeeded} operations succeeded")

    return {
        "success": True,
        "responses": all_responses,
        "succeeded": succeeded,
        "failed": failed,
        "total": len(requests),
    }


def register_msgraph_batch_request(agent: Any) -> Tool:
    """Register the batch request tool."""
    return agent.tool()(msgraph_batch_request)
