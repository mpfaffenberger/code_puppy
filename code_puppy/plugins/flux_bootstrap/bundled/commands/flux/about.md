---
name: about
description: Display a brief overview of Flux — structured AI dev pipeline
exec: {python} {script:flux_about.py} --source {command:flux/about.md}
---

# /flux/about

Output the following overview exactly as written. Do not add commentary, do not fetch anything, do not modify the content.

---

🌀 **Flux** — Structured AI Dev Pipeline

Flux turns chaotic AI coding sessions into a smooth, repeatable workflow. Instead of one giant "do everything" prompt, Flux breaks work into focused, per-file pipeline steps — keeping the AI sharp and your context clean.

**The 9-Step Pipeline:**

```
new → ask → split → aug → exec → qa → tests → commit → create-pr
```

| Command            | What it does                                           |
| ------------------ | ------------------------------------------------------ |
| `/flux/new`       | Create a task file from a description or Jira ticket   |
| `/flux/ask`       | Clarify requirements & research the codebase           |
| `/flux/split`     | Break large tasks into focused subtasks                |
| `/flux/aug`       | Deep research: annotate tasks with exact file paths    |
| `/flux/exec`      | Implement — precisely what the spec says, no more      |
| `/flux/qa`        | Score vs acceptance criteria; loop until 10/10         |
| `/flux/tests`     | Fix regressions without touching pre-existing failures |
| `/flux/commit`    | Craft a meaningful commit message, ask confirmation    |
| `/flux/create-pr` | Open a GitHub PR with full task-derived description    |

**Utility Commands:**

| Command                   | What it does                                                         |
| ------------------------- | -------------------------------------------------------------------- |
| `/flux/config`           | One-time setup: configure the test command used by /flux/tests       |
| `/flux/review`           | Full code review vs parent branch; optionally targets a PR number    |
| `/flux/address-feedback` | Convert review files into executable todo tasks                      |
| `/flux/auto-pilot`       | Run the full pipeline end-to-end from a single prompt or Jira ticket |
| `/flux/status`           | Show the status panel that displays task files and their status live |
| `/flux/cheatsheet`       | Show the //flux pipeline cheatsheet (all stages, colorized)          |

**Key Benefits:**

- **Crash-proof** — all state lives in `~/.flux/`; resume anytime after a crash or restart
- **Context-safe** — `/clear` between steps is encouraged; `aug` output persists to disk
- **Parallel agents** — `aug`, `exec`, and `qa` all support concurrent multi-agent runs
- **QA gate** — nothing ships until it scores 10/10 against acceptance criteria
