#!/usr/bin/env python3
"""Optional live-model QA benchmark for compaction resumability.

This script is intentionally outside the normal pytest suite. It calls a real
model, so it is slower, costs money, and can vary slightly between runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

import code_puppy.config as cp_config
from code_puppy.agents import _compaction
from code_puppy.agents._history import estimate_tokens_for_message
from code_puppy.agents.threshold_compaction.storage import (
    MASKED_OBSERVATION_MARKER,
    observations_dir,
)


@dataclass(frozen=True)
class Scenario:
    name: str
    goal: str
    constraints: list[str]
    active_files: list[str]
    invalidated_hypotheses: list[str]
    current_error_key: str
    next_action: str


@dataclass
class EvalCase:
    strategy: str
    scenario: Scenario
    messages: list[ModelMessage]
    prompt_text: str
    archive_text: str
    token_count: int
    message_count: int
    masked_count: int
    archive_count: int
    tool_pairs_valid: bool


class FakeAgent:
    name = "live-qa-eval-agent"
    id = "live-qa-eval-agent-id"

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._threshold_compaction_stats = {
            "previous_total_tokens": None,
            "turn_growth_history": [],
        }

    def get_model_name(self) -> str:
        return "fake-model"


def _sys_msg(text: str = "system prompt") -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _user_msg(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


def _tool_call(tool_name: str, args: dict[str, Any], call_id: str) -> ModelMessage:
    return ModelResponse(
        parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=call_id)]
    )


def _tool_return(tool_name: str, content: str, call_id: str) -> ModelMessage:
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name,
                content=content,
                tool_call_id=call_id,
            )
        ]
    )


def _message_text(messages: list[ModelMessage]) -> str:
    chunks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            if hasattr(part, "content"):
                chunks.append(str(getattr(part, "content")))
            if hasattr(part, "args"):
                chunks.append(json.dumps(getattr(part, "args"), sort_keys=True))
    return "\n".join(chunks)


def _archive_text(agent: FakeAgent) -> str:
    chunks: list[str] = []
    for archive_file in sorted(observations_dir(agent).glob("obs_*.json")):
        chunks.append(archive_file.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _token_count(messages: list[ModelMessage]) -> int:
    return sum(
        estimate_tokens_for_message(message, "fake-model") for message in messages
    )


def _tool_pairs_valid(messages: list[ModelMessage]) -> bool:
    calls: set[str] = set()
    returns: set[str] = set()
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            call_id = getattr(part, "tool_call_id", None)
            if not call_id:
                continue
            kind = getattr(part, "part_kind", None)
            if kind == "tool-call":
                calls.add(str(call_id))
            elif kind == "tool-return":
                returns.add(str(call_id))
    return calls == returns


def _scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="auth",
            goal=(
                "repair OAuth callback session replay without changing public CLI flags"
            ),
            constraints=[
                "do not change public CLI flags",
                "preserve backwards compatible config defaults",
                "no new dependencies",
            ],
            active_files=[
                "code_puppy/auth/callback.py",
                "tests/auth/test_callback.py",
                "code_puppy/config.py",
            ],
            invalidated_hypotheses=[
                "router layer",
                "token refresh timer",
                "browser redirect URI",
            ],
            current_error_key="SESSION-REPLAY-KEY-AUTH",
            next_action=(
                "patch callback state validation then rerun tests/auth/test_callback.py"
            ),
        ),
        Scenario(
            name="scheduler",
            goal="fix scheduler timezone drift across daylight saving transitions",
            constraints=[
                "keep persisted schedule format unchanged",
                "support America/Chicago explicitly",
                "do not rewrite daemon startup",
            ],
            active_files=[
                "code_puppy/scheduler/daemon.py",
                "tests/scheduler/test_dst.py",
                "code_puppy/scheduler/config.py",
            ],
            invalidated_hypotheses=[
                "cron parser",
                "database serializer",
                "daemon heartbeat",
            ],
            current_error_key="DST-DRIFT-KEY-SCHEDULER",
            next_action="normalize next_run with zoneinfo before persistence",
        ),
        Scenario(
            name="mcp",
            goal="stabilize MCP server restart recovery after failed health checks",
            constraints=[
                "leave server registry schema untouched",
                "do not lower health check coverage",
                "avoid async lifecycle rewrites",
            ],
            active_files=[
                "code_puppy/mcp_/manager.py",
                "tests/mcp/test_restart.py",
                "code_puppy/mcp_/health_monitor.py",
            ],
            invalidated_hypotheses=[
                "registry cache",
                "stdout capture",
                "retry jitter",
            ],
            current_error_key="MCP-RESTART-KEY-RECOVERY",
            next_action=(
                "add restart cooldown state and rerun tests/mcp/test_restart.py"
            ),
        ),
    ]


def _build_history(scenario: Scenario, tool_log_lines: int) -> list[ModelMessage]:
    history: list[ModelMessage] = [
        _sys_msg(),
        _user_msg(
            f"Task goal: {scenario.goal}. Hard constraints: "
            + "; ".join(scenario.constraints)
        ),
    ]
    for idx in range(1, 13):
        file_name = scenario.active_files[(idx - 1) % len(scenario.active_files)]
        hypothesis = scenario.invalidated_hypotheses[
            (idx - 1) % len(scenario.invalidated_hypotheses)
        ]
        call_id = f"{scenario.name}-call-{idx:02d}"
        noise = "\n".join(
            (
                f"irrelevant log line {line_idx:04d} "
                f"value={scenario.name}-{idx}-{line_idx}"
            )
            for line_idx in range(tool_log_lines)
        )
        status = (
            f"AssertionError {scenario.current_error_key} in {file_name}"
            if idx == 12
            else f"FAILED intermediate check in {file_name}"
        )
        history.extend(
            [
                _user_msg(
                    f"Iteration {idx}: continue {scenario.goal}. Must keep "
                    f"{scenario.constraints[idx % len(scenario.constraints)]}."
                ),
                _tool_call(
                    "run_shell_command",
                    {"command": f"pytest {file_name}"},
                    call_id,
                ),
                _tool_return(
                    "run_shell_command",
                    (
                        f"{status}\nFile: {file_name}\n{noise}\n"
                        f"DEEP-TRACE-{scenario.name}-{idx:02d}\n"
                    ),
                    call_id,
                ),
                _assistant_text(
                    f"Decision: {hypothesis} is not the root cause. "
                    f"Active file: {file_name}. "
                    f"Next action: {scenario.next_action}."
                ),
            ]
        )
    history.append(
        _user_msg(
            f"Latest request: finish {scenario.goal} and keep {scenario.next_action}."
        )
    )
    return history


def _compact_threshold(
    history: list[ModelMessage],
    agent: FakeAgent,
    cycles: int,
    model_window: int,
) -> list[ModelMessage]:
    compacted = history
    for _ in range(cycles):
        _compaction.get_compaction_strategy = lambda: "threshold"
        compacted, _ = _compaction.compact(
            agent,
            compacted,
            model_max=model_window,
            context_overhead=0,
            force=True,
        )
    return compacted


def _compact_legacy_strategy(
    strategy: str,
    history: list[ModelMessage],
    agent: FakeAgent,
    cycles: int,
    model_window: int,
    protected_tokens: int,
) -> list[ModelMessage]:
    compacted = history
    for _ in range(cycles):
        _compaction.get_compaction_strategy = lambda strategy=strategy: strategy
        _compaction.get_protected_token_count = (
            lambda protected_tokens=protected_tokens: protected_tokens
        )
        compacted, _ = _compaction.compact(
            agent,
            compacted,
            model_max=model_window,
            context_overhead=0,
            force=True,
        )
    return compacted


def _compact_truncation(
    history: list[ModelMessage],
    agent: FakeAgent,
    cycles: int,
    model_window: int,
    protected_tokens: int,
) -> list[ModelMessage]:
    return _compact_legacy_strategy(
        "truncation",
        history,
        agent,
        cycles,
        model_window,
        protected_tokens,
    )


def _compact_summarization(
    history: list[ModelMessage],
    agent: FakeAgent,
    cycles: int,
    model_window: int,
    protected_tokens: int,
) -> list[ModelMessage]:
    return _compact_legacy_strategy(
        "summarization",
        history,
        agent,
        cycles,
        model_window,
        protected_tokens,
    )


def _build_cases(
    *,
    strategies: list[str],
    cycles: int,
    model_window: int,
    tool_log_lines: int,
    protected_tokens: int,
) -> list[EvalCase]:
    compactors: dict[
        str,
        Callable[[list[ModelMessage], FakeAgent, int, int, int], list[ModelMessage]],
    ] = {
        "threshold": lambda history, agent, cycles, model_window, _protected: (
            _compact_threshold(history, agent, cycles, model_window)
        ),
        "truncation": _compact_truncation,
        "summarization": _compact_summarization,
    }
    unknown = sorted(set(strategies) - set(compactors))
    if unknown:
        raise ValueError(f"Unknown strategies: {', '.join(unknown)}")

    cases: list[EvalCase] = []
    for strategy in strategies:
        for scenario in _scenarios():
            agent = FakeAgent(session_id=f"live-qa-{strategy}-{scenario.name}")
            history = _build_history(scenario, tool_log_lines)
            compacted = compactors[strategy](
                history,
                agent,
                cycles,
                model_window,
                protected_tokens,
            )
            prompt_text = _message_text(compacted)
            archive_text = _archive_text(agent)
            cases.append(
                EvalCase(
                    strategy=strategy,
                    scenario=scenario,
                    messages=compacted,
                    prompt_text=prompt_text,
                    archive_text=archive_text,
                    token_count=_token_count(compacted),
                    message_count=len(compacted),
                    masked_count=prompt_text.count(MASKED_OBSERVATION_MARKER),
                    archive_count=len(list(observations_dir(agent).glob("obs_*.json"))),
                    tool_pairs_valid=_tool_pairs_valid(compacted),
                )
            )
    return cases


def _build_eval_prompt(case: EvalCase, include_archives: bool) -> str:
    archive_section = ""
    if include_archives and case.archive_text:
        archive_section = f"""

LOCAL ARCHIVE CONTENT
{case.archive_text}
"""
    return f"""You are evaluating whether a compacted coding-agent transcript
preserves enough state to resume the task.

Use ONLY the compacted transcript below. If LOCAL ARCHIVE CONTENT is present,
you may also use it. Do not use outside knowledge.

Return ONLY valid JSON with this exact shape:
{{
  "goal": string | null,
  "constraints": [string],
  "active_files": [string],
  "invalidated_hypotheses": [string],
  "current_error_key": string | null,
  "next_action": string | null,
  "archive_refs": [string],
  "confidence": number
}}

Copy exact phrases when available. Use null or [] rather than guessing.

COMPACTED TRANSCRIPT
{case.prompt_text}
{archive_section}
"""


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model output was not a JSON object")
    return value


def _field_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _grade(case: EvalCase, answer: dict[str, Any]) -> dict[str, Any]:
    scenario = case.scenario
    checks: list[tuple[str, str, Any]] = [
        ("goal", scenario.goal, answer.get("goal")),
        (
            "current_error_key",
            scenario.current_error_key,
            answer.get("current_error_key"),
        ),
        ("next_action", scenario.next_action, answer.get("next_action")),
    ]
    checks.extend(
        (f"constraint:{item}", item, answer.get("constraints", []))
        for item in scenario.constraints
    )
    checks.extend(
        (f"active_file:{item}", item, answer.get("active_files", []))
        for item in scenario.active_files
    )
    checks.extend(
        (
            f"invalidated_hypothesis:{item}",
            item,
            answer.get("invalidated_hypotheses", []),
        )
        for item in scenario.invalidated_hypotheses
    )
    missing = [
        label
        for label, expected, observed in checks
        if expected not in _field_text(observed)
    ]
    archive_refs = answer.get("archive_refs", [])
    if not isinstance(archive_refs, list):
        archive_refs = []
    return {
        "score": len(checks) - len(missing),
        "total": len(checks),
        "missing": missing,
        "archive_refs_reported": len(archive_refs),
        "archive_refs_expected_min": case.archive_count,
    }


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    return str(response)


def _call_openai(model: str, prompt: str, max_output_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=model,
        instructions=(
            "You are a precise evaluator. Return valid JSON only. "
            "Do not add markdown fences."
        ),
        input=prompt,
        max_output_tokens=max_output_tokens,
    )
    return _response_text(response)


def _write_prompt(path: Path, case: EvalCase, prompt: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{case.strategy}_{case.scenario.name}.txt").write_text(
        prompt,
        encoding="utf-8",
    )


def _make_record(
    *,
    case: EvalCase,
    model: str,
    include_archives: bool,
    answer_text: str | None,
    answer_json: dict[str, Any] | None,
    grade: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    scenario = asdict(case.scenario)
    return {
        "model": model,
        "strategy": case.strategy,
        "scenario": case.scenario.name,
        "include_archives": include_archives,
        "token_count": case.token_count,
        "message_count": case.message_count,
        "masked_count": case.masked_count,
        "archive_count": case.archive_count,
        "tool_pairs_valid": case.tool_pairs_valid,
        "expected": scenario,
        "answer_text": answer_text,
        "answer_json": answer_json,
        "grade": grade,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run optional live-model QA over compacted histories."
    )
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--strategies",
        default="threshold,truncation",
        help=(
            "Comma-separated strategies: threshold,truncation,summarization. "
            "Legacy strategies are routed through _compaction.compact()."
        ),
    )
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--model-window", type=int, default=200_000)
    parser.add_argument(
        "--legacy-protected-tokens",
        type=int,
        default=50_000,
        help=(
            "Recent-token budget used by legacy truncation/summarization. "
            "Defaults to Code Puppy's legacy default."
        ),
    )
    parser.add_argument("--tool-log-lines", type=int, default=750)
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    parser.add_argument(
        "--include-archives",
        action="store_true",
        help="Append local archive contents to the model prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build compacted prompts and write metadata without calling a model.",
    )
    parser.add_argument(
        "--write-prompts-dir",
        type=Path,
        help="Optional directory for prompt text files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/compaction_live_qa_eval.jsonl"),
    )
    args = parser.parse_args()

    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    if "summarization" in strategies and args.dry_run:
        print(
            "warning: summarization strategy still calls the configured "
            "summarization model while building compacted prompts."
        )
    with tempfile.TemporaryDirectory(prefix="code-puppy-live-qa-") as data_dir:
        cp_config.DATA_DIR = data_dir
        _compaction.get_compaction_strategy = lambda: "threshold"
        if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit(
                "OPENAI_API_KEY is not set. Re-run with OPENAI_API_KEY or "
                "use --dry-run to generate prompts only."
            )
        cases = _build_cases(
            strategies=strategies,
            cycles=args.cycles,
            model_window=args.model_window,
            tool_log_lines=args.tool_log_lines,
            protected_tokens=args.legacy_protected_tokens,
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        totals: dict[str, list[int]] = {}
        with args.output.open("w", encoding="utf-8") as output:
            for case in cases:
                prompt = _build_eval_prompt(case, args.include_archives)
                if args.write_prompts_dir:
                    _write_prompt(args.write_prompts_dir, case, prompt)

                answer_text: str | None = None
                answer_json: dict[str, Any] | None = None
                grade: dict[str, Any] | None = None
                error: str | None = None
                if not args.dry_run:
                    try:
                        answer_text = _call_openai(
                            args.model,
                            prompt,
                            args.max_output_tokens,
                        )
                        answer_json = _parse_json_object(answer_text)
                        grade = _grade(case, answer_json)
                    except Exception as exc:  # pragma: no cover - live diagnostic
                        error = f"{type(exc).__name__}: {exc}"

                record = _make_record(
                    case=case,
                    model=args.model,
                    include_archives=args.include_archives,
                    answer_text=answer_text,
                    answer_json=answer_json,
                    grade=grade,
                    error=error,
                )
                output.write(json.dumps(record, sort_keys=True) + "\n")

                if grade:
                    bucket = totals.setdefault(case.strategy, [0, 0])
                    bucket[0] += int(grade["score"])
                    bucket[1] += int(grade["total"])
                    score = f"{grade['score']}/{grade['total']}"
                else:
                    score = "dry-run" if args.dry_run else "error"
                print(
                    f"{case.strategy:10} {case.scenario.name:10} "
                    f"score={score:>7} tokens={case.token_count:>6} "
                    f"masked={case.masked_count:>2} archives={case.archive_count:>2} "
                    f"pairs={'ok' if case.tool_pairs_valid else 'bad'}"
                )
                if error:
                    print(f"  error: {error}")

        for strategy, (score, total) in totals.items():
            print(f"{strategy:10} TOTAL      score={score}/{total}")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
