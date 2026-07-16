"""Context-window usage indicator.

Shows a colored circle on the bottom bar's status row (next to the token
summary) reflecting how full the current agent's message history is
relative to the active model's context window:

* 🟢 — under 30% used
* 🟡 — 30%-65% used
* 🔴 — over 65% used

Also exposes a ``/context`` slash command for a detailed breakdown.
"""

__all__: list[str] = []
