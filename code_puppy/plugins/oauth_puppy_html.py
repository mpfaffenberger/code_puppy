"""Small, self-contained HTML pages for browser-based OAuth callbacks."""

from __future__ import annotations

from html import escape
from typing import Optional

_PAGE_STYLES = """
:root {
  color-scheme: light dark;
  --bg: #f5f3ef;
  --card: rgba(255, 255, 255, 0.92);
  --border: rgba(28, 25, 23, 0.10);
  --text: #1c1917;
  --muted: #6b645f;
  --success: #16845b;
  --success-soft: #e7f6ef;
  --failure: #c2413a;
  --failure-soft: #fcebea;
  --shadow: 0 24px 70px rgba(41, 37, 36, 0.12);
}
* { box-sizing: border-box; }
body {
  min-height: 100vh;
  margin: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at 20% 10%, rgba(249, 115, 22, 0.08), transparent 30%),
    var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.card {
  width: min(100%, 480px);
  padding: 40px;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--card);
  box-shadow: var(--shadow);
  text-align: center;
}
.mark {
  width: 64px;
  height: 64px;
  margin: 0 auto 24px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: #1c1917;
  color: #fff;
  font-size: 30px;
  box-shadow: 0 10px 24px rgba(28, 25, 23, 0.16);
}
.eyebrow {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: clamp(28px, 6vw, 38px);
  line-height: 1.12;
  letter-spacing: -0.035em;
}
.message {
  max-width: 370px;
  margin: 16px auto 0;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.6;
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 28px;
  padding: 9px 13px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}
.status::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.success .status { color: var(--success); background: var(--success-soft); }
.failure .status { color: var(--failure); background: var(--failure-soft); }
.hint {
  margin: 24px 0 0;
  color: var(--muted);
  font-size: 13px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #121110;
    --card: rgba(29, 27, 25, 0.94);
    --border: rgba(255, 255, 255, 0.09);
    --text: #f7f5f2;
    --muted: #aaa39d;
    --success: #73d5ad;
    --success-soft: rgba(22, 132, 91, 0.18);
    --failure: #f19a94;
    --failure-soft: rgba(194, 65, 58, 0.18);
    --shadow: 0 24px 70px rgba(0, 0, 0, 0.34);
  }
  .mark { background: #f7f5f2; color: #1c1917; }
}
@media (max-width: 520px) {
  .card { padding: 32px 24px; border-radius: 20px; }
}
"""


def oauth_success_html(service_name: str, extra_message: Optional[str] = None) -> str:
    """Return a restrained success page for an OAuth callback."""
    service = _clean(service_name, "OAuth")
    message = _clean(
        extra_message,
        "Authentication is complete. You can return to Code Puppy.",
    )
    return _render_page(
        service=service,
        state="success",
        title="You're connected",
        message=message,
        status="Authentication complete",
        hint="This window can be closed safely.",
        auto_close=True,
    )


def oauth_failure_html(service_name: str, reason: str) -> str:
    """Return a clear, low-drama failure page for an OAuth callback."""
    service = _clean(service_name, "OAuth")
    message = _clean(reason, "Authentication could not be completed.")
    return _render_page(
        service=service,
        state="failure",
        title="Couldn't connect",
        message=message,
        status="Authentication incomplete",
        hint="Return to Code Puppy and try signing in again.",
    )


def _clean(value: Optional[str], fallback: str) -> str:
    """Normalize and HTML-escape dynamic page content."""
    normalized = value.strip() if value else fallback
    return escape(normalized or fallback)


def _render_page(
    *,
    service: str,
    state: str,
    title: str,
    message: str,
    status: str,
    hint: str,
    auto_close: bool = False,
) -> str:
    """Build a complete OAuth result page without remote assets."""
    close_script = (
        "<script>setTimeout(() => window.close(), 3500);</script>" if auto_close else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>{service} authentication</title>
  <style>{_PAGE_STYLES}</style>
</head>
<body>
  <main class="card {state}">
    <div class="mark" aria-hidden="true">CP</div>
    <p class="eyebrow">Code Puppy · {service}</p>
    <h1>{title}</h1>
    <p class="message">{message}</p>
    <div class="status" role="status">{status}</div>
    <p class="hint">{hint}</p>
  </main>
  {close_script}
</body>
</html>"""
