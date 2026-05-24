"""Persisted configuration for goal-mode LLM judges.

Each judge is a (name, model, prompt, enabled) tuple. Judges live in a
JSON file at ``$XDG_DATA_HOME/code_puppy/judges.json`` so users can
configure multiple verifiers — for example, one judge that checks tests
pass, another that checks docs are updated, etc. The /goal loop fans
these out in parallel and only declares success when *every* enabled
judge reports no remediation notes.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field

from code_puppy.config import DATA_DIR

logger = logging.getLogger(__name__)

JUDGES_FILE = os.path.join(DATA_DIR, "judges.json")

_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


DEFAULT_JUDGE_PROMPT = """\
You are Code Puppy's goal-completion judge.

Decide whether the user's goal is verifiably complete based on the
implementor's latest response and (optionally) its message history.

Rules:
- You are not the implementation agent.
- Never modify files. You may use read-only tools if inspection helps.
- Never ask the user questions.
- Return the structured output exactly as requested by the runtime.
- Be strict. If completion is uncertain, mark incomplete and provide
  concrete remediation notes the implementor can act on next turn.
- For trivial conversational goals, judge based on whether the latest
  response satisfies the request.
- For coding goals, prefer concrete verification: passing tests,
  successful commands, file inspection.
"""


@dataclass
class JudgeConfig:
    """One configured judge."""

    name: str
    model: str
    prompt: str = DEFAULT_JUDGE_PROMPT
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JudgeConfig":
        return cls(
            name=str(data.get("name", "")),
            model=str(data.get("model", "")),
            prompt=str(data.get("prompt") or DEFAULT_JUDGE_PROMPT),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class JudgeRegistry:
    """In-memory snapshot of configured judges."""

    judges: list[JudgeConfig] = field(default_factory=list)

    def names(self) -> list[str]:
        return [j.name for j in self.judges]

    def enabled(self) -> list[JudgeConfig]:
        return [j for j in self.judges if j.enabled]

    def find(self, name: str) -> JudgeConfig | None:
        for j in self.judges:
            if j.name == name:
                return j
        return None


def validate_name(name: str) -> str | None:
    """Return an error string if the name is invalid, else None."""
    if not name:
        return "Name must not be empty."
    if not _NAME_RE.match(name):
        return (
            "Name must be 1–64 chars, letters/digits/underscore/hyphen only "
            "(no spaces)."
        )
    return None


def load_judges() -> JudgeRegistry:
    """Load judges from disk. Returns an empty registry if the file is missing."""
    if not os.path.exists(JUDGES_FILE):
        return JudgeRegistry()

    try:
        with open(JUDGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load judges from %s: %s", JUDGES_FILE, exc)
        return JudgeRegistry()

    raw_judges = data.get("judges") if isinstance(data, dict) else None
    if not isinstance(raw_judges, list):
        return JudgeRegistry()

    judges: list[JudgeConfig] = []
    seen_names: set[str] = set()
    for item in raw_judges:
        if not isinstance(item, dict):
            continue
        try:
            judge = JudgeConfig.from_dict(item)
        except Exception as exc:
            logger.warning("Skipping invalid judge entry: %s", exc)
            continue
        if validate_name(judge.name) is not None:
            logger.warning("Skipping judge with invalid name: %r", judge.name)
            continue
        if judge.name in seen_names:
            logger.warning("Skipping duplicate judge name: %r", judge.name)
            continue
        if not judge.model:
            logger.warning("Skipping judge %r with no model", judge.name)
            continue
        seen_names.add(judge.name)
        judges.append(judge)

    return JudgeRegistry(judges=judges)


def save_judges(registry: JudgeRegistry) -> None:
    """Persist the registry to disk atomically."""
    os.makedirs(os.path.dirname(JUDGES_FILE), exist_ok=True)
    payload = {"judges": [j.to_dict() for j in registry.judges]}
    tmp_path = f"{JUDGES_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, JUDGES_FILE)


def add_judge(judge: JudgeConfig) -> None:
    """Add a judge. Raises ValueError on name conflict or validation error."""
    err = validate_name(judge.name)
    if err:
        raise ValueError(err)
    if not judge.model:
        raise ValueError("Model must not be empty.")

    registry = load_judges()
    if registry.find(judge.name) is not None:
        raise ValueError(f"A judge named {judge.name!r} already exists.")
    registry.judges.append(judge)
    save_judges(registry)


def update_judge(
    name: str,
    /,
    *,
    new_name: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    enabled: bool | None = None,
) -> None:
    """Update fields of an existing judge.

    ``name`` is positional-only so it doesn't collide with the ``new_name``
    kwarg used to rename a judge. Pass ``None`` for any field to leave it
    unchanged.
    """
    registry = load_judges()
    existing = registry.find(name)
    if existing is None:
        raise ValueError(f"No judge named {name!r}.")

    if new_name is not None and new_name != existing.name:
        err = validate_name(new_name)
        if err:
            raise ValueError(err)
        if registry.find(new_name) is not None:
            raise ValueError(f"A judge named {new_name!r} already exists.")
        existing.name = new_name

    if model is not None:
        if not model:
            raise ValueError("Model must not be empty.")
        existing.model = model

    if prompt is not None:
        existing.prompt = prompt or DEFAULT_JUDGE_PROMPT

    if enabled is not None:
        existing.enabled = bool(enabled)

    save_judges(registry)


def delete_judge(name: str) -> bool:
    """Remove a judge. Returns True if it existed."""
    registry = load_judges()
    before = len(registry.judges)
    registry.judges = [j for j in registry.judges if j.name != name]
    if len(registry.judges) == before:
        return False
    save_judges(registry)
    return True


def toggle_judge(name: str) -> bool | None:
    """Flip the enabled flag for a judge. Returns the new state, or None if missing."""
    registry = load_judges()
    judge = registry.find(name)
    if judge is None:
        return None
    judge.enabled = not judge.enabled
    save_judges(registry)
    return judge.enabled


def get_enabled_judges_or_default(fallback_model: str) -> list[JudgeConfig]:
    """Return the list of enabled judges, or a single default judge.

    If the user has configured judges via /judges, those are used. Otherwise
    we synthesize a single default judge using ``fallback_model`` and the
    standard goal-judge prompt so /goal works out-of-the-box.
    """
    registry = load_judges()
    enabled = registry.enabled()
    if enabled:
        return enabled
    return [
        JudgeConfig(
            name="default",
            model=fallback_model,
            prompt=DEFAULT_JUDGE_PROMPT,
            enabled=True,
        )
    ]
