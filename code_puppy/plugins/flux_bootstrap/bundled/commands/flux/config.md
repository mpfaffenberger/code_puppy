---
name: config
description: Create or update the flux config.env with settings used by the flux command suite
allowed-tools: AskUserQuestion, Bash
---

# Configure Flux Settings

## STEP 1: Check for existing config

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
echo "FLUX_BASE=$FLUX_BASE"
```

```bash
cat "$FLUX_BASE/config.env" 2>/dev/null && echo "__EXISTS__" || echo "__MISSING__"
```

**File exists** — check mandatory keys (`TEST_CMD`, `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`):

- **All present** → display summary:

  ```
  TEST_CMD             = <value>
  JIRA_BASE_URL        = <value>
  JIRA_PROJECT_KEY     = <value>
  JIRA_TICKET_TEMPLATE = <value or "(not set)">
  JIRA_TICKET_PREFIX   = <value or "(not set)">
  ```

  `AskUserQuestion` — question: "Config looks good. Do you want to update any values?" / header: "Update config" / options: `Yes, update values` | `No, looks good`

  - No → stop. Yes → STEP 2 (update flow).

- **Any key missing** → note existing keys, proceed to STEP 2 (update flow, pre-fill existing values).

**File missing** → proceed to STEP 2 (new file flow).

---

## STEP 2: Collect values

### 2a. New file flow

If the config file did not exist, do NOT ask questions. Write the file immediately with blank values and inline comments:

```bash
cat > "$FLUX_BASE/config.env" << 'CONFIG_EOF'
# Command that runs your test suite (e.g. bun run test:quiet, npm test, pytest -q, cargo test -- --quiet)
# Tip: chain lint + tests together, e.g. bun run lint && bun run test:quiet
TEST_CMD=

# Jira base URL — always https://jira.walmart.com for Walmart projects
JIRA_BASE_URL=https://jira.walmart.com

# Your Jira project key — new tickets will be created here (e.g. PROJ, MYAPP — uppercase only)
JIRA_PROJECT_KEY=

# (optional) Jira template ticket to clone when creating new tickets (e.g. PROJ-100)
JIRA_TICKET_TEMPLATE=

# (optional) Prefix prepended to new Jira ticket summaries (e.g. [frontend])
JIRA_TICKET_PREFIX=
CONFIG_EOF
```

```bash
echo "=== $FLUX_BASE/config.env ==="
cat "$FLUX_BASE/config.env"
```

`AskUserQuestion` — question: "Config file created at `$FLUX_BASE/config.env`. Please open it, fill in your values, then re-run `//flux/config` to verify. Ready to continue?" / header: "Edit config" / options:

- `Done, verify now` — re-read `$FLUX_BASE/config.env`, jump to STEP 4
- `Exit` — stop

### 2b. Update flow

Runs only when user chose "Yes, update values" from STEP 1, or when keys are missing. Ask each key one at a time via `AskUserQuestion` with options `Keep current` (pre-filled) and `New value - use Other below` (free-text via Other input).

**TEST_CMD**: "What command runs your test suite?" / header: "TEST_CMD"

- `Keep current` → description: `Current value: <TEST_CMD>`
- `New value - use Other below` → description: `e.g. bun run test:quiet, npm test, pytest -q — or chain with lint: bun run lint && bun run test:quiet`
- Store result as `TEST_CMD_VALUE`.

**JIRA_BASE_URL**: Do NOT ask. Always set `JIRA_BASE_URL_VALUE=https://jira.walmart.com`.

**JIRA_PROJECT_KEY**: "What is your Jira project key?" / header: "JIRA_PROJECT_KEY"

- `Keep current` → description: `Current value: <JIRA_PROJECT_KEY>`
- `New value - use Other below` → description: `e.g. PROJ, MYAPP, BACKEND (uppercase only)`
- Store result as `JIRA_PROJECT_KEY_VALUE`.

**JIRA_TICKET_TEMPLATE** (optional): "Jira template ticket to clone for new tickets? Leave blank to skip." / header: "Template ticket"

- `Keep current` → description: `Current value: <JIRA_TICKET_TEMPLATE or "(not set)">`
- `New value - use Other below` → description: `e.g. PROJ-100. Type blank to clear.`
- Store as `JIRA_TEMPLATE_VALUE`. If blank, omit this key.

**JIRA_TICKET_PREFIX** (optional): "Prefix to prepend to new Jira ticket summaries? Leave blank to skip." / header: "Ticket prefix"

- `Keep current` → description: `Current value: <JIRA_TICKET_PREFIX or "(not set)">`
- `New value - use Other below` → description: `e.g. [frontend]. Type blank to clear.`
- Store as `JIRA_TICKET_PREFIX_VALUE`. If blank, omit this key.

---

## STEP 3: Write config (update flow only)

```bash
cat > "$FLUX_BASE/config.env" << 'CONFIG_EOF'
TEST_CMD=<TEST_CMD_VALUE>
JIRA_BASE_URL=<JIRA_BASE_URL_VALUE>
JIRA_PROJECT_KEY=<JIRA_PROJECT_KEY_VALUE>
JIRA_TICKET_TEMPLATE=<JIRA_TEMPLATE_VALUE>
JIRA_TICKET_PREFIX=<JIRA_TICKET_PREFIX_VALUE>
CONFIG_EOF
```

Rules: use actual collected values (not placeholder names), omit blank/skipped lines, overwrite completely.

```bash
echo "=== $FLUX_BASE/config.env ==="
cat "$FLUX_BASE/config.env"
```

---

## STEP 4: Confirm

Parse `$FLUX_BASE/config.env` (strip comments and blank lines) and print:

```
✅ $FLUX_BASE/config.env ready with X key(s):

  TEST_CMD             = <value or "(not set)">
  JIRA_BASE_URL        = <value or "(not set)">
  JIRA_PROJECT_KEY     = <value or "(not set)">
  JIRA_TICKET_TEMPLATE = <value or "(not set)">
  JIRA_TICKET_PREFIX   = <value or "(not set)">

All //flux commands will read this file automatically via:
  source "$FLUX_BASE/config.env" 2>/dev/null
```

## HARD CONSTRAINT

`//flux/config` MUST NOT modify any source files, task files, or any file outside of `$FLUX_BASE/config.env`. The only permitted file operation is writing/overwriting `$FLUX_BASE/config.env`. No git commands. No task creation.
