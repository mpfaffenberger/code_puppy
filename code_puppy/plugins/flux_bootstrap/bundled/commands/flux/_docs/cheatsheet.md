# //flux Cheatsheet

## FIRST-TIME SETUP (run once per project) - optional

```
/flux/config TEST_CMD=<your-test-command-for-this-project>
```

Sets up the flux `config.env` (`~/.flux/<flattened-dir>/config.env`) with your test command.
Required before using the //flux suite on a new repo.

> **Tip:** `TEST_CMD` supports chaining — e.g. `bun run lint && bun run test:quiet`

---

## ON MY BRANCH

### PIPELINE A:

New ticket, feature, bug fix

#### MANUAL

1. /flux/new <task-description | Jira ticket>
2. /flux/ask <task-file | all>
3. /flux/split <task-file>
4. /flux/aug <task-file> or /flux/aug <N> or /flux/aug all
5. /flux/exec <task-file> or /flux/exec <N> or /flux/exec all
6. /flux/qa <task-file> or /flux/qa <N> or /flux/exec all
7. /flux/tests
8. /flux/commit
9. test changes (build and run the application)
10. /flux/create-pr

#### AUTO-PILOT

1. /flux/auto-pilot <task-description | Jira ticket> 

### PIPELINE B:

Review my own changes

1. /flux/review
2. /flux/address-feedback
3. /flux/ask all
4. /flux/exec 2
5. /flux/qa 2
6. /flux/commit

### PIPELINE C:

Address review received from a PR reviewer

1. /flux/address-feedback ~/Desktop/review.zip
2. /flux/ask all
3. /flux/exec 2
4. /flux/qa 2
5. /flux/commit

### PIPELINE D:

Review someone else's PR

1. /flux/review <PR#> OR
   /flux/review (if you are in the checked out PR branch)
2. Share the zip file created (e.g. `~/.flux/<flattened-dir>/review.zip`) with PR author (post on the PR, Slack, etc.)

## Quick Reference

| Task                 | Command                                            |
| -------------------- | -------------------------------------------------- |
| Project setup        | /flux/config                                       |
| Create task          | /flux/new <description or JIRA-ID>                 |
| Clarify requirements | /flux/ask <task-file\|'all'>                       |
| Break down task      | /flux/split <task-file>                            |
| Research & augment   | /flux/aug <task-file\|N\|'all'>                    |
| Execute task(s)      | /flux/exec <task-file\|N\|'all'>                   |
| QA review            | /flux/qa <task-file\|N\|'all'>                     |
| Fix test regressions | /flux/tests                                        |
| Commit changes       | /flux/commit                                       |
| Create a PR          | /flux/create-pr                                    |
| Code review          | /flux/review [PR#]                                 |
| Process feedback     | /flux/address-feedback [zipfile]                   |
| Rebase onto main     | /flux/rebase                                       |
| Squash commits       | /flux/squash-commits                               |
| Full pipeline        | /flux/auto-pilot <prompt \| task-file \| JIRA-ID>  |
