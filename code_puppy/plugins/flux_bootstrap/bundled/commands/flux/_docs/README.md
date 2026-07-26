# 𝕱 Flux Workflow System

Read the full story [here](https://github.com/mpfaffenberger/code_puppy/blob/main/docs/FLUX.md)

Here is the TL;DR

A structured, AI-assisted development pipeline organized around **task files** stored in `~/.flux/<flattened-dir>/todo/`.
Every command guides you through one stage of the lifecycle, with each step proposing the next.

Naming: throughout the docs and command .md files the term 'task' and 'task-file' are used interchangeably.
They both mean: an .md file in the flux todo directory (`~/.flux/<flattened-dir>/todo`)

---

## First-Time Setup (optional)

```
/flux/config
```

This sets up the flux `config.env` file (at `~/.flux/<flattened-dir>/config.env`) with your project's test command.

**NOTE**: config.env is only used by the 'tests' command. If you don't plan to use it, you can skip flux/config and start directly with flux/new

> **Flux root directory:** `~/.flux/<flattened-dir>/`. All task files, review files, and config are stored under the root automatically.

## The Core Pipeline

```
new -> ask -> split -> aug -> exec -> qa -> tests -> commit -> create-pr
```

| Step | Command                          | What happens                                                                                                                                                                              |
| ---- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | /flux/new <prompt\|Jira ticket> | Creates a task `.md` file in the flux todo directory from your description or Jira ticket                                                                                                 |
| 2    | /flux/ask <task-file\|all>      | Asks clarifying questions (one at a time), researches the codebase, then **augments** the task file                                                                                            |
| 3    | /flux/split <task-file>         | Splits a large task into multiple focused subtask files. Deletes the original.                                                                                                            |
| 4    | /flux/aug <task-file\|N\|all>   | Deep research pass - explores source files, finds existing code, enriches task file(s) with citations                                                                                     |
| 5    | /flux/exec <task-file\|N\|all>  | Faithfully implements exactly what the task says. No scope creep.                                                                                                                         |
| 6    | /flux/qa <task-file\|N\|all>    | Rates implementation 1-10. If 10/10 -> moves the task file to `done`. If <10 -> refines remaining gaps                                                                                    |
| 7    | /flux/tests                     | Runs the test suite. Fixes regressions introduced by this branch. Leaves pre-existing failures untouched. If you want those also fixed, you can specify that as 'additional-instructions' |
| 8    | /flux/commit                    | Diffs vs previous commit, creates a detailed commit message, asks for confirmation, commits (no push)                                                                                     |
| 9    | /flux/create-pr                 | Creates a GitHub Pull Request from the current branch. Derives title from branch name. Idempotent: shows existing PR if one already exists.                                               |

> **QA loop**: If `qa` doesn't score 10/10, run `exec` again on the updated file, then `qa` again. Repeat until the file is marked 10/10 and is deleted.

---

## Unified Commands

The `aug`, `exec`, and `qa` commands support **both single-task and multi-task** modes through argument detection:

| Argument Type              | Mode        | Behavior                                                                                           |
| -------------------------- | ----------- | -------------------------------------------------------------------------------------------------- |
| Filename (e.g., NOTIFS.md) | Single-task | Process one specific task file                                                                     |
| Number (e.g., 2, 3, 5)     | Multi-task  | Spawn N sub-agents in parallel                                                                     |
| 'all'                      | Single-task | Process all task files sequentially
| (empty)                    | Interactive | Prompt user to select task(s) from the list found in the flux todo directory via `ask_user_question` |

**Examples:**

```
/flux/aug NOTIFS.md      # Augment single task
/flux/aug 2              # Augment all tasks, 2 agents in parallel
/flux/aug all            # Augment all tasks sequentially
/flux/aug                # Show selection prompt

/flux/exec DEV_1.md      # Execute single task
/flux/exec 3             # Execute all tasks, 3 agents in parallel
/flux/exec all           # Execute all tasks sequentially
/flux/exec               # Show selection prompt

/flux/qa FEATURE.md      # QA single task
/flux/qa 2               # QA all tasks, 2 agents in parallel
/flux/qa all             # QA all tasks sequentially
/flux/qa                 # Show selection prompt
```

---

## Utility Commands

| Command                       | What it does                                                                                                                                                                                                                       |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| /flux/config                 | (optional) Creates or updates the flux `config.env` with project-specific settings (the test command used by /flux/tests). Run once per project before using the Flux suite.                 |
| /flux/review [PR#]           | Full code review of changes vs parent branch. Optionally accepts PR number for automatic branch detection and PR commenting.                                                                                                       |
| /flux/address-feedback [zip] | Convert existing review files (present in the flux review folder) into todo tasks. Accepts optional zip file path for reviews received from others.                                                                                |
| /flux/rebase                 | Rebase the current branch onto latest main, preserving individual commits. Handles clean-tree check, conflict resolution, and force-with-lease push.                                                                               |
| /flux/squash-commits         | Squash all unmerged commits on the current branch into one. Checks clean tree (with stash option), detects remote out-of-sync, and offers force-with-lease push.                                                                   |
| /flux/auto-pilot             | Orchestrate the full PIPELINE A end-to-end from a single prompt, spec file, or Jira ticket. Pauses only during `/flux/ask`.                                                                                                       |

---

## Pipelines

### PIPELINE A - New feature / bug fix

```
1. /flux/new <prompt>
2. /flux/ask <task-file>
3. /flux/split <task-file>
4. /flux/aug 2
5. /flux/exec 2
6. /flux/qa 2
7. /flux/tests
8. /flux/commit
9. the agent asks the user to test the changes and proposes next step: /flux/create-pr
```

### PIPELINE B - Code review (your own changes)

```
1. /flux/review
2. /flux/address-feedback
3. /flux/ask all
4. /flux/exec 2
5. /flux/qa 2
6. /flux/tests
7. /flux/commit
```

> **Note:** Depending on the number of changes, you may want to process `critical` tasks one by one.

### PIPELINE C - Code review received on your PR

```
1. /flux/address-feedback ~/Desktop/review.zip
2. /flux/ask all
3. /flux/exec 2
4. /flux/qa 2
5. /flux/tests
6. /flux/commit
```

---

## Key Design Principles

- **Task files are the source of truth** - never modify them during `exec` or `qa`; only `qa` can edit/delete them
- **No tests, no benchmarks** - explicitly excluded; they are handled separately (/flux/tests)
- **No git commands** during `exec`/`qa` - other agents may be working concurrently
- **Steps always propose the next step** - each command ends by suggesting what to run next with the right arguments
- **task-file path and extension is inferred** - when passing a task-file as argument, the name with no suffix is sufficient
  e.g. instead of `/flux/aug <flux-todo-dir>/TASK_1.md` you can just do `/flux/aug TASK_1`

## APPENDIX

- Examples of config.env file:

```
TEST_CMD=bun run lint && bun run test:quiet
```

```
TEST_CMD=uv run ruff check . && uv run pytest -q --no-cov
```

- Examples of stack.env file:

This is used by `aug`, `exec`, `qa`, `review`. 
If absent, the agent runs a detection script and writes it (first-run per directory).

```
pydantic.ai + Python
```

```
Ink + Typescript
```

```
fastAPI + Python
```
