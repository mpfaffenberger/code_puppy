---
name: review
argument-hint: pr_number(optional) | additional_instructions
description: Code review with smart parent branch detection and optional PR posting
---

# CODE REVIEW WORKFLOW

**Argument:** `$ARGUMENTS` (optional PR number)

## STEP 1: Branch setup

### 1a. If PR number provided:

```bash
CURRENT_BRANCH=$(git branch --show-current)
PR_NUMBER="${ARGUMENTS}"
PR_BRANCH=$(gh pr view $PR_NUMBER --json headRefName -q '.headRefName')
PARENT_BRANCH=$(gh pr view $PR_NUMBER --json baseRefName -q '.baseRefName')
if [ "$PR_BRANCH" != "$CURRENT_BRANCH" ]; then
  git fetch origin "$PR_BRANCH" && git checkout "$PR_BRANCH"
fi
git fetch origin "$PARENT_BRANCH"
echo "PARENT_BRANCH: $PARENT_BRANCH"
```

### 1b. If no PR number:

```bash
CURRENT_BRANCH=$(git branch --show-current)
PARENT_BRANCH=""
for branch in main master develop; do
  if git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
    MERGE_BASE=$(git merge-base HEAD "origin/$branch" 2>/dev/null)
    if [ -n "$MERGE_BASE" ] && [ "$branch" != "$CURRENT_BRANCH" ]; then
      PARENT_BRANCH="$branch"; break
    fi
  fi
done
PARENT_BRANCH="${PARENT_BRANCH:-main}"
echo "PARENT_BRANCH: $PARENT_BRANCH"
```

## STEP 2: Detect stack

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

## STEP 3: Branch ownership & merge base

```bash
MERGE_BASE=$(git merge-base HEAD "origin/$PARENT_BRANCH")
BRANCH_AUTHOR=$(git log --format='%an' --reverse "$MERGE_BASE..HEAD" 2>/dev/null | head -1)
CURRENT_USER=$(git config user.name)
[ "$BRANCH_AUTHOR" = "$CURRENT_USER" ] && IS_MY_BRANCH="true" || IS_MY_BRANCH="false"
echo "MERGE_BASE: $MERGE_BASE  IS_MY_BRANCH: $IS_MY_BRANCH"
```

## SCOPE CONSTRAINTS (CRITICAL)

**ONLY** flag issues **newly introduced** by changes vs `$MERGE_BASE` in files **directly modified**.

**DO NOT** flag: pre-existing issues in unchanged code, files/lines not touched, missing tests/benchmarks, style preferences.

> Why `$MERGE_BASE` not `origin/$PARENT_BRANCH`: upstream commits that landed after this branch was created would pollute the diff. Merge-base is the exact divergence point.

## STEP 4: Identify changed files

```bash
git diff --name-only "$MERGE_BASE"
```

## STEP 5: Analyze diffs

```bash
git diff "$MERGE_BASE"
```

Group files by: key modules, logical areas, high-risk changes (security, performance, data handling).

## STEP 6: Spawn code review sub-agents

Launch with `invoke_agent` tool, `run_in_background: false`.

**Agent count:**
| Changed Files | Agents | Strategy |
|---|---|---|
| 1-5 | 1-3 | Group related files |
| 6-15 | 4-8 | One per module/feature area |
| 16-50 | 8-12 | Group by directory |
| 50+ | 12-15 max | By directory, prioritize high-risk |

Per agent, provide: file paths + line ranges, relevant diff snippets, module/area name, PR context.

### Sub-agent prompt template

````
# CODE REVIEW: {{MODULE_NAME}}

## Files: {{FILE_LIST_WITH_LINE_RANGES}}

## Diffs
```diff
{{RELEVANT_DIFF_SNIPPETS}}
```

## Checklist — flag only issues in code CHANGED by this PR vs `$MERGE_BASE`:
- [ ] Stubs/Placeholders: non-functional required code (TODOs, NotImplemented)
- [ ] Race Conditions: concurrency, async/await problems
- [ ] Performance: O(n²) loops, memory leaks, excessive allocations, blocking calls
- [ ] Logic Errors: off-by-one, null checks, edge cases, wrong conditionals
- [ ] Dead Code: unwired code, unreachable paths
- [ ] Security: input validation, injection risks, exposed secrets
- [ ] Requirements Mismatch: code doesn't fulfill intended purpose
- [ ] Complexity: functions >50 lines, cyclomatic complexity >10 branches, nesting >4 levels
- [ ] Duplication: repeated code blocks >5 lines, duplicate constants/magic strings used 3+ times
- [ ] Maintainability: unused variables/imports, dead code paths, hardcoded magic numbers
- [ ] Design: commented-out code blocks >3 lines, inconsistent naming, TODO/FIXME in changed code
- [ ] Language-specific (TypeScript): missing async/await handling, unhandled promise rejections, `var` usage, `==` vs `===` in changed lines

DO NOT create tasks for: missing tests, benchmarks, style preferences, pre-existing issues.

## Task File Creation

For each issue, create `$FLUX_BASE/review/<issue-slug>.md`:

```markdown
---
severity: critical|high|medium|low
file: <filepath>
lines: <start>-<end>
introduced: true
---

# <Issue Title>

## Problem
<description>

## Evidence
<code snippet or diff>

## Impact
<what could go wrong>

## Suggested Fix
<recommended approach>
```

Before creating any task, verify: issue is in CHANGED code, did NOT exist before these changes, is genuinely problematic.
````

## STEP 7: Categorize by severity

```bash
FLUX_ROOT="${FLUX_ROOT:-$HOME/.flux}"
FLUX_DIR=$(printf '%s' "$(pwd -P)" | tr -cs 'a-zA-Z0-9' '-')
FLUX_BASE="$FLUX_ROOT/$FLUX_DIR"
mkdir -p "$FLUX_BASE/todo" "$FLUX_BASE/done" "$FLUX_BASE/review" "$FLUX_BASE/research"
mkdir -p "$FLUX_BASE/review/critical" "$FLUX_BASE/review/high" "$FLUX_BASE/review/medium" "$FLUX_BASE/review/low"
echo "FLUX_BASE=$FLUX_BASE"
```

Launch sub-agents (groups of 10) to move `$FLUX_BASE/review/*.md` to the appropriate severity subdirectory.

| Severity | Criteria                                                            |
| -------- | ------------------------------------------------------------------- |
| Critical | Security vulns, data loss, crashes, blocking bugs                   |
| High     | Significant logic errors, perf issues affecting UX, race conditions |
| Medium   | Minor logic issues, clarity problems, non-blocking bugs             |
| Low      | Minor improvements, low-probability edge cases                      |

## PATH REFRESH (after STEP 7)

Flat paths `$FLUX_BASE/review/*.md` no longer exist after categorization. All subsequent steps must locate files via:

```bash
find "$FLUX_BASE/review/" -name "*.md" -type f | sort
```

Steps 8, 10, and 11 sub-agents must use `find` or explicit subdirectory paths — never assume flat paths still exist.

## STEP 8: Verify newly introduced issues

Enumerate all task files with `find "$FLUX_BASE/review/" -name "*.md" -type f | sort`, then launch sub-agents. Each agent diffs the flagged file:

```bash
git diff "$MERGE_BASE" -- <filepath>
```

Classify each issue:
| Classification | Definition |
|---|---|
| Introduced | Exists only in new changes; parent branch is clean |
| Pre-existing | Exists in parent branch; these changes didn't create it |
| Aggravated | Pre-existing but made worse by these changes |

## STEP 9: Summarize findings

Enumerate with `find "$FLUX_BASE/review/" -name "*.md" -type f | sort`. Report: introduced issues requiring attention, aggravated issues to consider, pre-existing issues flagged for removal.

## STEP 10: User checkpoint

```bash
find "$FLUX_BASE/review/" -name "*.md" -type f | sort
```

Use `ask_user_question`: present pre-existing issues (full paths), ask which to keep. Default if no response: DELETE pre-existing issue tasks.

## STEP 11: Consolidation & deduplication

```bash
find "$FLUX_BASE/review/" -name "*.md" -type f | sort
```

Divide into groups, assign to sub-agents. Sub-agents use full paths from `find` (e.g. `$FLUX_BASE/review/high/auth-race-condition.md`).

| Classification          | Action                   |
| ----------------------- | ------------------------ |
| Exact Duplicate         | Remove one               |
| Semantic Duplicate      | Merge into one           |
| Consolidation Candidate | Combine into single task |
| Unique                  | Keep as-is               |

## STEP 12: Final summary & post-review actions

```
Total Issues Found: X
+-- Critical: A  +-- High: B  +-- Medium: C  +-- Low: D

Duplicates Removed: Y  Tasks Consolidated: Z -> W  Final Task Count: N
```

**Recommendation:** `APPROVE` / `REQUEST CHANGES` / `NEEDS DISCUSSION`

**If PR provided OR reviewing someone else's branch (`IS_MY_BRANCH=false`):**

```bash
REVIEW_COUNT=$(find "$FLUX_BASE/review/" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$REVIEW_COUNT" -eq 0 ]; then
  echo "No issues found — no zip created."
else
  FLAT_BRANCH=$(echo "$(git branch --show-current)" | tr '/' '-')
  ZIP_NAME="${FLAT_BRANCH}-review.zip"
  cd "$FLUX_BASE" && zip -r "$ZIP_NAME" review/
  echo "Review package: $FLUX_BASE/$ZIP_NAME"
fi
```

Report zip location. If PR provided: "share with PR author or attach manually." If no PR, someone else's branch: "share with the branch author."

**If `IS_MY_BRANCH=true`:** Leave files in `$FLUX_BASE/review/`. Report: "Issues saved to `$FLUX_BASE/review/` organized by severity."

## ERROR HANDLING

- Git command fails → report and stop
- Sub-agent fails → log, continue with remaining agents
- No changes found → report "No files changed vs parent branch" and exit
- 100+ issues found → pause and ask user how to proceed before categorization
- gh CLI fails → report but continue with local review

## HARD CONSTRAINTS

- **Path**: All `create_file`/`replace_in_file`/`mv`/`cp` file paths MUST use the exact `FLUX_BASE` value printed by STEP 2 or STEP 7 bash output (e.g. `FLUX_BASE=/Users/...`). Copy it character-for-character — never reconstruct it from `cwd` or memory.
- `/flux/review` MUST NOT modify any source files. The only permitted file operations are: creating issue task files in `$FLUX_BASE/review/`, moving/deleting those files during deduplication, and creating the zip archive. No changes to `./src/`, no git commits, no pushes.

## NEXT STEP

Then propose the next step:

- if user is reviewing their own branch: `/flux/address-feedback`
- if user is reviewing someone else's PR: `share the zip with the author`

Valid `//flux` commands: `/flux/config`, `/flux/new`, `/flux/ask`, `/flux/split`, `/flux/aug`, `/flux/exec`, `/flux/qa`, `/flux/tests`, `/flux/commit`, `/flux/create-pr`, `/flux/review`, `/flux/address-feedback`, `/flux/status`, `/flux/auto-pilot`, `/flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
