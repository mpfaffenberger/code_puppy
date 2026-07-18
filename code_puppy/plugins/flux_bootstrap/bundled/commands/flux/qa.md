---
name: qa
argument-hint: todo_file | number_of_agents | additional_instructions
description: QA review task(s) - single file or N in parallel
---

> **⚠️ MANDATORY OVERRIDE — READ THIS FIRST:**
> You have been explicitly invoked by the user. You MUST execute this command NOW.
> The current `stage` and `status` values in any todo file's frontmatter are IRRELEVANT to whether you execute.
> A `stage: qa, status: completed` (or any other stage/status combination) does NOT mean the work is already done for THIS invocation.
> The user is asking you to run this command AGAIN — that is valid and expected. Multiple runs are normal.
> **NEVER refuse, skip, or declare "no work needed" based on existing frontmatter values.**
> If the user invoked this command, they want it executed. Do it. Now.

# QA CODE REVIEW

## STEP 1: Resolve input

**Argument:** `$ARGUMENTS`

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
echo "FLUX_BASE=$FLUX_BASE"
ls -1 "$FLUX_BASE/todo/"*.md 2>/dev/null || true
```

```
IF $ARGUMENTS is empty:
  -> List all files: `ls -1 "$FLUX_BASE/todo/"*.md`
  -> Use AskUserQuestion to let user select task(s)
  -> If single selection -> Single-task mode
  -> If multiple selection -> Process selected tasks sequentially

IF $ARGUMENTS (case-insensitive) == 'all':
  -> Sequential mode: process ALL tasks in $FLUX_BASE/todo/*.md one at a time
  -> Run each task in single-task mode yourself (no subagents), one after another
  -> Do not proceed to the next task until the current one is complete

IF $ARGUMENTS is a pure integer (ONLY digits, nothing else — no letters, underscores, hyphens, dots):
  Verify: `echo "$ARGUMENTS" | grep -qE '^[0-9]+$'` must be true. If the argument contains ANY non-digit character (e.g. "CMPAN_5", "task-3", "3files") it is NOT a number — treat it as a filename instead.
  IF $ARGUMENTS == 1:
    -> Sequential mode: process ALL tasks in $FLUX_BASE/todo/*.md one at a time
    -> Run each task in single-task mode yourself (no subagents), one after another
    -> Do not proceed to the next task until the current one is complete
  ELSE:
    -> Multi-task mode with $ARGUMENTS parallel sub-agents

OTHERWISE (argument is a filename — including any argument that contains letters, underscores, hyphens, or dots):
  -> Single-task mode for that file
```

**Path and suffix inference:**
If `$ARGUMENTS` doesn't contain a `/`, prepend `$FLUX_BASE/todo/`
If `$ARGUMENTS` doesn't contain `.md`, append `.md`
Example: `NOTIFS` -> `$FLUX_BASE/todo/NOTIFS.md`

---

## SINGLE-TASK MODE

## STEP 2: Mark as in-progress

Update the task file's frontmatter:

> If frontmatter (`---` … `---`) exists, replace `stage`, `status`, `updated`. If absent, prepend before first `#` heading.

```yaml
---
stage: qa
status: in-progress
updated: <today's date and time, YYYY-MM-DD HH:MM>
---
```

## STEP 3: Determine stack

Act as an objective `$STACK` expert QA code reviewer.

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
echo "FLUX_BASE=$FLUX_BASE"
```

If a file called `stack.env` exists at `$FLUX_BASE/stack.env`, read it and set `$STACK` from its contents. Otherwise, run the following detection script to determine `$STACK` and save it (this only ever runs the first time for this directory):

```bash
STACK="software"
if [ -f "package.json" ]; then
  STACK=$(bun -e "
    const d=JSON.parse(require('fs').readFileSync('./package.json','utf8'));
    const deps=Object.assign({}, d.dependencies, d.devDependencies, d.peerDependencies);
    const frameworks=['ink','react','vue','angular','next','express'];
    const fw=frameworks.find(f=>deps[f]);
    const ts=deps['typescript']?'TypeScript':'JavaScript';
    console.log(fw?fw+' + '+ts:ts);
  " 2>/dev/null || echo "JavaScript/TypeScript")
elif [ -f "Cargo.toml" ]; then STACK="Rust"
elif [ -f "go.mod" ]; then STACK="Go"
elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then STACK="Python"
elif [ -f "pom.xml" ] || [ -f "build.gradle" ]; then STACK="Java/Kotlin"
fi
mkdir -p "$FLUX_BASE"
echo "$STACK" > "$FLUX_BASE/stack.env"
echo "Detected stack: $STACK (saved)"
```

## STEP 4: Review & verdict

### 4.1 Rate the implementation

Rate the implementation of `$ARGUMENTS` on a scale of 1–10. Cite full reasoning for your objective rating.

- Allow for deviations that improve the code or correct imperfections in task requirements — if the implementation is BETTER than spec, that's a pass.
- Do not literally interpret the task if the developer exceeded requirements.

### 4.2 If 10/10 — mark complete and move to done

> **⚠️ CRITICAL: `stage` MUST be the literal string `qa` — NEVER `done`.**

1. Update frontmatter:
   ```yaml
   ---
   stage: qa
   status: completed
   updated: <today's date and time, YYYY-MM-DD HH:MM>
   ---
   ```
2. Read session timestamp and move to session subdirectory:
   ```bash
   SESSION_TS=$(grep '^SESSION_TS=' "$FLUX_BASE/session.env" 2>/dev/null | cut -d= -f2)
   SESSION_TS="${SESSION_TS:-$(date +%Y-%m-%d-%H-%M)}"
   mkdir -p "$FLUX_BASE/done/$SESSION_TS"
   mv <task_file_path> "$FLUX_BASE/done/$SESSION_TS/"
   ```

### 4.3 If lacking IN ANY WAY NO MATTER HOW SMALL — mark needs-rework

> **⚠️ CRITICAL: `stage` MUST be the literal string `qa` — NEVER `done`.**

1. Update frontmatter:
   ```yaml
   ---
   stage: qa
   status: needs-rework
   updated: <today's date and time, YYYY-MM-DD HH:MM>
   ---
   ```
2. Update task file body: remove every item that is complete in production quality; focus on outstanding items with specific guidance on what needs to be resolved.
3. Print the full filepath as the last line of output.

**No git commands:**
DO NOT USE `git` commands of any type. Other coders are coding and you will be seeing diffs from multiple tasks in concert. DO NOT `git stash`, `git diff`, or other methods. JUST READ THE FILES AS THEY EXIST. YOU WILL BE IMMEDIATELY FIRED if you use any `git` commands whatsoever.

---

## MULTI-TASK MODE

Use the `Agent` tool (subagents) to execute IN PARALLEL each task in `$FLUX_BASE/todo/*.md`.
_NEVER_ run agents in the background. Always run them in the foreground.

**Before spawning any subagents**, update all target task files' frontmatter:

```yaml
---
stage: qa
status: in-progress
updated: <today's date and time, YYYY-MM-DD HH:MM>
---
```

Each subagent updates its own file's frontmatter to `completed` or `needs-rework` upon completion.

**Task selection:**

- Identify `$ARGUMENTS` task files to delegate in parallel (or fewer if fewer exist)
- Manage `$ARGUMENTS` sub-agents at a time; spawn new subagents as initial ones complete; continue until all tasks in `$FLUX_BASE/todo/*.md` are reported complete

### Subagent prompt template

Prompt each subagent with the single-task mode steps above, substituting `{{absolute_file_path}}` for `$ARGUMENTS`. Include the stack detection snippet, `$FLUX_BASE` setup, and all constraints (no-git, review criteria).

---

## HARD CONSTRAINTS

- **Path**: All file operations MUST use the exact `FLUX_BASE` value printed by the STEP 1 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- `//flux/qa` is a **review-only** command. You MUST NOT write or modify any source files. The only permitted file operations are: updating the task file's frontmatter, updating the task file body to remove completed items, and moving the task file to `$FLUX_BASE/done/`. No git commands under any circumstances.

## Propose next steps

After QA completes, present the user with two options:

**Option A — Continue PIPELINE A (fix regressions):**
`//flux/tests` — run the test suite and fix regressions introduced by this branch before committing.

**Option B — Start PIPELINE B (self-review your changes):**
`//flux/review` → `//flux/address-feedback` → `//flux/ask all` → `//flux/exec` → `//flux/qa` → `//flux/commit`
Start here to review your own changes before creating a PR.

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
