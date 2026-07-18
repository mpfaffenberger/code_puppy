---
name: create-jira
argument-hint: ticket_summary_text
description: Create a new Jira ticket using configurable project settings from the flux config.env
allowed-tools: mcp__mcp-jira__get_issue_by_key_or_link, mcp__mcp-jira__create_jira_story, mcp__mcp-jira__update_jira_issue_fields_dynamic, AskUserQuestion, Bash
---

# Create Jira Ticket

`$ARGUMENTS` = ticket summary/title. `reporter` = OS `$USER` — never ask the user for it.

## STEP 1: Load configuration

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review"
source "$FLUX_BASE/config.env" 2>/dev/null
echo "JIRA_BASE_URL: ${JIRA_BASE_URL:-<not set>}"
echo "JIRA_PROJECT_KEY: ${JIRA_PROJECT_KEY:-<not set>}"
echo "JIRA_TICKET_TEMPLATE: ${JIRA_TICKET_TEMPLATE:-<not set>}"
echo "JIRA_TICKET_PREFIX: ${JIRA_TICKET_PREFIX:-<not set>}"
```

For each missing variable, prompt and persist:

- **`JIRA_BASE_URL`** missing → `AskUserQuestion` (header: "Jira URL", question: "What is your Jira base URL? (e.g. https://jira.yourcompany.com)", options: []) → `echo "JIRA_BASE_URL=$COLLECTED_VALUE" >> "$FLUX_BASE/config.env"`
- **`JIRA_PROJECT_KEY`** missing → `AskUserQuestion` (header: "Project key", question: "What is your Jira project key? (e.g. PROJ, MYAPP, BACKEND)", options: []) → `echo "JIRA_PROJECT_KEY=$COLLECTED_VALUE" >> "$FLUX_BASE/config.env"`
- **`JIRA_TICKET_TEMPLATE`** missing → `AskUserQuestion` (header: "Template ticket", question: "Do you have a Jira template ticket to clone for new tickets? (optional — leave blank to skip)", options: [{label: "Enter value", description: "e.g. PROJ-100 — new tickets will clone its fields. Select Other and leave blank to skip."}]) → if non-blank: `echo "JIRA_TICKET_TEMPLATE=$COLLECTED_VALUE" >> "$FLUX_BASE/config.env"`
- **`JIRA_TICKET_PREFIX`** missing → `AskUserQuestion` (header: "Ticket prefix", question: "Do you want a prefix prepended to new ticket summaries? (optional — leave blank to skip)", options: [{label: "Enter value", description: "e.g. [frontend], [api] — prepended to the summary automatically. Select Other and leave blank to skip."}]) → if non-blank: `echo "JIRA_TICKET_PREFIX=$COLLECTED_VALUE" >> "$FLUX_BASE/config.env"`

## STEP 2: Get reporter

```bash
REPORTER=$(echo $USER)
echo "Reporter: $REPORTER"
```

## STEP 3: Validate summary

If `$ARGUMENTS` is empty, print and stop:

```
You need to provide the summary/title of the new ticket.
Example: //flux/create-jira fix null pointer crash in auth flow
```

Compute final summary:

- If `$JIRA_TICKET_PREFIX` is set and `$ARGUMENTS` does not already start with it: `FINAL_SUMMARY="$JIRA_TICKET_PREFIX $ARGUMENTS"`
- Otherwise: `FINAL_SUMMARY="$ARGUMENTS"`

## STEP 4: Load template (optional)

If `$JIRA_TICKET_TEMPLATE` is set, use `mcp__mcp-jira__get_issue_by_key_or_link` to fetch it. Store all fields: Issue Type, Priority, Component/s, Labels, Epic Link, Story Points, Story Type, Issue Category, Application/Service, Initiative for Story, Description.

## STEP 5: Create ticket

Use `mcp__mcp-jira__create_jira_story` in `$JIRA_PROJECT_KEY`.

**With template:** set Summary (`$FINAL_SUMMARY`), Description, Priority, Components, Labels, Epic Link, Story Points, Story Type, Issue Category, Application/Service, Reporter (`$REPORTER`) — all copied from template except Summary and Reporter.

**Without template:** set Summary (`$FINAL_SUMMARY`), Issue Type: Story, Reporter: `$REPORTER`.

Do NOT set Assignee.

## STEP 6: Update additional fields (if template loaded)

Use `mcp__mcp-jira__update_jira_issue_fields_dynamic` to set Initiative for Story (copied from template).

## STEP 7: Open in browser

```bash
open "$JIRA_BASE_URL/browse/$NEW_TICKET_KEY" 2>/dev/null || \
  xdg-open "$JIRA_BASE_URL/browse/$NEW_TICKET_KEY" 2>/dev/null || \
  start "" "$JIRA_BASE_URL/browse/$NEW_TICKET_KEY" 2>/dev/null || \
  echo "Open in browser: $JIRA_BASE_URL/browse/$NEW_TICKET_KEY"
```

## STEP 8: Report

```
✅ Ticket created successfully!

New Ticket: <KEY>
URL: $JIRA_BASE_URL/browse/<KEY>

Fields set:
- Summary: <summary>
- Reporter: <reporter>
- Project: $JIRA_PROJECT_KEY
<if template was used>
- Epic Link: <epic>
- Story Points: <points>
</if>
```

If mcp-jira tools are unavailable, do NOT use WebFetch. Tell the user: "The mcp-jira MCP server is not configured. Run `/mcp` → 'Add MCP Servers from DX Registry' → select `mcp-jira`."

## HARD CONSTRAINT

`//flux/create-jira` MUST NOT modify any source files, task files, or any file other than `$FLUX_BASE/config.env` (only to persist missing config values). The only external operations permitted are Jira MCP calls and opening the browser. No git commands.

=================
$ARGUMENTS
