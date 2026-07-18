# `//flux` Command Synopsis

Quick reference for arguments, options, and usage examples for every command in the `//flux` suite.

---

## `/flux/config` ⚙️ First-time setup

> **Run this once before using the `//flux` suite on a new project.** It creates the flux `config.env` file (`~/.flux/<flattened-dir>/config.env`) with your project-specific settings. All other `//flux` commands read from this file automatically.

```
/flux/config
```

| Argument  | Required | Description         |
| --------- | -------- | ------------------- |
| _(empty)_ | —        | No arguments needed |

**What it configures:**

| Key                    | Required  | Description                                                          |
| ---------------------- | --------- | -------------------------------------------------------------------- |
| `TEST_CMD`             | mandatory | Command to run your test suite (e.g. `bun run test:quiet`)           |

**Example:**

```
/flux/config
```

---

## `/flux/new`

Create a new task file from a description or Jira ticket.

```
/flux/new <description | TICKET-ID>
```

| Argument      | Required        | Description                                                                                                               |
| ------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `description` | mandatory       | Natural language description of the task                                                                                  |
| `TICKET-ID`   | mandatory (alt) | Jira ticket key (e.g. `MYPROJ-123`, `CLIAPP-456`) — fetches summary, description, and acceptance criteria automatically |

**Examples:**

```
/flux/new "Add real-time notifications to the sidebar"
/flux/new MYPROJ-123
/flux/new CLIAPP-456
```

---

## `/flux/ask`

Clarify requirements via structured questions, then augment the task file with research and an implementation plan.

```
/flux/ask [todo-file | all]
```

| Argument    | Required       | Description                                                                                                 |
| ----------- | -------------- | ----------------------------------------------------------------------------------------------------------- |
| `todo_file` | optional       | Task file name (path and `.md` extension inferred). If omitted, prompts you to select from available tasks. |
| `all`       | optional (alt) | Iterates through every file in the flux todo directory and asks clarifying questions                        |

**Examples:**

```
/flux/ask NOTIFS
/flux/ask MYPROJ-123
/flux/ask all
/flux/ask                    # interactive selection
```

---

## `/flux/split`

Decompose a large task file into multiple focused, single-session subtask files. Deletes the original.

```
/flux/split <todo-file>
```

| Argument    | Required  | Description                                            |
| ----------- | --------- | ------------------------------------------------------ |
| `todo-file` | mandatory | Task file to split (path and `.md` extension inferred) |

**Examples:**

```
/flux/split NOTIFS
/flux/split MYPROJ-123
```

---

## `/flux/aug`

Research the codebase and enrich task file(s) with implementation detail and citations.

```
/flux/aug [todo-file | N]
```

| Argument    | Required       | Description                                                    |
| ----------- | -------------- | -------------------------------------------------------------- |
| `todo-file` | optional       | Augment a single task file (path and `.md` extension inferred) |
| `N`         | optional (alt) | Augment all tasks using N parallel sub-agents                  |
| _(empty)_   | —              | Interactive selection prompt                                   |

**Examples:**

```
/flux/aug NOTIFS            # single task
/flux/aug 2                 # all tasks, 2 agents in parallel
/flux/aug 3                 # all tasks, 3 agents in parallel
/flux/aug                   # interactive selection
```

---

## `/flux/exec`

Execute task(s) exactly as written — no scope creep.

```
/flux/exec [todo_file | N]
```

| Argument    | Required       | Description                                                    |
| ----------- | -------------- | -------------------------------------------------------------- |
| `todo_file` | optional       | Execute a single task file (path and `.md` extension inferred) |
| `N`         | optional (alt) | Execute all tasks using N parallel sub-agents                  |
| _(empty)_   | —              | Interactive selection prompt                                   |

**Examples:**

```
/flux/exec NOTIFS_1         # single task
/flux/exec 2                # all tasks, 2 agents in parallel
```

---

## `/flux/qa`

Code-review the implementation for a task. Rates 1–10. Moves to `done/` if perfect; refines the task file if not.

```
/flux/qa [todo_file | N]
```

| Argument    | Required       | Description                                               |
| ----------- | -------------- | --------------------------------------------------------- |
| `todo_file` | optional       | QA a single task file (path and `.md` extension inferred) |
| `N`         | optional (alt) | QA all tasks using N parallel sub-agents                  |
| _(empty)_   | —              | Interactive selection prompt                              |

**Examples:**

```
/flux/qa NOTIFS_1           # single task
/flux/qa 2                  # all tasks, 2 agents in parallel
/flux/qa                    # interactive selection
```

> **QA loop:** If score < 10/10, re-run `/flux/exec` then `/flux/qa` until the task file is deleted.

---

## `/flux/tests`

Run the project's test suite, fix regressions introduced by this branch, and leave pre-existing failures untouched.

```
/flux/tests [additional_instructions]
```

| Argument                  | Required | Description                                                                                                      |
| ------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------- |
| `additional_instructions` | optional | Override default behavior (e.g. "address all failing tests including pre-existing", "focus on auth/ tests only") |
| _(empty)_                 | —        | Runs with default behavior: fix regressions only, skip pre-existing                                              |

**How it works:**

1. Reads `TEST_CMD` from the flux `config.env`
2. Establishes a baseline of pre-existing failures by running the test suite against the merge base
3. Runs tests on the current branch, classifies failures as regressions vs. pre-existing
4. Fixes regressions (up to 3 fix cycles), leaves pre-existing failures untouched
5. Prints a summary: regressions fixed, pre-existing skipped, unresolved

**Examples:**

```
/flux/tests
/flux/tests address all failing tests including pre-existing
/flux/tests focus only on src/auth/ test failures
```

> **Note:** Requires `TEST_CMD` to be configured via `/flux/config` first.

---

## `/flux/commit`

Stage all changes and create a detailed commit message derived from the diff vs. main. Asks for confirmation before committing.

```
/flux/commit
```

| Argument  | Required | Description         |
| --------- | -------- | ------------------- |
| _(empty)_ | —        | No arguments needed |

**Example:**

```
/flux/commit
```

---

## `/flux/create-pr`

Create a GitHub PR for the current branch, or display the existing PR URL and status if one already exists. Idempotent.

```
/flux/create-pr
```

| Argument  | Required | Description         |
| --------- | -------- | ------------------- |
| _(empty)_ | —        | No arguments needed |

**Example:**

```
/flux/create-pr
```

---

## `/flux/review`

Full code review of changed files with severity ratings. Optionally targets a specific PR by number.

```
/flux/review [PR#]
```

| Argument | Required | Description                                                                                           |
| -------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `PR#`    | optional | PR number to review (e.g. `123`). If omitted, reviews the current branch against its detected parent. |

**Examples:**

```
/flux/review                # review current branch
/flux/review 123            # review PR #123
```

Output: review files are written to the flux review directory (`~/.flux/<flattened-dir>/review/`), and then zipped as `review.zip` in the same parent directory.

---

## `/flux/address-feedback`

Convert review files into actionable todo tasks in the flux todo directory.

```
/flux/address-feedback [/path/to/review.zip]
```

| Argument              | Required | Description                                    |
| --------------------- | -------- | ---------------------------------------------- |
| `/path/to/review.zip` | optional | Path to a zip file received from a reviewer    |
| _(empty)_             | -        | If omitted, uses the local flux review folder. |

**Examples:**

```
/flux/address-feedback ~/Desktop/review.zip    # processed received zip file
/flux/address-feedback                         # uses local review folder
```

---

## `/flux/rebase`

Rebase the current branch onto the latest `main`, preserving each commit individually. Handles clean-tree check (with stash option), conflict resolution per commit, and force-with-lease push.

```
/flux/rebase
```

| Argument  | Required | Description         |
| --------- | -------- | ------------------- |
| _(empty)_ | —        | No arguments needed |

**What it does:**

1. Captures current branch state (commits, changed files)
2. Checks working tree is clean — offers to stash if not
3. Fetches and syncs local `main` with `origin/main`
4. Identifies potential conflict hotspots
5. Runs `git rebase main` — replays your commits on top of latest main
6. Guides through conflict resolution per commit (text, modify/delete, binary, rename, submodule)
7. Verifies history and changed files after rebase
8. Asks whether to push (`git push -u` for new branches, `--force-with-lease` for existing)
9. Offers to pop the stash if one was created in step 2

**Example:**

```
/flux/rebase
```

---

## `/flux/squash-commits`

Squash all unmerged commits (commits on your branch not yet on the default branch) into a single commit. Handles clean-tree check (with stash option), detects out-of-sync remote branches, and offers force-with-lease push.

```
/flux/squash-commits
```

| Argument  | Required | Description         |
| --------- | -------- | ------------------- |
| _(empty)_ | —        | No arguments needed |

**What it does:**

1. Captures current branch state (commits, changed files)
2. Checks working tree is clean — offers to stash if not
3. Checks the branch is not behind its remote counterpart — aborts with instructions if so
4. Shows commits to squash and asks for confirmation
5. Builds a combined commit message from all individual messages (bulleted list, oldest first) — user can override
6. Squashes via `git reset --soft` + `git commit`
7. Verifies result — confirms exactly 1 commit and correct diff
8. Asks whether to push (`git push -u` for new branches, `--force-with-lease` for existing)
9. Offers to pop the stash if one was created in step 2

**Example:**

```
/flux/squash-commits
```

---

## `/flux/auto-pilot`

Orchestrate the complete **PIPELINE A** sequence end-to-end from a single prompt. Pauses only during `/flux/ask` for clarifying questions.

```
/flux/auto-pilot <prompt | spec.md | spec.txt | TICKET-ID>
```

| Argument               | Required           | Description                                                             |
| ---------------------- | ------------------ | ----------------------------------------------------------------------- |
| `prompt`               | mandatory (one of) | Natural language description of the task                                |
| `spec.md` / `spec.txt` | mandatory (alt)    | Path to a spec file — contents used as the task description             |
| `TICKET-ID`            | mandatory (alt)    | Jira ticket key — fetches summary, description, and acceptance criteria |

**Examples:**

```
/flux/auto-pilot "Add real-time notifications"
/flux/auto-pilot ./specs/notifications.md
/flux/auto-pilot MYPROJ-123
/flux/auto-pilot CLIAPP-456
```

**Stages executed automatically:**

1. `/flux/new` → create task file
2. `/flux/ask` → clarify requirements _(only user pause)_
3. `/clear`
4. `/flux/split` → decompose into subtasks
5. `/flux/aug 2` → augment with 2 agents
6. `/clear`
7. `/flux/exec 2` → execute with 2 agents
8. `/clear`
9. `/flux/qa 2` → QA with 2 agents (up to 3 cycles)
10. `/flux/tests` → fix test regressions
11. `/flux/commit` → commit _(asks for confirmation)_
