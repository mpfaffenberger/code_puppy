from dataclasses import dataclass, field

from code_puppy.safety.classifier import (
    ActionCandidate,
    Decision,
    SafetyPolicy,
    TwoStageClassifier,
    Verdict,
    classify,
)

POLICY = SafetyPolicy(name="test", prompt_prefix="Block destructive file operations.")


@dataclass
class FakeBackend:
    flagged: bool
    verdict: Verdict = field(
        default_factory=lambda: Verdict(
            decision=Decision.BLOCK, reason="unsafe", stage=2
        )
    )
    screens: int = 0
    reviews: int = 0

    async def screen(self, candidate, policy):
        self.screens += 1
        assert candidate.tool_name == "delete_file"
        assert policy is POLICY
        return self.flagged

    async def review(self, candidate, policy):
        self.reviews += 1
        return self.verdict


async def test_stage_one_allow_skips_expensive_review():
    backend = FakeBackend(flagged=False)
    verdict = await TwoStageClassifier(backend).classify(
        "delete_file", {"path": "tmp.txt"}, POLICY
    )
    assert verdict.decision is Decision.ALLOW
    assert verdict.stage == 1
    assert backend.screens == 1
    assert backend.reviews == 0


async def test_flagged_action_runs_stage_two():
    backend = FakeBackend(flagged=True)
    verdict = await classify(
        "delete_file", {"path": "tmp.txt"}, POLICY, backend=backend
    )
    assert verdict.decision is Decision.BLOCK
    assert verdict.reason == "unsafe"
    assert verdict.stage == 2
    assert backend.reviews == 1


async def test_classifier_failure_fails_closed_to_ask():
    class BrokenBackend:
        async def screen(self, candidate, policy):
            raise TimeoutError("offline")

        async def review(self, candidate, policy):
            raise AssertionError("unreachable")

    verdict = await classify(
        "delete_file", {"path": "tmp.txt"}, POLICY, backend=BrokenBackend()
    )
    assert verdict.decision is Decision.ASK
    assert "TimeoutError" in verdict.reason


def test_candidate_serializes_only_action_fields():
    candidate = ActionCandidate("shell", {"command": "rm file"})
    payload = candidate.as_json()
    assert "tool_name" in payload
    assert "tool_input" in payload
    assert "history" not in payload
    assert "reasoning" not in payload
