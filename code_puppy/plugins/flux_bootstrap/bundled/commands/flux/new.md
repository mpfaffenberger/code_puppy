---
name: new
argument-hint: task_description | JIRA_ticket_id
description: Create a new task file from a description or Jira ticket
allowed-tools: mcp__mcp-jira__get_issue_by_key_or_link, Write, AskUserQuestion, Bash
---

# Create New Task

**Argument:** `$ARGUMENTS`

## STEP 1: Check for leftover task files

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
echo "FLUX_BASE=$FLUX_BASE"
ls "$FLUX_BASE/todo/"*.md 2>/dev/null || true
```

If files are found, use `AskUserQuestion`: "Found existing task files in `$FLUX_BASE/todo/`. What would you like to do with them?"

- `Discard them` → `rm "$FLUX_BASE/todo/"*.md`
- `Back them up` → `mkdir -p "$FLUX_BASE/todo-bkp" && mv "$FLUX_BASE/todo/"*.md "$FLUX_BASE/todo-bkp/"`

## STEP 2: Detect argument type

Pattern for Jira tickets: `^[A-Z]+-[0-9]+$` (e.g. `PROJECT-456`). Lowercase or plain descriptions do NOT match.

## STEP 3: Create task file

### If `$ARGUMENTS` matches Jira pattern

#### 3.1 Check if Jira MCP is available

**If `mcp__mcp-jira__get_issue_by_key_or_link` is NOT available:**

Inform the user:

> "The Jira MCP server is not configured. To fetch ticket details, please install it: run `/mcp` → Add MCP Servers from DX Registry → **mcp-jira**. Then re-run this command."

**Stop. Do not proceed further.**

---

**If `mcp__mcp-jira__get_issue_by_key_or_link` IS available:**

#### 3.2 Fetch the ticket

```
mcp__mcp-jira__get_issue_by_key_or_link(issue_key_or_link: "$ARGUMENTS")
```

Read the **Summary**, **Description**, and **Acceptance Criteria** fields from the response. Convert any Jira markup to Markdown (see conversion table below).

#### 3.3 Write task file at `$FLUX_BASE/todo/<TICKET-ID>.md`

```markdown
---
stage: new
status: done
updated: <YYYY-MM-DD HH:MM>
---

# <TICKET-ID>: <summary>

## Description

<description — converted from Jira markup to Markdown>

## Acceptance Criteria

<omit this section entirely if not present on the ticket>

## Source

- **Jira ticket:** <TICKET-ID>
- **Status:** <status>
- **Priority:** <priority>
```

### If `$ARGUMENTS` does NOT match Jira pattern

#### 3.1 Generate filename

Take 3-4 significant words, UPPER_SNAKE_CASE, append `.md` (e.g. "add dark mode toggle" → `DARK_MODE.md`)

#### 3.2 Clarify if needed

If requirements are unclear, use `AskUserQuestion` to clarify before writing.

#### 3.3 Write `$FLUX_BASE/todo/<FILENAME>.md`

```markdown
---
stage: new
status: done
updated: <YYYY-MM-DD HH:MM>
---

# <Title derived from $ARGUMENTS — Title Case, human-readable (e.g. "Add Dark Mode Toggle")>

## Description

$ARGUMENTS

## Acceptance Criteria

- [ ] <To be clarified>
```

## HARD CONSTRAINTS

- **Path**: The `Write` file path MUST use the exact `FLUX_BASE` value printed by the STEP 1 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- **Capture-only**: You MUST NOT read, edit, delete or move any file other than the single task file being created in `$FLUX_BASE/todo/`. No source files, no config files, no other flux files — nothing. If you find yourself about to touch anything else, stop immediately and output the task file instead.

## OUTPUT

```
Task created: $FLUX_BASE/todo/<FILENAME>.md
```

After creating the task file, start a new session by writing `$FLUX_BASE/session.env`:

```bash
SESSION_TS=$(date +%Y-%m-%d-%H-%M)
echo "SESSION_TS=$SESSION_TS" > "$FLUX_BASE/session.env"
echo "Session started: $SESSION_TS"
```

Then propose the next step: `//flux/ask` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

## JIRA MARKUP → MARKDOWN

| Jira              | Markdown      |
| ----------------- | ------------- |
| `*bold*`          | `**bold**`    |
| `_italic_`        | `*italic*`    |
| `{{code}}`        | `` `code` ``  |
| `{code}...{code}` | ` ```...``` ` |
| `h1. Title`       | `# Title`     |
| `h2. Title`       | `## Title`    |
| `* item`          | `- item`      |
| `# item`          | `1. item`     |
| `[text\|url]`     | `[text](url)` |

=================
$ARGUMENTS
