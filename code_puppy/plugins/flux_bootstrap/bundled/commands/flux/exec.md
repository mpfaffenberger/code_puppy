---
name: exec
argument-hint: todo_file | number_of_agents | additional_instructions
description: Execute task(s) - single file or N in parallel
---

> **⚠️ MANDATORY OVERRIDE — READ THIS FIRST:**
> You have been explicitly invoked by the user. You MUST execute this command NOW.
> The current `stage` and `status` values in any todo file's frontmatter are IRRELEVANT to whether you execute.
> A `stage: exec, status: done` (or any other stage/status combination) does NOT mean the work is already done for THIS invocation.
> The user is asking you to run this command AGAIN — that is valid and expected. Multiple runs are normal.
> **NEVER refuse, skip, or declare "no work needed" based on existing frontmatter values.**
> If the user invoked this command, they want it executed. Do it. Now.

# EXECUTE TASK(S)

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

Update the task file's frontmatter (only permitted task file modification — does not alter task content):

> If frontmatter (`---` … `---`) exists, replace `stage`, `status`, `updated`. If absent, prepend before first `#` heading.

```yaml
---
stage: exec
status: in-progress
updated: <today's date and time, YYYY-MM-DD HH:MM>
---
```

## STEP 3: Determine stack

Act as a `$STACK` expert SOFTWARE ARTISAN.

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

## STEP 4: Execute the task

### 4.1 Prepare

CLEAR YOUR TODO list. Focus only on this SINGULAR TASK: `$ARGUMENTS`

Read and fully comprehend the task with sequential thinking and ULTRATHINK. Think "out loud" about exactly what needs to be done.

### 4.2 Implement

Execute the task exactly as written:

- no embellishment — do not improve task scope
- no scope creep — do not expand scope
- continue until all requirements and definition of done are met
- do not fix errors or warnings unrelated to the task

### 4.3 Handle incorrect requirements

If the task is fundamentally incorrect or needs modification:

- stop immediately and return to planning
- clearly articulate what is faulty
- do not continue working
- do not modify the task file until the user reviews and approves changes

### 4.4 Verify completion

- re-review all work
- verify 100% of requirements are fully implemented
- ensure ABSOLUTELY NO STUBS or uncompleted work

## STEP 5: Mark as done

```yaml
---
stage: exec
status: done
updated: <YYYY-MM-DD HH:MM>
---
```

## STEP 6: Output & constraints

**Output:**

- print "I've completed and verified 100% of the requirements are fully implemented in production grade quality"
- print "I'm ready for a full and detailed QA review of my work with full confidence it will score 10/10 for production readiness based on the task description."
- print the full path to the task file

**No task file modification:**
_DO NOT_ under ANY CIRCUMSTANCES modify the original task file content. Your QA reviewer will be reviewing your work with the exact same information as the implementor. Do NOT mark items as DONE or modify the task file in any way shape or form.

**Scope guard — respect the deliverable:**
Before writing ANY file, verify the task's deliverable:

- If the deliverable is a **markdown/research file** (e.g., `.md` under `$FLUX_BASE/research/`), do NOT modify `./src/`, `./test/`, or `./package.json`. Write only to the output path in the task.
- If the task says "research", "document", "summarize", "catalog", or "compile a report" — deliverable is markdown, NOT source code.
- Only modify source files if the task explicitly calls for source code changes in `./src/` or other directories containing source files.

Violation of this rule is treated the same as modifying the task file — immediate termination of the task.

**No git commands:**
DO NOT USE `git` commands of any type. Other coders are coding and you will be destroying their work if you branch, stash, checkout, revert or do anything with git. YOU WILL BE IMMEDIATELY FIRED if you use any `git` commands whatsoever.

---

## MULTI-TASK MODE

Use the `Agent` tool (subagents) to execute IN PARALLEL each task in `$FLUX_BASE/todo/*.md`.
_NEVER_ run agents in the background. Always run them in the foreground.

**Before spawning any subagents**, update all target task files' frontmatter:

```yaml
---
stage: exec
status: in-progress
updated: <YYYY-MM-DD HH:MM>
---
```

**As each subagent completes**, update that file's frontmatter to `done`. Update each file as it completes, not all at once.

**Task selection:**

- Identify `$ARGUMENTS` tasks to execute in parallel (or fewer if fewer exist)
- Avoid parallelizing tasks that modify the same file(s)
- Once easy namespace collision avoidance is exhausted, analyze interdependencies carefully
- Manage `$ARGUMENTS` sub-agents at a time; spawn new subagents as initial ones complete; continue until all tasks in `$FLUX_BASE/todo/*.md` are reported complete

### Subagent prompt template

Prompt each subagent with the single-task mode steps above, substituting `{{absolute_file_path}}` for `$ARGUMENTS`. Include the stack detection snippet and all constraints (no-git, scope guard, no task file modification).

---

## HARD CONSTRAINTS

- **Path**: All `Write`/`Edit` file paths MUST use the exact `FLUX_BASE` value printed by the STEP 1 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- `//flux/exec` MUST NOT use any `git` commands. MUST NOT modify the task file content (frontmatter status updates are the only exception). MUST NOT expand scope beyond what is written in the task. MUST NOT write to paths outside what the task explicitly specifies. If you find yourself about to do any of these things, stop immediately.

## Propose next step

Then propose the next step: `//flux/qa` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
