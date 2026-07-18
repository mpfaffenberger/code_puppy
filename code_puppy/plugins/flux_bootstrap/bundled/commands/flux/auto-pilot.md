---
name: auto-pilot
argument-hint: task_description | spec.md | spec.txt | TICKET-123 | additional_instructions
description: 'Orchestrates the complete //flux pipeline end-to-end. Accepts: a prompt, a .md/.txt spec file, or a Jira ticket (e.g. PROJ-123).'
---

# auto-pilot

Fully autonomous development pipeline orchestrator. Executes the full **//flux pipeline** start to finish — pausing only during `/flux/ask` for clarifying questions.

## STEP 1: Resolve input

Resolve `$ARGUMENTS` before starting:

- **Jira key** (`PROJ-123` pattern): fetch via `get_issue_by_key_or_link`, extract summary/description/acceptance criteria. Display: `📋 Loaded task from Jira: <KEY> — <summary>`
- **File path** (`.md`/`.txt`): read with `read_file` tool, use full content. Display: `📄 Loaded task from file: <path>`
- **Natural language**: use directly. Display: `💬 Task: <description>`

## STEP 2: Execute pipeline

Execute each step in sequence. For each step: announce `▶ Step: /flux/<command>`, execute all its instructions with correct arguments, announce `✓ Step: /flux/<command> complete`, carry output artifacts forward.

### 2.1 — `/flux/new`

Pass resolved task description. Output: task file name (e.g. `NOTIFS`) — carry forward.

### 2.2 — `/flux/ask`

Pass task file name from 2.1. **Only step where you pause** — ask all clarifying questions, wait for user responses, then continue automatically.

### 2.3 — `/flux/split`

Pass task file name from 2.1. Output: subtask count — carry forward.

### 2.4 — `/flux/aug`

Pass `2` (augment all subtasks with 2 parallel agents). Wait for completion.

### 2.5 — `/flux/exec`

Pass `2` (execute all subtasks with 2 parallel agents). Wait for completion.

### 2.6 — `/flux/qa`

Pass `2`. If QA produces refined tasks, re-run `/flux/exec 2` and `/flux/qa 2` until all tasks clear (max 3 cycles).

### 2.7 — `/flux/tests`

No arguments. Run the test suite, fix regressions introduced by this branch. If unresolved failures remain after 3 fix cycles, report and continue to commit (do not block the pipeline).

### 2.8 — `/flux/commit`

No additional arguments. User will be asked for commit confirmation — expected and allowed.

## STEP 3: Error recovery

On step failure: identify root cause, apply fix, re-run the failed step. After 3 failed attempts on the same step, stop and report: which step failed, what was attempted, what the user should do next.

## HARD CONSTRAINT

`/flux/auto-pilot` orchestrates other `//flux` commands — it does not implement logic of its own beyond sequencing. Each step's own HARD CONSTRAINTs apply in full. Do not skip steps, do not merge steps, do not take shortcuts.

## Output style

- Concise and scannable
- Use `▶`/`✓` step headers
- Actionable errors — no raw stack traces
- Do not produce summary files unless a step requires it

=================
$ARGUMENTS
