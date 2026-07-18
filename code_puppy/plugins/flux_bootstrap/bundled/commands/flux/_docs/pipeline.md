# Core Pipeline

## First-Time Setup

**Run once per project before using the `//flux` suite:**

//flux/config

Configures the flux `config.env` (`~/.flux/<flattened-dir>/config.env` for stable, `~/.flux-nightly/<flattened-dir>/config.env` for nightly) with your test command, Jira project key, template ticket, and summary prefix.

> **Tip:** `TEST_CMD` can chain lint and tests. Example: `bun run lint && bun run test:quiet`

---

## Available Commands

| Command                             | What it does                                                                            |
| ----------------------------------- | --------------------------------------------------------------------------------------- |
| //flux/config                       | **One-time setup** — configure project settings in the flux `config.env`                |
| //flux/create-jira <ticket-summary> | Create a new Jira ticket                                                                |
| //flux/new                          | Create a new task file in the flux todo directory                                       |
| //flux/ask                          | Clarify requirements via structured questions, then augment the spec                    |
| //flux/split                        | Break a large task into focused, single-session subtask files                           |
| //flux/aug <task-file\|N>           | Research codebase and enrich task file(s) with detail and citations                     |
| //flux/exec <task-file\|N>          | Execute task(s) exactly as written                                                      |
| //flux/qa <task-file\|N>            | Code review - rate 1-10, delete if perfect, refine if not                               |
| //flux/tests                        | Run test suite, fix regressions introduced by this branch, leave pre-existing untouched |
| //flux/commit                       | Stage and commit with Jira ID from branch name                                          |
| //flux/create-pr                    | Create a GitHub PR for the current branch, or show existing PR URL and status           |
| //flux/review [<pr-number>]         | Full code review of changed files with severity ratings                                 |
| //flux/address-feedback [<zipfile>] | Convert review files into todo task files                                               |
| //flux/rebase                       | Rebase the current branch onto latest main, preserving individual commits               |
| //flux/view-looper <pr-number>      | Open the Looper CI job for a PR in the browser                                          |
| //flux/auto-pilot                   | Orchestrate full PIPELINE A end-to-end from a prompt, spec file, or Jira ticket         |

### Unified Commands

The `aug`, `exec`, and `qa` commands are **unified** - they detect argument type automatically:

| Argument   | Mode        | Behavior                                                    |
| ---------- | ----------- | ----------------------------------------------------------- |
| task-file  | Single-task | Process one specific task file, path and extension inferred |
| N (number) | Multi-task  | Spawn N sub-agents in parallel                              |
| (empty)    | Interactive | Prompt user to select task(s)                               |

**Examples:**

- //flux/exec NOTIFS - Execute single task
- //flux/exec 3 - Execute all tasks, 3 agents in parallel
- //flux/exec - Show task selection prompt

## PIPELINE A:

---

New ticket, feature, or bug fix

```
//flux/new
 -> //flux/ask
  -> //flux/split
   -> //flux/aug
    -> //flux/exec
     -> //flux/qa
      -> //flux/tests
       -> //flux/commit
        -> run the app, test the changes
         -> //flux/create-pr
```

---

**Example**

- //flux/new "Add real-time notifications"
- //flux/ask NOTIFS
- //flux/split NOTIFS
- //flux/aug 2 (augment all tasks, 2 agents)
- //flux/exec 2 (execute all tasks, 2 agents)
- //flux/qa 2 (QA all tasks, 2 agents)
- //flux/tests
- //flux/commit
- the agent asks the user to test the changes and proposes next step: //flux/create-pr

## PIPELINE B:

---

Review my own changes on the current branch

```
//flux/review
 -> //flux/address-feedback
  -> //flux/ask
   -> //flux/exec
    -> //flux/qa
     -> //flux/tests
      -> //flux/commit
```

---

**Example**

- //flux/review
- //flux/address-feedback
- //flux/ask all
- //flux/exec 2
- //flux/qa 2
- //flux/tests
- //flux/commit

## PIPELINE C:

---

Address review feedback

```
//flux/address-feedback
 -> //flux/ask
  -> //flux/exec
   -> //flux/qa
    -> //flux/tests
     -> //flux/commit
```

---

**Example**

- //flux/address-feedback ~/Desktop/review.zip
- //flux/ask all
- //flux/exec 2
- //flux/qa 2
- //flux/tests
- //flux/commit

## PIPELINE D:

---

Review someone else's PR

```
# If the review is done from the PR branch itself (recommended)

//flux/review

# If the review is done from another branch, you need to provide PR number

//flux/review <PR#>

# For both cases, after the review has completed:
# -> post a comment on the PR, "Code changes suggested", and attach the zip file created
# (e.g. ~/.flux/<flattened-dir>/review.zip or ~/.flux-nightly/<flattened-dir>/review.zip)
```

---

**Example**

- //flux/review 123 (provide PR number if not on the PR branch)
- post a comment on the PR, "Code changes suggested", and attach the review.zip from your flux directory (e.g. `~/.flux/<flattened-dir>/review.zip` or `~/.flux-nightly/<flattened-dir>/review.zip`)
