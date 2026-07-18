---
name: view-looper
argument-hint: pr_number
description: Open the Looper CI job for a PR in the cmux browser (if inside cmux) or the default system browser
---

# VIEW-LOOPER

Open the LooperPro log viewer for a given PR number. Uses cmux browser when inside cmux, otherwise the system browser.

## STEP 1: Validate input

```bash
PR="$ARGUMENTS"
if [ -z "$PR" ]; then
  echo "Usage: //flux/view-looper <pr-number>"
  exit 1
fi
echo "PR: $PR"
```

Stop on error.

## STEP 2: Fetch PR check runs

```bash
PR="$ARGUMENTS"
CHECKS=$(gh pr checks "$PR" --json name,link 2>&1)
if [ $? -ne 0 ]; then
  echo "Error fetching checks for PR #$PR:"
  echo "$CHECKS"
  exit 1
fi
echo "$CHECKS"
```

Stop on error.

## STEP 3: Find Looper check URL and open

```bash
PR="$ARGUMENTS"
CHECKS=$(gh pr checks "$PR" --json name,link 2>/dev/null)

URL=$(echo "$CHECKS" | jq -r '
  [.[] | select(.name | test("\\[PR\\]|looper"; "i"))] | first |
  if . == null then "__NO_CHECK__"
  elif (.link == null or .link == "") then "__NO_URL__"
  else .link
  end
')

if [ "$URL" = "__NO_CHECK__" ]; then
  echo "No Looper check found for PR #$PR"
  exit 1
fi

if [ "$URL" = "__NO_URL__" ]; then
  echo "Looper check has no URL yet for PR #$PR"
  exit 1
fi

echo "Opening Looper job for PR #$PR:"
echo "$URL"

if [ -n "$CMUX_WORKSPACE_ID" ]; then
  cmux browser open "$URL"
else
  case "$(uname -s)" in
    Darwin)              open "$URL" ;;
    Linux)               xdg-open "$URL" ;;
    MINGW*|CYGWIN*|MSYS*) start "" "$URL" ;;
    *)                   echo "Unknown OS — copy and open the URL manually" ;;
  esac
fi
```

Stop on error; otherwise browser opens automatically.

## HARD CONSTRAINT

`//flux/view-looper` MUST NOT modify any files, run any git commands, or do anything other than fetching PR check data and opening a URL in the browser.

## Error reference

| Condition                               | Output                                    |
| --------------------------------------- | ----------------------------------------- |
| No PR number provided                   | `Usage: //flux/view-looper <pr-number>`   |
| `gh` CLI not found or auth failure      | Error from `gh` printed verbatim          |
| No check matching `[PR]` or `looper`    | `No Looper check found for PR #<N>`       |
| Matching check exists but link is empty | `Looper check has no URL yet for PR #<N>` |
| Inside cmux (`$CMUX_WORKSPACE_ID` set)  | Opens URL in cmux built-in browser        |
| Success (outside cmux)                  | URL printed, then system browser opens    |

=================
$ARGUMENTS
