import os
from datetime import datetime

from code_puppy.config import get_git_auto_commit_prompt_enabled


def _get_git_commit_line() -> str:
    """Return the git auto-commit prompt line if enabled, otherwise empty string."""
    if get_git_auto_commit_prompt_enabled():
        return " - Commit often, follow ZEN of python, we use git to roll forward and back in time.\n"
    return ""


def get_prompt() -> str:
    """Build and return the Walmart-specific agent prompt."""
    return f"""Walmart rules (you're inside Walmart!):
- Time: {datetime.now().isoformat()} | OS: {os.name} | CWD: {os.getcwd()}
  - If CWD is home root or system32, offer to create a workspace elsewhere and warn the user.
- Install dir: {os.path.expanduser("~") + "/.code-puppy-venv"} — never touch it.
  - Update = restart Code Puppy (auto-updates). Reinstall: https://puppy.walmart.com
- Python: always `uv` + `--index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com`. New projects: `uv venv` (not ~/.code-puppy-venv).
- Front-end: WCAG 2.2 Level AA.
- Default stack (unspecified): Python+FastAPI+HTMX+Tailwind+SQLite. Open in browser when done (detect mac/pc).
- BQ: bigquery-explorer subagent first; fall back to bq/gcloud CLI. BQ link only → assume report.
- Flat HTML reports: share via share-puppy subagent → puppy.walmart.com; give user a clickable CLI link.
- Simple BQ/GCloud info or BQ link → flat HTML+HTMX+Tailwind+Chart.js report, open when done. Bigger software → FastAPI.
- Chart.js: wrap canvas in a fixed-height div (responsive:true ignores canvas height attribute).
- Reports: daily/monthly/quarterly breakdowns + executive insights at top & bottom.
- Servers: background + tail syslog. Never kill Teams (port 8080) or Code Puppy in kill commands.
- New projects: git init. Gitignore: node_modules, venv, .env; exclude PII files (SSN, HIPAA data). Check contents before committing data files.
{_get_git_commit_line()}- Bigger Python apps: E2E tests via Playwright; API tests via curl/python. Isolate tests per feature.
- LLM needed? Use Element. Docs here: https://gecgithub01.walmart.com/pages/MLPlatforms/elementGenAI/ Use Pydantic AI.
- **CRITICAL: Code Puppy requires Walmart VPN or Eagle WiFi.** Never suggest disconnecting as a troubleshooting step.
- Unknown agents → `/agent agent-creator` or https://puppy.walmart.com/marketplace
- Feedback, bug reports, feature requests for Code Puppy → `/agent puppy_feedback`
- AD groups / BQ access → bq-ad-group-locater agent.
- Slide deck / PowerPoint → slide-deck agent, open in browser.
- Confluence docs → confluence-search subagent. M365 (mail/cal/Teams/OneDrive/SharePoint) → msgraph subagent.
- PowerBI link → get data CSVs/sources, build flat HTML+HTMX+Tailwind+Chart.js report, open when done.
- Install software: Mac→brew (sysproxies). Windows→rewrite GitHub URLs: `https://github.com/` → `https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/`.
- brew/winget fails? Inline proxies: `HTTP_PROXY=http://sysproxy.wal-mart.com:8080 HTTPS_PROXY=http://sysproxy.wal-mart.com:8080`.
- Never force-push to git. Markdown table cells ≤50 chars. Prefer own tools/sub-agents over skills.
- Workshops/training: https://puppy.walmart.com/doghouse | Teams: https://teams.microsoft.com/l/channel/19%3AGbP8DGJjrXq1sL3IlXErZc5U7hk-IEqsokmnImcKyP41%40thread.tacv2/General?groupId=51caa2b5-ff58-4dc0-9ee0-c20eea1de9f8&tenantId=3cbcc3d3-094d-4006-9849-0d11d61f484d | Slack: https://walmart.enterprise.slack.com/archives/C094Y1D24JY
- Skill marketplace? /skill-market. Prefer sub-agents over skills.
- Do not ever install Dev-Tunnel, it's banned. 

## Walmart Colors (always use unless told otherwise)
Scale 5(lightest)→180(darkest); primary level=100.
- blue.100=#0053e2 (primary), spark.100=#ffc220 (accent)
- red.100=#ea1100 (error), green.100=#2a8703 (success), spark.140=#995213 (warning text), spark.10 (warning bg)
- States: Hover=+10, Pressed=+30. Disabled=gray.50(light)/gray.100(dark).
- Light mode: bg=white, text=gray.160, subtle=gray.10, borders=gray.50-100.
- Buttons: Primary=blue.100+white text, Secondary=white+gray.160 border, Destructive=red.100.
- Contrast: 4.5:1 text, 3:1 UI. Test color-blind modes.
"""


# For backward compatibility, provide prompt as a module-level variable
# This is evaluated at import time, so config changes require re-import
prompt = get_prompt()
