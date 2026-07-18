# `//flux` Workflow System

A structured, AI-assisted development pipeline organized around **task files** stored in `~/.flux/<flattened-dir>/todo/`.
Every command guides you through one stage of the lifecycle, with each step proposing the next.

Naming: throughout the docs and command .md files the term 'task' and 'task-file' are used interchangeably.
They both mean: an .md file in the flux todo directory (`~/.flux/<flattened-dir>/todo` for stable, `~/.flux-nightly/<flattened-dir>/todo` for nightly)

Attribution: Based on the original `gandalf` workflow by David Maple.

---

## First-Time Setup

**Before using the `//flux` suite on a new project, run this once:**

```
//flux/config
```

This sets up the flux `config.env` file (at `~/.flux/<flattened-dir>/config.env`, or `~/.flux-nightly/<flattened-dir>/config.env` for nightly) with your project's test command, Jira project key, template ticket, and summary prefix.
All subsequent `//flux` commands read from this file automatically.

**NOTE**: config.env is only used by the 'create-jira' and 'tests' commands. If you don't plan to use those commands, you can skip flux/config and start directly with flux/new

> **Flux root directory:** `~/.flux/<flattened-dir>/`. All task files, review files, and config are stored under the root automatically.

## The Core Pipeline

```
new -> ask -> split -> aug -> exec -> qa -> tests -> commit -> create-pr
```

| Step | Command                          | What happens                                                                                                                                                                              |
| ---- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | //flux/new <prompt\|Jira ticket> | Creates a task `.md` file in the flux todo directory from your description or Jira ticket                                                                                                 |
| 2    | //flux/ask <task-file\|all>      | Asks clarifying questions (one at a time), researches the codebase, then **augments** the spec                                                                                            |
| 3    | //flux/split <task-file>         | Splits a large task into multiple focused subtask files. Deletes the original.                                                                                                            |
| 4    | //flux/aug <task-file\|N>        | Deep research pass - explores source files, finds existing code, enriches task file(s) with citations                                                                                     |
| 5    | //flux/exec <task-file\|N>       | Faithfully implements exactly what the task says. No scope creep.                                                                                                                         |
| 6    | //flux/qa <task-file\|N>         | Rates implementation 1-10. If 10/10 -> moves the task file to `done`. If <10 -> refines remaining gaps                                                                                    |
| 7    | //flux/tests                     | Runs the test suite. Fixes regressions introduced by this branch. Leaves pre-existing failures untouched. If you want those also fixed, you can specify that as 'additional-instructions' |
| 8    | //flux/commit                    | Diffs vs previous commit, creates a detailed commit message, asks for confirmation, commits (no push)                                                                                     |
| 9    | //flux/create-pr                 | Creates a GitHub Pull Request from the current branch. Derives title from branch name. Idempotent: shows existing PR if one already exists.                                               |

> **QA loop**: If `qa` doesn't score 10/10, run `exec` again on the updated file, then `qa` again. Repeat until the file is marked 10/10 and is deleted.

---

## Unified Commands

The `aug`, `exec`, and `qa` commands support **both single-task and multi-task** modes through argument detection:

| Argument Type              | Mode        | Behavior                                                                                           |
| -------------------------- | ----------- | -------------------------------------------------------------------------------------------------- |
| Filename (e.g., NOTIFS.md) | Single-task | Process one specific task file                                                                     |
| Number (e.g., 2, 3, 5)     | Multi-task  | Spawn N sub-agents in parallel                                                                     |
| (empty)                    | Interactive | Prompt user to select task(s) from the list found in the flux todo directory via `AskUserQuestion` |

**Examples:**

```
//flux/aug NOTIFS.md      # Augment single task
//flux/aug 2              # Augment all tasks, 2 agents in parallel
//flux/aug                # Show selection prompt

//flux/exec DEV_1.md      # Execute single task
//flux/exec 3             # Execute all tasks, 3 agents in parallel
//flux/aug                # Show selection prompt

//flux/qa FEATURE.md      # QA single task
//flux/qa 2               # QA all tasks, 2 agents in parallel
//flux/qa                 # Show selection prompt
```

---

## Utility Commands

| Command                       | What it does                                                                                                                                                                                                                       |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| //flux/config                 | **One-time setup.** Creates or updates the flux `config.env` with project-specific settings (test command, Jira project key, template ticket, summary prefix). Run once per project before using the //flux suite.                 |
| //flux/create-jira <title>    | clones template specified in the flux `config.env` file, to create a new Jira ticket in the project specified in the same config file. Ticket opens in browser automatically after creation. Reporter defaults to current OS user. |
| //flux/review [PR#]           | Full code review of changes vs parent branch. Optionally accepts PR number for automatic branch detection and PR commenting.                                                                                                       |
| //flux/address-feedback [zip] | Convert existing review files (present in the flux review folder) into todo tasks. Accepts optional zip file path for reviews received from others.                                                                                |
| //flux/rebase                 | Rebase the current branch onto latest main, preserving individual commits. Handles clean-tree check, conflict resolution, and force-with-lease push.                                                                               |
| //flux/squash-commits         | Squash all unmerged commits on the current branch into one. Checks clean tree (with stash option), detects remote out-of-sync, and offers force-with-lease push.                                                                   |
| //flux/view-looper <PR#>      | Open the Looper CI job for a given PR number in the browser (cmux-aware).                                                                                                                                                          |
| //flux/auto-pilot             | Orchestrate the full PIPELINE A end-to-end from a single prompt, spec file, or Jira ticket. Pauses only during `//flux/ask`.                                                                                                       |

---

## Pipelines

### PIPELINE A - New feature / bug fix

```
1. //flux/new <prompt>
2. //flux/ask <task-file>
3. //flux/split <task-file>
4. //flux/aug 2
5. //flux/exec 2
6. //flux/qa 2
7. //flux/tests
8. //flux/commit
9. the agent asks the user to test the changes and proposes next step: //flux/create-pr
```

### PIPELINE B - Code review (your own changes)

```
1. //flux/review
2. //flux/address-feedback
3. //flux/ask all
4. //flux/exec 2
5. //flux/qa 2
6. //flux/tests
7. //flux/commit
```

> **Note:** Depending on the number of changes, you may want to process `critical` tasks one by one.

### PIPELINE C - Code review received on your PR

```
1. //flux/address-feedback ~/Desktop/review.zip
2. //flux/ask all
3. //flux/exec 2
4. //flux/qa 2
5. //flux/tests
6. //flux/commit
```

---

## Key Design Principles

- **Task files are the source of truth** - never modify them during `exec` or `qa`; only `qa` can edit/delete them
- **No tests, no benchmarks** - explicitly excluded; they are handled separately (//flux/tests)
- **No git commands** during `exec`/`qa` - other agents may be working concurrently
- **Steps always propose the next step** - each command ends by suggesting what to run next with the right arguments
- **task-file path and extension is inferred** - when passing a task-file as argument, the name with no suffix is sufficient
  e.g. instead of `//flux/aug <flux-todo-dir>/TASK_1.md` you can just do `//flux/aug TASK_1`

## APPENDIX

- Usage for the `//flux/create-jira` command

```
//flux/create-jira My new feature
```

The prefix defined in the flux `config.env` file is automatically prepended to the summary if not already present.
Reporter is automatically set from the current OS user — no need to provide it.
All the other fields are pre-populated from the Jira ticket template (if you provided one in config.env)

- Example config.env file:

```
TEST_CMD=bun run test:quiet
JIRA_BASE_URL=https://jira.myorg.com
JIRA_PROJECT_KEY=MYPROJ
JIRA_TICKET_TEMPLATE=MYPROJ-171
JIRA_TICKET_PREFIX=[frontend]
```

- Example stack.env file:

```
ink + Typescript
```
