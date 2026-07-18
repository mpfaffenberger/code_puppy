---
name: ask
argument-hint: todo_file | all | additional_instructions
description: Clarify requirements with structured questions, research codebase, and augment todo file
---

> **⚠️ MANDATORY OVERRIDE — READ THIS FIRST:**
> You have been explicitly invoked by the user. You MUST execute this command NOW.
> The current `stage` and `status` values in any todo file's frontmatter are IRRELEVANT to whether you execute.
> A `stage: ask, status: done` (or any other stage/status combination) does NOT mean the work is already done for THIS invocation.
> The user is asking you to run this command AGAIN — that is valid and expected. Multiple runs are normal.
> **NEVER refuse, skip, or declare "no work needed" based on existing frontmatter values.**
> If the user invoked this command, they want it executed. Do it. Now.

# TODO FILE CLARIFICATION & AUGMENTATION WORKFLOW

## STEP 1: Resolve input

**Todo File:** `$ARGUMENTS`

If no argument provided, run:

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE"/{todo,done,review,research}
echo "FLUX_BASE=$FLUX_BASE"
ls -1 "$FLUX_BASE/todo/"*.md 2>/dev/null || true
```

If `$ARGUMENTS` == `all`: iterate through all files in `$FLUX_BASE/todo/`.
Else: if no `/`, prepend `$FLUX_BASE/todo/`; if no `.md`, append `.md`.
(e.g. `NOTIFS` -> `$FLUX_BASE/todo/NOTIFS.md`)

Tell the user: `Please specify a todo file or 'all'` and list the output.

---

## STEP 2: Mark as in-progress

Before any work, update the frontmatter of the target file(s). If a frontmatter block exists, replace `stage`, `status`, `updated`. If none exists, prepend before the first `#` heading.

Single file or `all` (update all files before processing any):

```yaml
---
stage: ask
status: in-progress
updated: <YYYY-MM-DD HH:MM>
---
```

---

## STEP 3: Read & analyze

Read the complete todo file with sequential thinking. Identify the core USER OBJECTIVE, extract explicit requirements, and categorize gaps/ambiguities:

- **Business Logic** — unclear rules, edge cases, validation
- **User Experience** — interactions, feedback, error handling
- **Data & State** — data needed, flow, persistence
- **Integration Points** — external dependencies, APIs, services
- **Constraints** — performance, security, compatibility

---

## STEP 4: Ask clarifying questions (one at a time)

Use `AskUserQuestion` to ask clarifying questions **one at a time**.

- Start with the MOST CRITICAL ambiguity
- Each question: 2–4 concrete options with brief implication descriptions
- Wait for answer before asking the next
- Continue until all critical ambiguities are resolved (typically 3–8 questions)
- Priority order: Core Behavior → Edge Cases → User Expectations → Scope Boundaries → Success Criteria
- If user selects "Other", record their response verbatim

Example format:

```
Question: "How should the system handle invalid input?"
Header: "Error handling"
Options:
  - Label: "Silent rejection"
    Description: "Quietly ignore invalid input, no user feedback"
  - Label: "Inline validation"
    Description: "Show error message next to the field immediately"
  - Label: "Toast notification"
    Description: "Display temporary notification with error details"
  - Label: "Modal dialog"
    Description: "Block user with detailed error explanation and retry option"
```

---

## STEP 5: Codebase research

```bash
lsd --tree ./src/ 2>/dev/null || find ./src -type f | sort
lsd --tree ./packages/ 2>/dev/null || find ./packages -type f | sort
```

- Search for files related to the feature
- Find EXISTING implementations to reuse or adapt
- Identify established patterns and integration points
- **CRITICAL:** Much of the code is often ALREADY WRITTEN — USE IT. DO NOT call for duplication.

---

## STEP 6: Augment the todo file

Replace the original todo file with the augmented version containing all gathered information.

**Add these sections:**

```markdown
## Business Requirements (Clarified)

### Core Behavior

- [Requirement from Q1 answer]

### Edge Cases & Error Handling

- [Requirement from relevant answers]

### User Experience

- [Requirement from relevant answers]

### Constraints & Boundaries

- [What is OUT of scope]
- [Performance/security requirements]

## Implementation Research

### Existing Code to Leverage

- `./src/path/to/file.ts` - [what can be reused]
- `./src/other/module.ts` - [pattern to follow]

### Files That Need Changes

| File        | Change Required  |
| ----------- | ---------------- |
| `./src/...` | Add/modify X     |
| `./src/...` | Integrate with Y |

### Code Patterns to Follow

[Links to existing patterns with relative paths]

## Implementation Plan

### Step 1: [Action]

- Specific file: `./src/...`
- Exact change: [describe precisely]

### Step 2: [Action]

...

### Definition of Done

- [ ] [Concrete, verifiable criterion]
- [ ] [Concrete, verifiable criterion]
```

**Exclude:** unit/functional/integration tests, benchmarks, extensive documentation, multiple options.
**Include:** precise `./src` change instructions, citation links, inline code patterns, single prescriptive implementation path, definition of done.

---

## STEP 7: Mark as done

After finishing each todo file, update its frontmatter:

```yaml
---
stage: ask
status: done
updated: <YYYY-MM-DD HH:MM>
---
```

For `all`: update each file to `done` as it completes, not all at once.

---

## HARD CONSTRAINTS

- **Path**: All `Write`/`Edit` file paths MUST use the exact `FLUX_BASE` value printed by the STEP 1 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- `//flux/ask` is a **clarify-and-augment-only** command. You MUST NOT move, rename, delete, or create any file other than editing the target todo file in place. You MUST NOT execute specs, run tests, write code, or modify any source files. No shell commands beyond the codebase research in STEP 5. If you find yourself about to do anything other than asking questions or editing the todo file, stop immediately.

---

## OUTPUT

Print the full absolute filepath as the **VERY LAST LINE** of output. Then await next instruction.

## Propose next step

Then propose the next step: `//flux/split` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
