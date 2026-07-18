---
name: config
description: Create or update the flux config.env with settings used by the flux command suite
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

**File exists** — check the mandatory key (`TEST_CMD`):

- **Present** → display summary:

  ```
  TEST_CMD = <value>
  ```

  `ask_user_question` — question: "Config looks good. Do you want to update any values?" / header: "Update config" / options: `Yes, update values` | `No, looks good`

  - No → stop. Yes → STEP 2 (update flow).

- **Missing** → proceed to STEP 2 (update flow).

**File missing** → proceed to STEP 2 (new file flow).

---

## STEP 2: Collect values

### 2a. New file flow

If the config file did not exist, do NOT ask questions. Write the file immediately with a blank value and an inline comment:

```bash
cat > "$FLUX_BASE/config.env" << 'CONFIG_EOF'
# Command that runs your test suite (e.g. bun run test:quiet, npm test, pytest -q, cargo test -- --quiet)
# Tip: chain lint + tests together, e.g. bun run lint && bun run test:quiet
TEST_CMD=
CONFIG_EOF
```

```bash
echo "=== $FLUX_BASE/config.env ==="
cat "$FLUX_BASE/config.env"
```

`ask_user_question` — question: "Config file created at `$FLUX_BASE/config.env`. Please open it, fill in your value, then re-run `/flux/config` to verify. Ready to continue?" / header: "Edit config" / options:

- `Done, verify now` — re-read `$FLUX_BASE/config.env`, jump to STEP 4
- `Exit` — stop

### 2b. Update flow

Runs only when the user chose "Yes, update values" from STEP 1, or when the key is missing. Ask via `ask_user_question` with options `Keep current` (pre-filled) and `New value - use Other below` (free-text via Other input).

**TEST_CMD**: "What command runs your test suite?" / header: "TEST_CMD"

- `Keep current` → description: `Current value: <TEST_CMD>`
- `New value - use Other below` → description: `e.g. bun run test:quiet, npm test, pytest -q — or chain with lint: bun run lint && bun run test:quiet`
- Store result as `TEST_CMD_VALUE`.

---

## STEP 3: Write config (update flow only)

```bash
cat > "$FLUX_BASE/config.env" << 'CONFIG_EOF'
TEST_CMD=<TEST_CMD_VALUE>
CONFIG_EOF
```

Rules: use the actual collected value (not the placeholder name), overwrite completely.

```bash
echo "=== $FLUX_BASE/config.env ==="
cat "$FLUX_BASE/config.env"
```

---

## STEP 4: Confirm

Parse `$FLUX_BASE/config.env` (strip comments and blank lines) and print:

```
 $FLUX_BASE/config.env ready:

  TEST_CMD = <value or "(not set)">

All //flux commands will read this file automatically via:
  source "$FLUX_BASE/config.env" 2>/dev/null
```

## HARD CONSTRAINT

`/flux/config` MUST NOT modify any source files, task files, or any file outside of `$FLUX_BASE/config.env`. The only permitted file operation is writing/overwriting `$FLUX_BASE/config.env`. No git commands. No task creation.
