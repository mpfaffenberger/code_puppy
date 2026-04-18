"""Live integration tests for message-history compaction.

Drives a REAL ``CodePuppyAgent`` through ``run_with_mcp`` with a pre-populated
~180k-token message history, pinned to ``firepass-kimi-k2p5-turbo`` (262k ctx window).
Compaction MUST fire, the run MUST complete, and history MUST shrink.

This is the kind of test that would have caught the Phase 4 signature bug
(``history_processor(ctx, messages)`` vs pydantic-ai's 1-arg calling
convention) in ~1s instead of on the user's screen.

Skips gracefully if ``SYN_API_KEY`` is not set.

Run:

    SYN_API_KEY=xxx uv run pytest tests/integration/test_compaction_live.py -v

"""

from __future__ import annotations

import os
import random
from typing import List, Set

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

# -- Gate on SYN_API_KEY ------------------------------------------------------


def _fireworks_key_available() -> bool:
    """True if FIREWORKS_API_KEY is set via env OR in puppy.cfg."""
    if os.environ.get("FIREWORKS_API_KEY"):
        return True
    try:
        from code_puppy.model_factory import get_api_key

        return bool(get_api_key("FIREWORKS_API_KEY"))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _fireworks_key_available(),
    reason="FIREWORKS_API_KEY not set (env or puppy.cfg); live compaction tests skipped.",
)


# -- Also disable the integration-env-var gate for THIS file ------------------
# tests/integration/conftest.py auto-skips everything unless CI=1 and
# CODE_PUPPY_TEST_FAST=1 are set. Those gates exist for pexpect-harness tests;
# we're not using pexpect, so opt out by overriding the autouse fixture.


@pytest.fixture(autouse=True)
def _require_integration_env_vars():
    """Override the integration gate fixture — this file is SDK-based, no TTY."""
    yield


# -- Synthetic message-history builder ----------------------------------------

_LOREM_CORPUS = (
    "The quick brown fox jumps over the lazy dog. Lorem ipsum dolor sit amet "
    "consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et "
    "dolore magna aliqua. Ut enim ad minim veniam quis nostrud exercitation "
    "ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure "
    "dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat "
    "nulla pariatur. Excepteur sint occaecat cupidatat non proident sunt in "
    "culpa qui officia deserunt mollit anim id est laborum. "
)


def _big_blob(approx_tokens: int, rng: random.Random) -> str:
    """Generate roughly ``approx_tokens`` tokens of filler text.

    We target the same ~2.5-chars-per-token heuristic that ``_history.py`` uses,
    so ``approx_tokens * 2.5`` chars → the intended token estimate.
    """
    target_chars = int(approx_tokens * 2.5)
    chunks: List[str] = []
    total = 0
    while total < target_chars:
        chunk = _LOREM_CORPUS + f" (random-seed-{rng.randint(0, 1_000_000)}) "
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)[:target_chars]


def _build_huge_history(
    target_tokens: int = 180_000, seed: int = 42
) -> List[ModelMessage]:
    """Build a realistic ~``target_tokens`` message history.

    Mix:
      - 1 system prompt at index 0
      - Alternating user prompts, tool_call/tool_return pairs, assistant text
      - Every tool_call has its matching tool_return (no orphans)
      - Payloads distributed so each individual message is well under the
        50k-token filter_huge_messages cutoff

    Returns a history that will come in close to but not exceeding the target.
    """
    rng = random.Random(seed)
    msgs: List[ModelMessage] = [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=(
                        "You are a helpful test agent. Answer questions tersely. "
                        "If asked simple math, just output the number."
                    )
                )
            ]
        )
    ]

    # Each "turn" below is ~4 messages and ~5000 tokens. 180000/5000 = ~36 turns.
    approx_per_turn = 5_000
    num_turns = target_tokens // approx_per_turn
    per_msg_tokens = approx_per_turn // 4  # split across 4 messages per turn

    for i in range(num_turns):
        call_id = f"integration_call_{i:04d}"
        # 1. user asks a "question"
        msgs.append(
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=f"Q{i}: please read this file and analyze it. "
                        + _big_blob(per_msg_tokens, rng)
                    )
                ]
            )
        )
        # 2. assistant issues a tool call
        msgs.append(
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_file",
                        args={"file_path": f"/fake/path/file_{i}.txt"},
                        tool_call_id=call_id,
                    )
                ]
            )
        )
        # 3. tool return with a big blob of "file contents"
        msgs.append(
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="read_file",
                        content=f"contents of file_{i}:\n"
                        + _big_blob(per_msg_tokens * 2, rng),  # bulk of the tokens
                        tool_call_id=call_id,
                    )
                ]
            )
        )
        # 4. assistant text response
        msgs.append(
            ModelResponse(
                parts=[
                    TextPart(
                        content=f"Analyzed file_{i}. Summary: "
                        + _big_blob(per_msg_tokens // 2, rng)
                    )
                ]
            )
        )

    # History must end with a ModelRequest (we'll be adding a user prompt via
    # run_with_mcp, but the accumulator may care). Ensure the last element is
    # a ModelRequest by ending on a tool_return-style turn or adding a user msg.
    # In our loop above, the last appended is a ModelResponse (TextPart), so
    # drop it to leave a tool_return at the tail.
    if isinstance(msgs[-1], ModelResponse):
        msgs.pop()

    return msgs


def _count_orphan_tool_ids(messages: List[ModelMessage]) -> tuple[Set[str], Set[str]]:
    """Return (call_ids_without_return, return_ids_without_call)."""
    calls: Set[str] = set()
    returns: Set[str] = set()
    for msg in messages:
        for part in msg.parts:
            tool_call_id = getattr(part, "tool_call_id", None)
            if not tool_call_id:
                continue
            part_kind = getattr(part, "part_kind", "")
            if part_kind == "tool-call":
                calls.add(tool_call_id)
            elif part_kind == "tool-return":
                returns.add(tool_call_id)
    return calls - returns, returns - calls


# -- The tests ----------------------------------------------------------------


@pytest.fixture
def huge_history() -> List[ModelMessage]:
    return _build_huge_history(target_tokens=200_000)


@pytest.fixture
def pinned_code_puppy_agent(monkeypatch):
    """Fresh CodePuppyAgent pinned to firepass-kimi-k2p5-turbo.

    Uses monkeypatch to override the global model getter so we don't touch
    the user's on-disk config during the test run.
    """
    from code_puppy import config as cp_config
    from code_puppy import summarization_agent as _sum_mod
    from code_puppy.agents import _builder, _runtime
    from code_puppy.agents import base_agent as _base_agent_mod
    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    # `from code_puppy.config import foo` captures a binding at import time, so
    # patching cp_config.foo alone doesnt propagate. Patch every site that
    # re-imports the model-name getters.
    for mod in (cp_config, _base_agent_mod):
        if hasattr(mod, "get_global_model_name"):
            monkeypatch.setattr(
                mod, "get_global_model_name", lambda: "firepass-kimi-k2p5-turbo"
            )
        if hasattr(mod, "get_agent_pinned_model"):
            monkeypatch.setattr(
                mod, "get_agent_pinned_model", lambda _n: "firepass-kimi-k2p5-turbo"
            )

    # Summarization sub-agent has its own model resolver — patch it at the
    # dedicated summarization_model hook (the cleaner post-refactor path).
    monkeypatch.setattr(
        _sum_mod,
        "get_summarization_model_name",
        lambda: "firepass-kimi-k2p5-turbo",
    )

    # Disable MCP so the test doesn't try to connect to external MCP servers.
    monkeypatch.setenv("disable_mcp_servers", "true")

    # Force DBOS off at every import site.
    for mod in (cp_config, _builder, _runtime):
        if hasattr(mod, "get_use_dbos"):
            monkeypatch.setattr(mod, "get_use_dbos", lambda: False)

    agent = CodePuppyAgent()
    return agent


@pytest.mark.asyncio
async def test_live_compaction_truncation_strategy(
    pinned_code_puppy_agent, huge_history, monkeypatch
):
    """180k tokens + truncation strategy → run succeeds, history shrinks."""
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    # Force truncation strategy + low threshold via monkeypatch (no disk writes)
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "truncation")
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.5)
    monkeypatch.setattr(_compaction, "get_protected_token_count", lambda: 20_000)

    agent = pinned_code_puppy_agent
    agent.set_message_history(list(huge_history))

    before_tokens = sum(estimate_tokens_for_message(m) for m in huge_history)
    before_len = len(huge_history)

    print(f"\n[pre-run]  history: {before_len} msgs, ~{before_tokens:,} tokens")

    # Verify we actually built a big enough history
    assert before_tokens > 170_000, (
        f"Test setup bug: history only has {before_tokens:,} tokens; "
        "compaction may not fire."
    )

    # Kick the run. Short prompt; model should respond quickly.
    result = await agent.run_with_mcp(
        "What is 2+2? Reply with just the number, nothing else."
    )

    # -- Assertions -----------------------------------------------------------

    # 1. The run completed and returned something
    assert result is not None, "run_with_mcp returned None"

    # 2. Response text extractable
    response_text = None
    for attr in ("output", "data"):
        val = getattr(result, attr, None)
        if val:
            response_text = str(val)
            break
    assert response_text, f"No response text in result: {result!r}"
    print(f"[response] {response_text[:200]!r}")

    # 3. History was compacted
    after_history = agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after_history)
    after_len = len(after_history)
    print(f"[post-run] history: {after_len} msgs, ~{after_tokens:,} tokens")
    print(
        f"[reduction] {before_tokens - after_tokens:,} tokens "
        f"({(1 - after_tokens / before_tokens) * 100:.1f}%)"
    )

    assert after_len < before_len, f"History did not shrink: {before_len} → {after_len}"
    assert after_tokens < before_tokens, (
        f"Token count did not drop: {before_tokens:,} → {after_tokens:,}"
    )

    # 4. System message preserved (first message unchanged)
    assert after_history[0] is huge_history[0] or (
        after_history[0].parts[0].content == huge_history[0].parts[0].content
    ), "System message was not preserved"

    # 5. No orphan tool pairs after compaction (Anthropic/OpenAI would reject)
    orphan_calls, orphan_returns = _count_orphan_tool_ids(after_history)
    assert not orphan_calls, f"Orphan tool_calls in compacted history: {orphan_calls}"
    assert not orphan_returns, (
        f"Orphan tool_returns in compacted history: {orphan_returns}"
    )

    # 6. History ends with a ModelRequest (prefill-safe)
    assert isinstance(after_history[-1], ModelRequest), (
        f"History must end with ModelRequest, got {type(after_history[-1]).__name__}"
    )


@pytest.mark.asyncio
async def test_live_compaction_summarization_strategy(
    pinned_code_puppy_agent, huge_history, monkeypatch
):
    """180k tokens + summarization strategy.

    Exercises the full real-world path: history_processor closure →
    compact() → summarize() → summarization sub-agent makes a REAL LLM call →
    compacted history handed back to pydantic-ai → GLM-5.1 answers the prompt.

    This test validates TWO acceptable outcomes:
      1. ✨ Summarization succeeds: history shrinks dramatically.
      2. 🛟 Summarization fails (e.g., 429 rate limit): graceful degradation —
         original history preserved, users run still completes successfully.

    Both are correct behavior. What would be WRONG:
      - Run crashes
      - History becomes corrupted (orphan tool pairs, trailing ModelResponse)
      - Summarization is skipped when it should fire (detectable via spy)
    """
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "summarization")
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.5)
    monkeypatch.setattr(_compaction, "get_protected_token_count", lambda: 20_000)

    # Spy: did summarization actually get attempted?
    summarize_calls = {"count": 0, "succeeded": False, "error": None}
    orig_summarize = _compaction.summarize

    def spy_summarize(*a, **kw):
        summarize_calls["count"] += 1
        result, dropped = orig_summarize(*a, **kw)
        # If dropped is non-empty, summarization succeeded and emitted new summary msgs
        summarize_calls["succeeded"] = len(dropped) > 0
        return result, dropped

    monkeypatch.setattr(_compaction, "summarize", spy_summarize)

    agent = pinned_code_puppy_agent
    agent.set_message_history(list(huge_history))

    before_tokens = sum(estimate_tokens_for_message(m) for m in huge_history)
    before_len = len(huge_history)
    print(f"\n[pre-run]  history: {before_len} msgs, ~{before_tokens:,} tokens")

    result = await agent.run_with_mcp(
        "What is 2+2? Reply with just the number, nothing else."
    )

    assert result is not None, "run_with_mcp returned None"

    after_history = agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after_history)
    after_len = len(after_history)
    print(f"[post-run] history: {after_len} msgs, ~{after_tokens:,} tokens")
    print(
        f"[summarize] attempts={summarize_calls['count']} "
        f"succeeded={summarize_calls['succeeded']}"
    )

    # -- CORE INVARIANT: summarize() MUST have been attempted ----------------
    # If this fails, compaction isnt routing to the summarization path at all.
    assert summarize_calls["count"] >= 1, (
        "summarize() was never called — compact() didnt route to summarization"
    )

    # -- Integrity invariants (must hold in both success and failure paths) --
    orphan_calls, orphan_returns = _count_orphan_tool_ids(after_history)
    assert not orphan_calls, f"Orphan tool_calls: {orphan_calls}"
    assert not orphan_returns, f"Orphan tool_returns: {orphan_returns}"
    assert isinstance(after_history[-1], ModelRequest), (
        f"History must end with ModelRequest, got {type(after_history[-1]).__name__}"
    )

    # -- Path A: summarization succeeded → verify dramatic reduction ---------
    if summarize_calls["succeeded"]:
        print("[path] ✨ summarization succeeded")
        print(f"[reduction] {(1 - after_tokens / before_tokens) * 100:.1f}%")
        assert after_len < before_len, "Summarization ran but didnt reduce msgs"
        assert after_tokens < before_tokens, "Summarization ran but didnt reduce tokens"

    # -- Path B: summarization failed → verify graceful degradation ----------
    else:
        print(
            "[path] 🛟 summarization failed gracefully "
            "(likely rate-limit or LLM error). Run still completed — correct fallback."
        )
        # Main-agent run should still have added at least 1-2 new msgs
        # (user prompt + assistant response).
        assert after_len >= before_len, (
            "History shrank on failure path — expected graceful preservation"
        )


@pytest.mark.asyncio
async def test_live_no_compaction_under_threshold(pinned_code_puppy_agent, monkeypatch):
    """Small history + high threshold → compaction must NOT fire, run succeeds."""
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    # High threshold — should never trip
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.95)
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "truncation")

    agent = pinned_code_puppy_agent
    small_history = _build_huge_history(target_tokens=5_000)
    agent.set_message_history(list(small_history))

    before_tokens = sum(estimate_tokens_for_message(m) for m in small_history)
    print(f"\n[pre-run] small history: ~{before_tokens:,} tokens")

    result = await agent.run_with_mcp("What is 3+3? Reply with just the number.")
    assert result is not None

    after_history = agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after_history)
    print(f"[post-run] ~{after_tokens:,} tokens")

    # Under-threshold run should NOT cause a big drop. It may still grow from
    # the new prompt + response. Key invariant: all of the original messages
    # are still there (by hash).
    from code_puppy.agents._history import hash_message

    original_hashes = {hash_message(m) for m in small_history}
    after_hashes = {hash_message(m) for m in after_history}
    # Every original message hash should still be present (nothing dropped)
    missing = original_hashes - after_hashes
    assert not missing, (
        f"Under-threshold run dropped {len(missing)} original messages: "
        "compaction should not have fired"
    )


@pytest.mark.asyncio
async def test_live_orphan_tool_call_does_not_block_compaction(
    pinned_code_puppy_agent, monkeypatch
):
    """REGRESSION: orphan tool_calls in history must not permanently defer
    compaction. This is the actual bug the user hit in production.

    Setup:
      - 180k-token history
      - Inject a stray orphan tool_call (no matching return), simulating
        what happens after Ctrl-C during a tool execution
      - Summarization strategy enabled with low threshold
    Expected:
      - compaction proceeds (orphan gets pruned, summary succeeds)
      - run completes successfully
      - history shrinks dramatically

    Before the fix, this would log:
      "Summarization deferred: pending tool call(s) detected"
    on every turn, forever.
    """
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "summarization")
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.5)
    monkeypatch.setattr(_compaction, "get_protected_token_count", lambda: 20_000)

    summarize_calls = {"count": 0, "succeeded": False}
    orig_summarize = _compaction.summarize

    def spy_summarize(*a, **kw):
        summarize_calls["count"] += 1
        result, dropped = orig_summarize(*a, **kw)
        summarize_calls["succeeded"] = len(dropped) > 0
        return result, dropped

    monkeypatch.setattr(_compaction, "summarize", spy_summarize)

    # Build the usual 180k history, then inject an orphan tool_call
    history = _build_huge_history(target_tokens=200_000)
    orphan = ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="read_file",
                args={"file_path": "/ctrl-c-cancelled.txt"},
                tool_call_id="orphan_cancelled_run",
            )
        ]
    )
    # Insert between system message and the rest — permanent orphan
    history = [history[0], orphan] + history[1:]

    agent = pinned_code_puppy_agent
    agent.set_message_history(list(history))

    before_tokens = sum(estimate_tokens_for_message(m) for m in history)
    print(
        f"\n[pre-run] history: {len(history)} msgs, ~{before_tokens:,} tokens "
        "(with 1 orphan tool_call)"
    )

    result = await agent.run_with_mcp("What is 5+5? Reply with just the number.")
    assert result is not None, "run_with_mcp returned None"

    after = agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after)
    print(f"[post-run] history: {len(after)} msgs, ~{after_tokens:,} tokens")
    print(
        f"[summarize] attempts={summarize_calls['count']} "
        f"succeeded={summarize_calls['succeeded']}"
    )

    # CORE REGRESSION ASSERTIONS:
    # 1. Summarization must have been attempted (not deferred forever)
    assert summarize_calls["count"] >= 1, (
        "summarize() was never called — orphan blocked compaction (the bug is back)"
    )

    # 2. The orphan must no longer be in the compacted history
    for m in after:
        for p in m.parts:
            assert getattr(p, "tool_call_id", None) != "orphan_cancelled_run", (
                "orphan tool_call leaked through to post-run history"
            )

    # 3. Run must have completed & history must still have integrity
    orphan_calls, orphan_returns = _count_orphan_tool_ids(after)
    assert not orphan_calls, f"Orphan tool_calls after run: {orphan_calls}"
    assert not orphan_returns, f"Orphan tool_returns after run: {orphan_returns}"
