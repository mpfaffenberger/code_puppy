---
name: split
argument-hint: task_file | additional_instructions
description: Decompose a large task into smaller, single-session tasks.
---

# DECOMPOSE A LARGE TASK

**Argument:** `$ARGUMENTS`

## STEP 1: Mark as in-progress

Before anything else, update the input task file's frontmatter (replace existing values, or prepend if no frontmatter exists):

```yaml
---
stage: split
status: in-progress
updated: <YYYY-MM-DD HH:MM>
---
```

## STEP 2: Resolve path & setup

If `$ARGUMENTS` has no `/`, prepend `$FLUX_BASE/todo/`. If no `.md`, append `.md`. (e.g. `NOTIFS` → `$FLUX_BASE/todo/NOTIFS.md`)

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
echo "FLUX_BASE=$FLUX_BASE"
```

## STEP 3: Decompose into subtask files

### 3.1 Choose a prefix

Short, uppercase, human-meaningful, fewer than 8 characters. Example: tasks about "in production" stubs → `IN_PROD_1.md`, `IN_PROD_2.md`, etc.

### 3.2 Write subtask files

Output files:

- `$FLUX_BASE/todo/PREFIX_1.md`
- `$FLUX_BASE/todo/PREFIX_2.md`
- `$FLUX_BASE/todo/PREFIX_3.md`
- ... etc.

Each task must be:

- Focused on a single area of concern
- Achievable in **one Claude session** — after writing, ask yourself "is this really doable in one session?" If no, split into A/B/C variants
- Free of research tasks (all research is done prior to execution)
- Free of tests and benchmarks (see 3.3 and 3.4)

**Frontmatter (required at top of every subtask file):**

```yaml
---
stage: new
status: done
updated: <YYYY-MM-DD HH:MM>
---
```

**Body must include:**

- `OBJECTIVE:` — what this task accomplishes
- Numbered subtasks: SUBTASK1, SUBTASK2, SUBTASK3...
- For each: what changes, where it changes, why it changes
- Clear definition of done
- Research notes and locations of relevant docs/source code

### 3.3 No tests

Another team owns tests. Writing any test code makes their work harder. Each task file must explicitly state: no tests to be written.

### 3.4 No benchmarks

Another team owns benchmarks. Writing any benchmark code makes their work harder. Each task file must explicitly state: no benchmarks to be written.

## STEP 4: Preserve the original task file

Update the original task file's frontmatter to mark it as split, then move it to the session done directory.

1. Update the original file's frontmatter (replace `stage`, `status`, `updated` — keep body unchanged):

```yaml
---
stage: split
status: complete
updated: <YYYY-MM-DD HH:MM>
---
```

2. Read the session timestamp and move to the session done subdirectory:

```bash
SESSION_TS=$(grep '^SESSION_TS=' "$FLUX_BASE/session.env" 2>/dev/null | cut -d= -f2)
SESSION_TS="${SESSION_TS:-$(date +%Y-%m-%d-%H-%M)}"
mkdir -p "$FLUX_BASE/done/$SESSION_TS"
mv "<original_task_file_path>" "$FLUX_BASE/done/$SESSION_TS/"
```

The original file is preserved in `done/$SESSION_TS/` as an audit trail of the pre-split specification.

## HARD CONSTRAINTS

- **Path**: All `create_file` file paths MUST use the exact `FLUX_BASE` value printed by the STEP 2 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- `/flux/split` is a **decompose-only** command. You MUST NOT modify any source files, run any tests, or touch any file outside of `$FLUX_BASE/todo/`. The only file operations allowed are: writing the new subtask files and deleting the original task file. If you find yourself about to do anything else, stop immediately.

## PROPOSE NEXT STEP

Then propose the next step: `/flux/aug` (include arguments if needed).

Valid `//flux` commands: `/flux/config`, `/flux/new`, `/flux/ask`, `/flux/split`, `/flux/aug`, `/flux/exec`, `/flux/qa`, `/flux/tests`, `/flux/commit`, `/flux/create-pr`, `/flux/review`, `/flux/address-feedback`, `/flux/status`, `/flux/auto-pilot`, `/flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
