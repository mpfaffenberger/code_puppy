"""Distiller — extract durable facts/preferences from NATURAL conversation turns.

This is what makes the memory *learn*: instead of hand-tagged facts, a local
model reads each user message and emits the atomic, durable facts worth
remembering (brand, conventions, preferences), flags chatter as nothing, and
detects when a message UPDATES a prior fact (so the recorder can supersede it
via ``correct()``).

Entirely fail-soft: any error — Ollama unreachable, bad JSON, distiller turned
off — returns ``[]`` so the turn is logged episodically and nothing breaks.
"""

from __future__ import annotations

import json
import re

from .config import (
    DISTILLER_ENABLED,
    DISTILLER_MODEL,
    DISTILLER_TIMEOUT,
    DISTILLER_URL,
)

SYSTEM = (
    "You extract DURABLE facts and preferences worth remembering long-term from a "
    "user's message: brand, conventions, standing rules, personal preferences, and "
    "ONGOING STYLE preferences (e.g. 'keep charts minimalist, no gridlines'). "
    "A message can mix small talk with a durable preference — extract the durable "
    "part and ignore the rest. Ignore PURE small talk and one-off task requests. "
    "Return ONLY a JSON array. Each item: "
    '{"fact": "<concise durable fact>", "importance": <0.0-1.0>, '
    '"updates": "<exact prior fact text this replaces, or null>"}. '
    "If there is nothing durable, return []."
)

_ARR = re.compile(r"\[.*\]", re.DOTALL)


def extract(message: str, existing_facts: list[str] | None = None) -> list[dict]:
    """Return a list of ``{fact, importance, updates}`` dicts. Never raises."""
    if not DISTILLER_ENABLED:
        return []
    if not message or not message.strip():
        return []

    ctx = ""
    if existing_facts:
        ctx = (
            "Known facts (an update may replace one of these):\n"
            + "\n".join(f"- {f}" for f in existing_facts)
            + "\n\n"
        )
    prompt = f"{ctx}Message:\n{message}"

    try:
        import requests  # imported lazily so a missing dep doesn't break import.

        r = requests.post(
            DISTILLER_URL,
            json={
                "model": DISTILLER_MODEL,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0},
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=DISTILLER_TIMEOUT,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"]
    except Exception:
        return []

    m = _ARR.search(text)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except Exception:
        return []

    out: list[dict] = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and it.get("fact"):
            out.append(
                {
                    "fact": str(it["fact"]).strip(),
                    "importance": float(it.get("importance", 0.7) or 0.7),
                    "updates": (it.get("updates") or None),
                }
            )
    return out
