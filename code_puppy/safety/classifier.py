"""Two-stage, provenance-blind safety classification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK = "ask"


class Verdict(BaseModel):
    decision: Decision
    reason: str = ""
    stage: int = Field(default=1, ge=1, le=2)


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Stable policy text shared by both model stages."""

    name: str
    prompt_prefix: str
    stage_one_question: str = "Could this action violate the policy?"
    stage_two_question: str = "Decide allow, block, or ask and explain briefly."


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    """The only information a judge receives (no assistant narrative/history)."""

    tool_name: str
    tool_input: dict[str, Any]

    def as_json(self) -> str:
        return json.dumps(
            {"tool_name": self.tool_name, "tool_input": self.tool_input},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


class DecisionBackend(Protocol):
    async def screen(
        self, candidate: ActionCandidate, policy: SafetyPolicy
    ) -> bool: ...

    async def review(
        self, candidate: ActionCandidate, policy: SafetyPolicy
    ) -> Verdict: ...


class TwoStageClassifier:
    """Cheap over-blocking screen followed by review only for flagged actions."""

    def __init__(self, backend: DecisionBackend):
        self.backend = backend

    async def classify(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        policy: SafetyPolicy,
    ) -> Verdict:
        candidate = ActionCandidate(tool_name=tool_name, tool_input=tool_input)
        try:
            flagged = await self.backend.screen(candidate, policy)
            if not flagged:
                return Verdict(decision=Decision.ALLOW, stage=1)
            verdict = await self.backend.review(candidate, policy)
            return verdict.model_copy(update={"stage": 2})
        except Exception as exc:
            return Verdict(
                decision=Decision.ASK,
                reason=f"classifier unavailable: {type(exc).__name__}: {exc}",
                stage=2,
            )


async def classify(
    tool_name: str,
    tool_input: dict[str, Any],
    policy: SafetyPolicy,
    *,
    backend: DecisionBackend | None = None,
) -> Verdict:
    """Classify an action without accepting history or agent reasoning."""
    if backend is None:
        from .model_backend import ModelDecisionBackend

        backend = ModelDecisionBackend()
    return await TwoStageClassifier(backend).classify(tool_name, tool_input, policy)
