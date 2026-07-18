---
name: tests
description: Run the test suite, fix regressions introduced by this branch, and leave pre-existing failures untouched
argument-hint: additional_instructions
---

# RUN & FIX TESTS

**Argument:** `$ARGUMENTS` (optional additional instructions, e.g. "address all failing tests including pre-existing")

Run the project's test suite, fix only regressions introduced by this branch, and leave pre-existing failures untouched.

If `$ARGUMENTS` contains additional instructions, apply them — they override default behavior (e.g. fix pre-existing failures too, focus on specific test files).

## STEP 1: Setup

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
CONFIG_FILE="$FLUX_BASE/config.env"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
```

Source config to get `TEST_CMD`:

```bash
source "$CONFIG_FILE" 2>/dev/null
echo "TEST_CMD: ${TEST_CMD:-<not set>}"
```

If `TEST_CMD` is empty or config file is missing:

```
Error: TEST_CMD is not configured.
Run /flux/config to set your test command.
```

Stop.

## STEP 2: Establish baseline (pre-existing failures)

Find the merge base with the default branch to identify which tests were already failing before this branch's changes:

```bash
DEFAULT_BRANCH=$(git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{print $NF}' || echo "main")
MERGE_BASE=$(git merge-base HEAD "origin/$DEFAULT_BRANCH" 2>/dev/null)
echo "MERGE_BASE: $MERGE_BASE"
```

Run the test suite against the merge base in a temporary worktree to record pre-existing failures:

```bash
WORKTREE_DIR=$(mktemp -d)
git worktree add "$WORKTREE_DIR" "$MERGE_BASE" --detach 2>/dev/null
```

If worktree creation fails (e.g. no network, shallow clone), skip baseline and assume all failures are regressions — note this clearly in output.

If worktree created: run `$TEST_CMD` inside it, capture failing test names → `BASELINE_FAILURES`. Then clean up:

```bash
git worktree remove "$WORKTREE_DIR" --force 2>/dev/null
```

## STEP 3: Run tests on current branch

```bash
eval "$TEST_CMD" 2>&1
```

Capture exit code and full output.

- **All tests pass** → print `✅ All tests pass.` and skip to STEP 6.
- **Failures found** → continue to STEP 4.

## STEP 4: Classify failures

For each failing test, classify it:

| Classification   | Criteria                                                   | Action   |
| ---------------- | ---------------------------------------------------------- | -------- |
| **Regression**   | Was passing at merge base (not in `BASELINE_FAILURES`)     | Fix it   |
| **Pre-existing** | Was already failing at merge base (in `BASELINE_FAILURES`) | Leave it |
| **Unknown**      | Baseline unavailable                                       | Fix it   |

Print a summary table:

```
Test Results
────────────────────────────────────────
  Total failures:    N
  Regressions:       R  ← will fix
  Pre-existing:      P  ← will skip
  Unknown:           U  ← will fix
────────────────────────────────────────
```

If there are no regressions or unknowns → print `✅ No regressions introduced by this branch.` and skip to STEP 6.

## STEP 5: Fix regressions

Fix regressions one at a time. For each:

1. Read the failing test and the source it exercises
2. Determine root cause: did the feature change break the test, or does the test need updating to match intentional new behavior?
3. Apply the minimal fix — either in source or in the test file
4. Do NOT expand test scope or add new test cases
5. Do NOT touch pre-existing failures

After fixing all regressions, re-run:

```bash
eval "$TEST_CMD" 2>&1
```

Repeat fix → re-run cycle until all regressions pass (max 3 cycles). If still failing after 3 cycles, stop and report:

```
⚠️  Could not fix the following regressions after 3 attempts:
  - <test name>: <last error>

Remaining pre-existing failures (not touched):
  - <test name>

Please review manually.
```

## STEP 6: Final summary

Print:

```
Test Suite Summary
────────────────────────────────────────
  ✅ Regressions fixed:   R
  ⏭  Pre-existing skipped: P
  ❌ Unresolved:           U
────────────────────────────────────────
```

If `U > 0`, recommend the user review those manually before committing.

## HARD CONSTRAINT

`/flux/tests` MUST NOT use `git commit`, `git push`, `git stash`, `git checkout`, or `git branch`. Only `git merge-base`, `git worktree`, and `git remote` are permitted. MUST NOT modify source files beyond the minimal fix required to resolve a regression. MUST NOT touch pre-existing failures. MUST NOT add new test cases or expand test scope.

## Propose next step

Then propose the next step: `/flux/commit` (include arguments if needed).

Valid `//flux` commands: `/flux/config`, `/flux/new`, `/flux/ask`, `/flux/split`, `/flux/aug`, `/flux/exec`, `/flux/qa`, `/flux/tests`, `/flux/commit`, `/flux/create-pr`, `/flux/review`, `/flux/address-feedback`, `/flux/status`, `/flux/auto-pilot`, `/flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
