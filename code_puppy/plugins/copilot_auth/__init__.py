"""GitHub Copilot auth plugin for Code Puppy.

Authenticates with GitHub (or GitHub Enterprise) via the browser-based
Device Flow and exchanges the resulting OAuth token for a short-lived
Copilot session token to access the Copilot API.

Commands:
- ``/copilot-login``  — authenticate via browser
- ``/copilot-status`` — show auth & model status
- ``/copilot-logout`` — remove tokens and registered models
"""

