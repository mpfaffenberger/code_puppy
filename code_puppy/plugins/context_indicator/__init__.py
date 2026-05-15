"""Context-window usage indicator.

Shows a colored circle in the terminal prompt reflecting how full the current
agent's message history is relative to the active model's context window:

* 🟢 — under 30% used
* 🟡 — 30%-60% used
* 🔴 — over 60% used

Also exposes a ``/context`` slash command for a detailed breakdown.
"""

__all__: list[str] = []
