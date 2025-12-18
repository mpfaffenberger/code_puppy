# Microsoft Graph Agent Usage Guide 📊

The Microsoft Graph Agent provides seamless access to Microsoft 365 services directly from Code Puppy. Interact with your email, calendar, files, Teams, SharePoint, and Planner using natural language commands.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Authentication](#authentication)
4. [Using the Agent](#using-the-agent)
5. [Tools Reference](#tools-reference)
6. [Common Workflows](#common-workflows)
7. [Troubleshooting](#troubleshooting)

---

## Overview

The Microsoft Graph Agent enables you to interact with your Microsoft 365 data using natural language. It wraps the Microsoft Graph API to provide a conversational interface for common tasks.

### Supported Services

| Service | Description |
|---------|-------------|
| **👤 Users** | Profile information, organizational hierarchy, user search |
| **📧 Mail** | Read, send, search, and reply to Outlook emails |
| **📅 Calendar** | List, create, update, and delete calendar events; check availability |
| **📁 OneDrive** | Browse, upload, download, share, and search files |
| **💬 Teams** | List teams and channels, read/send messages, create meetings |
| **🌐 SharePoint** | Access sites, document libraries, and search SharePoint content |
| **✅ Planner** | Manage plans, buckets, and tasks |

---

## Prerequisites

### Quick Start (Recommended)

Code Puppy uses the Azure CLI's public Client ID by default, so **no Azure AD app registration is required** for most users. Just run:

```
/msgraph_auth
```

This opens a browser for Azure AD login and works out of the box for most organizations. That's it! 🎉

### Custom App Registration (Advanced)

If your organization blocks the Azure CLI's Client ID, or you need specific permissions beyond the defaults, you can register your own app:

1. **Register an Application in Azure AD:**
   - Go to [Azure Portal](https://portal.azure.com) → **Azure Active Directory** → **App registrations**
   - Click **New registration**
   - Name: `Code Puppy` (or any name you prefer)
   - Supported account types: **Accounts in any organizational directory** (for multi-tenant) or your organization only
   - Redirect URI: Select **Web** and enter `http://localhost:8400/callback`

2. **Configure API Permissions:**
   - Go to **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**
   - Add the required scopes (see below)
   - Click **Grant admin consent** if required by your organization

3. **Get Application Credentials:**
   - Copy the **Application (client) ID** from the Overview page
   - If using confidential client: Go to **Certificates & secrets** → **New client secret** → Copy the secret value

4. **Set the environment variable:**
   ```bash
   export MSGRAPH_CLIENT_ID="your-custom-client-id"
   ```

### Required Permissions (Scopes)

The following Microsoft Graph scopes are required for full functionality:

| Scope | Purpose |
|-------|----------|
| `User.Read` | Read your profile |
| `Mail.Read` | Read emails |
| `Mail.Send` | Send emails |
| `Calendars.ReadWrite` | Read and write calendar events |
| `Files.ReadWrite.All` | Full access to OneDrive files |
| `Team.ReadBasic.All` | Read Teams information |
| `Sites.Read.All` | Read SharePoint sites |
| `Tasks.ReadWrite` | Read and write Planner tasks |
| `offline_access` | Refresh tokens for persistent sessions |

**Additional permissions for advanced features:**

| Scope | Purpose |
|-------|----------|
| `ChannelMessage.Send` | Send messages to Teams channels |
| `Channel.ReadBasic.All` | Read channel information |
| `Chat.Read` | Read chat messages |
| `OnlineMeetings.ReadWrite` | Create Teams meetings |
| `User.ReadBasic.All` | Search for users in directory |

### Environment Variables (Optional)

For most users, no environment variables are needed! Code Puppy uses sensible defaults.

However, you can customize behavior with these optional variables:

```bash
# Only needed if using a custom app registration (see Advanced section above)
export MSGRAPH_CLIENT_ID="your-custom-client-id"

# Only needed for confidential client apps
export MSGRAPH_CLIENT_SECRET="your-client-secret"

# Customize callback URL (default: http://localhost:8400/callback)
export MSGRAPH_REDIRECT_URI="http://localhost:8400/callback"

# Customize scopes (default includes all common scopes)
export MSGRAPH_SCOPES="User.Read Mail.Read Mail.Send Calendars.ReadWrite Files.ReadWrite.All Team.ReadBasic.All Sites.Read.All Tasks.ReadWrite offline_access"
```

**Tip:** Add these to your `~/.bashrc`, `~/.zshrc`, or use a `.env` file.

---

## Authentication

### Initial Authentication with `/msgraph_auth`

Before using any Microsoft Graph tools, you must authenticate:

```
/msgraph_auth
```

This command:
1. Opens a browser window to the Microsoft login page
2. You sign in with your Microsoft 365 credentials
3. Grants the requested permissions to Code Puppy
4. Redirects back to a local callback server
5. Stores the access and refresh tokens securely

### How the OAuth Flow Works

```
┌──────────────┐     1. /msgraph_auth      ┌──────────────────┐
│  Code Puppy  │ ─────────────────────────▶│   Opens Browser  │
└──────────────┘                           └────────┬─────────┘
                                                    │
                                            2. User logs in
                                                    ▼
┌──────────────┐     4. Exchange code      ┌──────────────────┐
│  Azure AD    │ ◀────────────────────────│  Microsoft Login │
│  Token API   │                           └────────┬─────────┘
└──────┬───────┘                                    │
       │                                    3. Auth code callback
       │ 5. Access + Refresh tokens                 │
       ▼                                            ▼
┌──────────────┐                           ┌──────────────────┐
│  Code Puppy  │ ◀─────────────────────────│  localhost:8400  │
│  (tokens     │                           │  /callback       │
│   saved)     │                           └──────────────────┘
└──────────────┘
```

### Token Storage

Tokens are stored at:

```
~/.code_puppy/msgraph.json
```

This file contains:
- **Access Token** - Used for API calls (expires after ~1 hour)
- **Refresh Token** - Used to obtain new access tokens (longer-lived)
- **Expiration Time** - When the access token expires
- **Scopes** - The permissions granted

**Security Note:** This file contains sensitive tokens. Protect it appropriately and never commit it to version control.

### Token Refresh Behavior

The MS Graph client automatically handles token refresh:

1. Before each API call, it checks if the access token is expired
2. If expired, it uses the refresh token to obtain a new access token
3. If the refresh token is also expired or invalid, you'll be prompted to re-authenticate

### Testing Authentication with `/msgraph_test`

Verify your authentication is working:

```
/msgraph_test
```

This command:
- Checks if tokens exist
- Validates the access token by calling the `/me` endpoint
- Reports your authenticated user information

For verbose output:

```
/msgraph_test debug
```

---

## Using the Agent

### Switching to the MS Graph Agent

Use the `/agent` command to switch:

```
/agent msgraph
```

Once switched, all your prompts will be handled by the MS Graph Agent with access to Microsoft 365 tools.

### Invoking as a Sub-Agent

You can invoke the MS Graph Agent from another agent:

```python
# From the default code-puppy agent
"Use the msgraph agent to check my calendar for tomorrow"
```

Or programmatically:

```python
invoke_agent(
    agent_name="msgraph",
    prompt="What meetings do I have tomorrow?"
)
```

### Example Conversations

**Email:**
```
User: Show me my unread emails
Agent: [Lists unread emails with subject, sender, and preview]

User: Search for emails about "Q4 budget"
Agent: [Searches and displays matching emails]

User: Send an email to john.doe@company.com saying the report is ready
Agent: [Composes and sends the email]
```

**Calendar:**
```
User: What's on my calendar today?
Agent: [Lists today's events with times and locations]

User: Schedule a meeting with Sarah tomorrow at 2pm for 30 minutes about project sync
Agent: [Creates the calendar event]

User: When are Mike and Lisa both free next week?
Agent: [Checks availability and suggests times]
```

**Files:**
```
User: List files in my Documents folder
Agent: [Lists files and folders with sizes and dates]

User: Find spreadsheets related to "budget"
Agent: [Searches OneDrive for matching files]

User: Share the Q4 report with view permissions
Agent: [Creates a sharing link]
```

---

## Tools Reference

### 👤 Users

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_get_me` | Get your own profile | None |
| `msgraph_get_user` | Get a user's profile | `user_id` (ID or email) |
| `msgraph_search_users` | Search directory for users | `query`, `limit` (default 10) |
| `msgraph_get_manager` | Get a user's manager | `user_id` (default "me") |
| `msgraph_get_direct_reports` | Get direct reports | `user_id` (default "me"), `limit` (default 50) |

**Return Fields for User:**
- `id`, `display_name`, `mail`, `user_principal_name`
- `job_title`, `department`, `office_location`
- `mobile_phone`, `business_phones`

---

### 📧 Mail

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_messages` | List emails from a folder | `folder` (default "inbox"), `limit` (default 10), `skip` (default 0), `filter_unread` (default false) |
| `msgraph_get_message` | Get full email content | `message_id` |
| `msgraph_send_mail` | Send a new email | `to` (list), `subject`, `body`, `cc` (optional), `bcc` (optional), `is_html` (default false) |
| `msgraph_reply_to_message` | Reply to an email | `message_id`, `body`, `reply_all` (default false) |
| `msgraph_search_mail` | Search emails | `query`, `limit` (default 10) |
| `msgraph_list_mail_folders` | List mail folders | None |

**Supported Folders:**
- `inbox`, `sentitems`, `drafts`, `deleteditems`, or folder ID

**Return Fields for Message:**
- `id`, `subject`, `from` (name, email), `to`, `cc`, `bcc`
- `body`, `received`, `sent`, `is_read`, `has_attachments`, `importance`

---

### 📅 Calendar

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_events` | List calendar events | `start` (ISO datetime, default now), `end` (ISO datetime, default +7 days), `limit` (default 10) |
| `msgraph_get_event` | Get event details | `event_id` |
| `msgraph_create_event` | Create a new event | `subject`, `start`, `end`, `attendees` (optional list), `body` (optional), `location` (optional), `is_online_meeting` (default false) |
| `msgraph_update_event` | Update an event | `event_id`, `subject`, `start`, `end`, `body`, `location` (all optional except event_id) |
| `msgraph_delete_event` | Delete an event | `event_id` |
| `msgraph_get_availability` | Check free/busy times | `emails` (list), `start`, `end`, `interval_minutes` (default 30) |
| `msgraph_list_calendars` | List user's calendars | None |

**Return Fields for Event:**
- `id`, `subject`, `start`, `end`, `location`
- `organizer`, `attendees` (with response status)
- `body`, `is_all_day`, `is_online_meeting`, `teams_link`

---

### 📁 OneDrive

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_drive_items` | List files/folders | `path` (default "/"), `limit` (default 25) |
| `msgraph_get_drive_item` | Get file/folder info | `item_id` or `path` |
| `msgraph_download_file` | Download file content | `item_id` or `path`, `max_size_mb` (default 10) |
| `msgraph_upload_file` | Upload a file (up to 4MB) | `path`, `content`, `content_type` (default "text/plain") |
| `msgraph_create_folder` | Create a folder | `path` (parent), `name` |
| `msgraph_share_file` | Create sharing link | `item_id`, `share_type` ("view" or "edit"), `scope` ("anonymous", "organization", "users") |
| `msgraph_search_files` | Search OneDrive | `query`, `limit` (default 10) |
| `msgraph_delete_drive_item` | Delete file/folder | `item_id` |

**Return Fields for Drive Item:**
- `id`, `name`, `type` (file/folder), `size`, `mime_type`
- `last_modified`, `created`, `web_url`, `child_count`

---

### 💬 Microsoft Teams

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_teams` | List joined teams | None |
| `msgraph_get_team` | Get team details | `team_id` |
| `msgraph_list_channels` | List team channels | `team_id` |
| `msgraph_get_channel` | Get channel details | `team_id`, `channel_id` |
| `msgraph_list_channel_messages` | Read channel messages | `team_id`, `channel_id`, `limit` (default 20) |
| `msgraph_send_channel_message` | Post to a channel | `team_id`, `channel_id`, `content`, `content_type` ("text" or "html") |
| `msgraph_create_online_meeting` | Create Teams meeting | `subject`, `start`, `end`, `attendees` (optional) |
| `msgraph_list_chats` | List recent chats | `limit` (default 20) |

**Return Fields for Team:**
- `id`, `display_name`, `description`, `visibility`, `web_url`

**Return Fields for Channel:**
- `id`, `display_name`, `description`, `membership_type`, `web_url`

---

### 🌐 SharePoint

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_sites` | List/search sites | `query` (optional, if None lists followed sites), `limit` (default 10) |
| `msgraph_get_site` | Get site details | `site_id` (ID or path like "contoso.sharepoint.com:/sites/team") |
| `msgraph_list_site_drives` | List document libraries | `site_id` |
| `msgraph_list_site_items` | List files in a site | `site_id`, `drive_id` (optional), `path` (default "/"), `limit` (default 25) |
| `msgraph_search_sharepoint` | Search all SharePoint | `query`, `limit` (default 10) |

**Return Fields for Site:**
- `id`, `name`, `description`, `web_url`, `created`, `last_modified`

---

### ✅ Planner

| Tool | Description | Parameters |
|------|-------------|------------|
| `msgraph_list_plans` | List Planner plans | `group_id` (optional, if None lists user's plans) |
| `msgraph_get_plan` | Get plan details | `plan_id` |
| `msgraph_list_buckets` | List buckets in a plan | `plan_id` |
| `msgraph_list_tasks` | List tasks | `plan_id`, `bucket_id` (optional), `limit` (default 50) |
| `msgraph_get_task` | Get task details | `task_id` |
| `msgraph_create_task` | Create a new task | `plan_id`, `title`, `bucket_id` (optional), `assigned_to` (optional list of user IDs), `due_date` (optional), `priority` (optional: 1=urgent, 3=important, 5=medium, 9=low) |
| `msgraph_update_task` | Update a task | `task_id`, `title`, `percent_complete` (0-100), `due_date`, `priority` (all optional except task_id) |
| `msgraph_delete_task` | Delete a task | `task_id` |

**Return Fields for Task:**
- `id`, `title`, `bucket_id`, `plan_id`
- `percent_complete`, `priority`, `priority_label`
- `due_date`, `start_date`, `assigned_to`
- `checklist_item_count`, `has_description`

**Priority Values:**
- `1` = Urgent
- `3` = Important  
- `5` = Medium (default)
- `9` = Low

---

## Common Workflows

### 📅 "Check my calendar for tomorrow and summarize meetings"

```
User: What meetings do I have tomorrow?

Agent: I'll check your calendar for tomorrow.
[Uses msgraph_list_events with start/end for tomorrow]

You have 3 meetings tomorrow:

1. **9:00 AM - 9:30 AM** - Daily Standup
   📍 Teams (online meeting)
   
2. **11:00 AM - 12:00 PM** - Project Review
   📍 Conference Room B
   👥 Sarah, Mike, Lisa
   
3. **2:00 PM - 2:30 PM** - 1:1 with Manager
   📍 Teams (online meeting)
```

### 📧 "Send an email to X about Y"

```
User: Send an email to john.smith@company.com about the Q4 report being ready

Agent: I'll send that email for you.
[Uses msgraph_send_mail]

✅ Email sent successfully!
- To: john.smith@company.com
- Subject: Q4 Report Ready
- Body: Hi John, I wanted to let you know that the Q4 report is now ready for your review...
```

### 📁 "Find files related to project Z"

```
User: Find files related to "Project Alpha"

Agent: Searching your OneDrive for Project Alpha files...
[Uses msgraph_search_files]

Found 5 files:

1. 📄 Project Alpha PRD.docx (245 KB)
   📁 /Documents/Projects/
   
2. 📊 Project Alpha Budget.xlsx (128 KB)
   📁 /Documents/Projects/
   
3. 📄 Alpha Team Meeting Notes.docx (56 KB)
   📁 /Documents/Meetings/
```

### ✅ "Create a task in the Sprint Planning board"

```
User: Create a task called "Review API documentation" in the Sprint 24 plan, assign it to me, due next Friday

Agent: Let me find the Sprint 24 plan and create that task.
[Uses msgraph_list_plans to find the plan]
[Uses msgraph_list_buckets to find the appropriate bucket]
[Uses msgraph_create_task]

✅ Task created!
- Title: Review API documentation
- Plan: Sprint 24
- Due: 2024-01-19
- Assigned to: You
```

### 👥 "Who are John's direct reports?"

```
User: Who reports to John Smith?

Agent: Let me look up John Smith and find his direct reports.
[Uses msgraph_search_users to find John Smith]
[Uses msgraph_get_direct_reports with John's user ID]

John Smith has 4 direct reports:

1. **Sarah Johnson** - Senior Engineer
   📧 sarah.johnson@company.com
   
2. **Mike Chen** - Engineer
   📧 mike.chen@company.com
   
3. **Lisa Park** - Engineer  
   📧 lisa.park@company.com
   
4. **Alex Rivera** - Associate Engineer
   📧 alex.rivera@company.com
```

---

## Troubleshooting

### Common Errors and Solutions

#### "No Microsoft Graph tokens found"

**Cause:** You haven't authenticated yet.

**Solution:**
```
/msgraph_auth
```

#### "Authentication failed (HTTP 401)"

**Cause:** Access token is invalid or expired.

**Solution:**
1. Try the operation again (auto-refresh may work)
2. If still failing, re-authenticate:
   ```
   /msgraph_auth
   ```

#### "Access denied (HTTP 403)"

**Cause:** Missing required permissions for the operation.

**Solution:**
1. Check that your Azure AD app has the required permissions
2. Ensure admin consent was granted for the permissions
3. Re-authenticate to get tokens with updated scopes:
   ```
   /msgraph_auth
   ```

#### "Resource not found (HTTP 404)"

**Cause:** The requested resource (email, event, file, etc.) doesn't exist or you don't have access.

**Solution:**
1. Verify the ID is correct
2. Check that you have access to the resource
3. Use list/search operations to find the correct ID

#### "Rate limited by Microsoft Graph"

**Cause:** Too many API requests in a short time.

**Solution:**
1. Wait a moment and try again
2. The agent automatically respects rate limits
3. For bulk operations, consider spacing out requests

#### "Custom Client ID issues"

**Cause:** Your organization may block the default Azure CLI Client ID.

**Solution:** Register a custom app (see [Custom App Registration](#custom-app-registration-advanced)) and set:
```bash
export MSGRAPH_CLIENT_ID="your-custom-client-id"
```

### Re-authenticating

If you encounter persistent authentication issues:

1. **Delete stored tokens:**
   ```bash
   rm ~/.code_puppy/msgraph.json
   ```

2. **Re-authenticate:**
   ```
   /msgraph_auth
   ```

3. **Verify authentication:**
   ```
   /msgraph_test debug
   ```

### Permission Issues

If certain operations fail with 403 errors:

1. **Check required scopes** in the [Tools Reference](#tools-reference)
2. **Update Azure AD app permissions:**
   - Go to Azure Portal → App registrations → Your app → API permissions
   - Add the missing permissions
   - Grant admin consent if required
3. **Re-authenticate** to get tokens with new permissions

### Browser Not Opening

If `/msgraph_auth` doesn't open a browser:

1. **Check Playwright is installed:**
   ```bash
   uv pip install playwright
   playwright install chromium
   ```

2. **Check if port 8400 is available:**
   ```bash
   lsof -i :8400
   ```

3. **Try a different redirect port** (update your Azure AD app and env var):
   ```bash
   export MSGRAPH_REDIRECT_URI="http://localhost:8401/callback"
   ```

---

## Tips for Effective Use

1. **Start with search** - When looking for specific emails, files, or users, use search tools first to find IDs

2. **Use IDs for follow-up operations** - Many tools require IDs (message ID, event ID, etc.) - get these from list/search operations

3. **Be specific with dates** - For calendar operations, use clear date formats like ISO 8601 (`2024-01-15T10:00:00`)

4. **Check availability before scheduling** - Use `msgraph_get_availability` to find good meeting times

5. **Paginate large results** - Use `limit` and `skip` parameters to page through large result sets

6. **Keep tokens secure** - Never share or commit `~/.code_puppy/msgraph.json`

---

*Happy Microsoft 365 automating! 🐶📊*
