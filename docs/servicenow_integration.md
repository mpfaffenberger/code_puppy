# ServiceNow Integration for Code Puppy

This document describes the ServiceNow integration added to Code Puppy, providing full access to Walmart's ServiceNow instance for KB articles, incident management, service catalog requests, and user/group management.

## Overview

**Agent Name:** `servicenow`  
**Display Name:** ServiceNow 🎫  
**Total Tools:** 17 (16 ServiceNow + agent_share_your_reasoning)

## Files Modified/Created

### Core Files
- `code_puppy/agents/agent_servicenow.py` - The ServiceNow agent (renamed from agent_servicenow_kb.py)
- `code_puppy/tools/servicenow_tools.py` - All ServiceNow tools
- `code_puppy/plugins/walmart_specific/servicenow_client.py` - ServiceNow API client
- `code_puppy/plugins/walmart_specific/servicenow_auth.py` - Authentication (pre-existing)
- `code_puppy/tools/__init__.py` - Tool registration
- `tests/test_servicenow_tools.py` - Unit tests

## Tools Reference

### Knowledge Base (3 tools)

| Tool | Description |
|------|-------------|
| `servicenow_kb_search` | Search KB articles by keyword |
| `servicenow_kb_read_article` | Read full article content (supports pagination) |
| `servicenow_kb_search_by_category` | Search articles within a category |

### Incident Management (4 tools)

| Tool | Description |
|------|-------------|
| `servicenow_create_incident` | Create a new incident (supports dry_run) |
| `servicenow_get_incident` | Get full incident details |
| `servicenow_list_my_incidents` | List incidents for current user |
| `servicenow_add_incident_comment` | Add comment/work note (supports dry_run) |

### Service Catalog (4 tools)

| Tool | Description |
|------|-------------|
| `servicenow_list_catalog_items` | Search/browse catalog items |
| `servicenow_get_catalog_item_details` | Get item details including required variables |
| `servicenow_submit_catalog_request` | Submit a catalog request (supports dry_run) |
| `servicenow_get_request_status` | Check status of a submitted request |

### Groups & Users (4 tools)

| Tool | Description |
|------|-------------|
| `servicenow_search_assignment_groups` | Search for ITIL assignment groups |
| `servicenow_search_users` | Search for users by name/email |
| `servicenow_get_user_groups` | Get groups a user belongs to |
| `servicenow_get_group_members` | Get members of a group |

### Authentication (1 tool)

| Tool | Description |
|------|-------------|
| `servicenow_authenticate` | Launch browser-based SSO login |

## Incident Creation - Full Field Reference

### `servicenow_create_incident` Parameters

```python
servicenow_create_incident(
    # Required
    short_description: str,           # Brief summary (max 160 chars)
    
    # Optional - Core Fields
    description: str = "",            # Detailed description
    urgency: int = 3,                 # 1=High, 2=Medium, 3=Low
    impact: int = 3,                  # 1=High, 2=Medium, 3=Low
    category: str = "",               # e.g., "Software", "Hardware", "Network"
    subcategory: str = "",            # e.g., "Application", "Email"
    
    # Optional - Assignment
    assignment_group: str = "",       # ITIL group name or sys_id
    assigned_to: str = "",            # Username or sys_id
    
    # Optional - Caller & Channel
    caller_id: str = "",              # Who reported it (defaults to current user)
    contact_type: str = "",           # "phone", "email", "self-service", "chat"
    
    # Optional - Configuration Item
    cmdb_ci: str = "",                # Affected CI/application name or sys_id
    
    # Optional - Any Other Field
    additional_fields: dict = None,   # Pass any ServiceNow incident field
    
    # Testing
    dry_run: bool = False,            # Preview without creating
)
```

### `additional_fields` - Supported Fields

```python
additional_fields={
    # Standard fields
    "priority": "1",                    # Override calculated priority (1-5)
    "state": "2",                       # 1=New, 2=In Progress, 3=On Hold, 6=Resolved, 7=Closed
    "work_notes": "Internal notes...",  # Not visible to caller
    "comments": "Customer comment...",  # Visible to caller
    "business_service": "AI Platform",  # Business service
    "service_offering": "Code Puppy",   # Service offering
    "location": "Bentonville HO",       # Location
    "opened_by": "jsmith",              # Who opened it
    "close_code": "Solved",             # For resolved incidents
    "close_notes": "Fixed by...",       # Resolution notes
    "parent_incident": "INC0012345",    # Parent incident
    "problem_id": "PRB0001234",         # Related problem
    "rfc": "CHG0001234",                # Related change
    
    # Custom fields (check your ServiceNow instance)
    "u_environment": "Production",
    "u_application_name": "Code Puppy",
}
```

## Service Catalog Workflow

### Step 1: Find the Catalog Item
```python
servicenow_list_catalog_items(query="Active Directory Group")
# Returns: sys_id, name, description for matching items
```

### Step 2: Get Required Variables
```python
servicenow_get_catalog_item_details(item_id="b320974d...")
# Returns:
#   - addremove (required): "addusers" or "removeusers"
#   - groupname (required): AD group name
#   - busjust (required): Business justification
#   - user_list (optional): Users to add/remove
```

### Step 3: Preview Request (dry_run)
```python
servicenow_submit_catalog_request(
    item_id="b320974d...",
    variables={
        "addremove": "addusers",
        "groupname": "DL-TeamAlpha-Developers",
        "busjust": "Need access for Q1 project",
        "user_list": "jsmith"
    },
    dry_run=True
)
```

### Step 4: Submit for Real
```python
servicenow_submit_catalog_request(..., dry_run=False)
```

### Automation Feasibility Detection

The `servicenow_get_catalog_item_details` function now analyzes catalog items to detect if they can be automated via API. The response includes an `automation` field:

```python
"automation": {
    "automatable": bool,      # Whether API submission is likely to work
    "confidence": str,        # "high", "medium", or "low"
    "blockers": list[str],    # Definite reasons automation will fail
    "warnings": list[str],    # Potential issues that may cause problems
}
```

**Blockers are detected for:**
- External API integrations (Tableau, Azure, etc.)
- Bearer token authentication in client scripts
- Dynamically populated dropdowns (empty choices)
- Hidden validation fields checked by onSubmit
- Client-side error validation
- Form submission blocking logic

**Example response for the Tableau AD Group form:**
```json
{
  "automatable": false,
  "confidence": "high",
  "blockers": [
    "Tableau API integration detected in onChange script",
    "Bearer token authentication detected (external API) in onSubmit script",
    "Field 'site_name' has no choices (dynamically populated by JavaScript)"
  ]
}
```

### Handling Complex/Dynamic Forms

For forms that ARE automatable but have complex fields:

1. **Map variable names** - Try variations like `ad_group_name`, `groupname`, `group_name`
2. **Use sys_id for reference fields** - Reference fields need sys_id values, not display names
3. **Report actual errors** - If submission fails, the exact ServiceNow error is returned with hints

If a submission fails with a validation error, the response includes:
- `error`: The exact error message from ServiceNow
- `raw_error`: Full error details for debugging
- `retry_hint`: Suggestions for fixing the issue

## Dry Run Mode

All write operations support `dry_run=True` for safe testing:

- `servicenow_create_incident(..., dry_run=True)`
- `servicenow_submit_catalog_request(..., dry_run=True)`
- `servicenow_add_incident_comment(..., dry_run=True)`

In dry_run mode:
- No data is sent to ServiceNow
- Returns a preview of what WOULD be submitted
- Safe for testing and validation

## Example Usage

### Create Incident with Full Details
```python
servicenow_create_incident(
    short_description="Critical Application Outage - Code Puppy",
    description="The ServiceNow integration is experiencing complete outage.",
    urgency=1,
    impact=1,
    category="Software",
    subcategory="Application",
    assignment_group="GTL AI Labs",
    assigned_to="wkramme",
    caller_id="wkramme",
    contact_type="self-service",
    cmdb_ci="Code Puppy",
    additional_fields={
        "priority": "1",
        "business_service": "AI Platform Services",
        "work_notes": "Initial investigation started.",
    },
    dry_run=True  # Remove to actually create
)
```

### Find User's Groups
```python
servicenow_get_user_groups(user_id="wkramme")
# Returns: GTL AI Labs, GTL-LAI, Delegates, etc.
```

### Find Group Members
```python
servicenow_get_group_members(group_id="GTL AI Labs")
# Returns: Matthew Arsenault, Julie Pei, Bill Kramme, etc.
```

## Authentication

The ServiceNow integration uses session-based authentication stored in:
`~/.code_puppy/servicenow.json`

If you get a 401 error, use:
```python
servicenow_authenticate()
```

This launches a browser-based SSO login flow.

## API Details

### Base URL
`https://walmartglobal.service-now.com`

### Tables Used
- `kb_knowledge` - Knowledge Base articles
- `incident` - Incidents
- `sc_cat_item` - Service Catalog items
- `sc_request` - Service Requests
- `sys_user_group` - Assignment groups
- `sys_user` - Users
- `sys_user_grmember` - Group membership

### Rate Limiting
The client includes a shared rate limiter (20 requests/minute) to avoid hitting ServiceNow limits.

## Testing

Run unit tests:
```bash
cd ~/code-puppy
python -m pytest tests/test_servicenow_tools.py -v
```

Tests use mocked responses and don't hit the real API.