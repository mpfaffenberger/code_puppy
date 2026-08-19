"""Live integration test for summarization-failure → truncation fallback.

Pins both the main agent and the summarization sub-agent to ``LILAC_MODEL``
(Kimi K2.6, 262k context window via LILAC_API_KEY), then stuffs ~500k tokens of
synthetic message history into the agent and sends a trivial prompt.

Expected flow:
    1. ``compact()`` sees 500k > 262k * 0.5 threshold → strategy=summarization.
    2. The harness ``SummarizingCompaction`` asks the summarizer model to chew
       on the oversized prefix.
    3. Kimi K2.6's 262k context window rejects the request server-side with a
       ``ModelAPIError``.
    4. ``FallbackCompaction`` catches it and advances to
       ``SlidingWindowCompaction``.
    5. The slid history fits, main agent completes the "hi" turn cleanly.

What we assert:
    - Summarization was *attempted* (not silently skipped).
    - Summarization actually *failed* (raised an exception).
    - The sliding-window fallback *executed*.
    - History shrank to fit inside the context window.
    - Run completed and produced a response.
    - History integrity preserved (no orphan tool pairs, ends with ModelRequest).

Skips gracefully if ``LILAC_API_KEY`` is not set.

Run:

    LILAC_API_KEY=xxx uv run pytest \
        tests/integration/test_compaction_summarization_fallback_live.py -v -s
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.messages import ModelRequest

from tests.integration.test_compaction_live import (
    LILAC_MODEL,
    _build_huge_history,
    _count_orphan_tool_ids,
    _lilac_key_available,
    _lilac_model_present,
)

# -- Gate on LILAC_API_KEY + model presence -----------------------------------

# NOTE: ``_lilac_key_available`` is imported (not redefined) from
# ``test_compaction_live`` so both live suites share ONE source of truth for
# the key/CI gate. That helper already skips when CI=1 (no real Lilac provider
# in CI) and when only a fake placeholder secret is present -- which is exactly
# what kept these tests from being silently run-and-failed in CI.


def _live_lilac_skip_reason() -> str | None:
    """Skip reason if the live lilac model isn't usable, else None.

    models.json ships empty, so this guards BOTH that the key is set AND that
    the lilac model was actually added to extra_models.json — otherwise the
    run would fail opaquely (run_with_mcp returns None) instead of skipping.
    """
    if not _lilac_key_available():
        return "LILAC_API_KEY not set (env or puppy.cfg); lilac fallback test skipped."
    if not _lilac_model_present():
        return (
            f"{LILAC_MODEL!r} not found in models config — models.json is empty "
            "and it was never added to ~/.code_puppy/extra_models.json; "
            "lilac fallback test skipped."
        )
    return None


pytestmark = pytest.mark.skipif(
    _live_lilac_skip_reason() is not None,
    reason=_live_lilac_skip_reason() or "",
)


# Override the autouse pexpect-gating fixture from tests/integration/conftest.py;
# this file is SDK-based, no TTY required.
@pytest.fixture(autouse=True)
def _require_integration_env_vars():
    yield


# -- Agent fixture pinned to LILAC_MODEL --------------------------------------


@pytest.fixture
def lilac_agent(monkeypatch):
    """Fresh CodePuppyAgent pinned to ``LILAC_MODEL`` (Kimi K2.6, 262k ctx)."""
    from code_puppy import config as cp_config
    from code_puppy.agents import _builder, _compaction, _runtime
    from code_puppy.agents import base_agent as _base_agent_mod
    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    pinned = LILAC_MODEL

    # models.json is empty: this model only exists if added to
    # extra_models.json. Module-level skip already guards it; assert here too
    # so a bypass surfaces as "model not added" rather than an opaque None.
    from code_puppy.model_factory import ModelFactory

    assert pinned in ModelFactory.load_config(), (
        f"{pinned!r} is not in the model config. models.json ships empty; "
        "add it to ~/.code_puppy/extra_models.json (CI does this in the "
        "'Provision CI model' step)."
    )

    # `from code_puppy.config import foo` captures bindings at import time, so
    # patch every site that re-imports the model-name getters.
    for mod in (cp_config, _base_agent_mod):
        if hasattr(mod, "get_global_model_name"):
            monkeypatch.setattr(mod, "get_global_model_name", lambda: pinned)
        if hasattr(mod, "get_agent_pinned_model"):
            monkeypatch.setattr(mod, "get_agent_pinned_model", lambda _n: pinned)

    # Critical: summarizer ALSO uses the 262k-ctx lilac model so it will choke
    # on the 480k-token summarization payload — that's the whole point of this test.
    monkeypatch.setattr(_compaction, "get_summarization_model_name", lambda: pinned)

    # No MCP / no DBOS — keep the test surface small.
    monkeypatch.setenv("disable_mcp_servers", "true")
    for mod in (cp_config, _builder, _runtime):
        if hasattr(mod, "get_use_dbos"):
            monkeypatch.setattr(mod, "get_use_dbos", lambda: False)

    return CodePuppyAgent()


# -- The test -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarization_oversize_falls_back_to_truncation(
    lilac_agent, monkeypatch
):
    """500k-token history + Kimi K2.6 (262k ctx) + summarization strategy →
    summarization sub-agent rejects the oversized payload → compact() catches
    the failure and falls back to truncation → main run still completes.
    """
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    # Force summarization strategy with a low threshold so compaction fires
    # immediately, and a small protected window so the summarizer is asked
    # to chew on a payload that DEFINITELY wont fit in 262k.
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "summarization")
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.5)
    monkeypatch.setattr(_compaction, "get_protected_token_count", lambda: 20_000)

    # -- Spies ----------------------------------------------------------------
    # We need to confirm BOTH that summarization was attempted AND raised,
    # AND that the sliding-window fallback executed. Spy on the two harness
    # strategies FallbackCompaction drives.
    from pydantic_ai_harness.compaction import (
        SlidingWindowCompaction,
        SummarizingCompaction,
    )

    summarize_spy = {"calls": 0, "raised": False, "error_type": None}
    orig_summarize_compact = SummarizingCompaction.compact

    async def spy_summarize_compact(self, messages, ctx):
        summarize_spy["calls"] += 1
        try:
            return await orig_summarize_compact(self, messages, ctx)
        except Exception as e:
            summarize_spy["raised"] = True
            summarize_spy["error_type"] = type(e).__name__
            raise

    monkeypatch.setattr(SummarizingCompaction, "compact", spy_summarize_compact)

    sliding_spy = {"calls": 0, "before": 0, "kept": 0}
    orig_sliding_compact = SlidingWindowCompaction.compact

    async def spy_sliding_compact(self, messages, ctx):
        sliding_spy["calls"] += 1
        sliding_spy["before"] = len(messages)
        result = await orig_sliding_compact(self, messages, ctx)
        sliding_spy["kept"] = len(result)
        return result

    monkeypatch.setattr(SlidingWindowCompaction, "compact", spy_sliding_compact)

    # -- Exception spy (to detect rate limits swallowed by run_agent_task) ---
    from code_puppy.agents import _runtime as _runtime_mod
    from code_puppy.agents._diagnostics import emit_exception_diagnostics

    _captured_exceptions: list[BaseException] = []
    orig_emit_diag = emit_exception_diagnostics

    def spy_emit_diag(exc: BaseException, **kwargs: Any) -> None:
        _captured_exceptions.append(exc)
        return orig_emit_diag(exc, **kwargs)

    monkeypatch.setattr(_runtime_mod, "emit_exception_diagnostics", spy_emit_diag)

    # -- History setup --------------------------------------------------------
    # 500k tokens — well over the 262k ctx window. The summarization payload
    # (history minus ~20k protected tail) will be ~480k → guaranteed reject.
    history = _build_huge_history(target_tokens=500_000)
    before_tokens = sum(estimate_tokens_for_message(m) for m in history)
    before_len = len(history)

    print(f"\n[pre-run]  history: {before_len} msgs, ~{before_tokens:,} tokens")
    assert before_tokens > 400_000, (
        f"Test setup bug: only built {before_tokens:,} tokens, need >400k to "
        "guarantee summarizer overflow."
    )

    lilac_agent.set_message_history(list(history))

    # -- Kick the run ---------------------------------------------------------
    result = await lilac_agent.run_with_mcp("hi")

    # -- Rate-limit guard ------------------------------------------------------
    # Live integration tests can hit 429s from the provider. If run_with_mcp
    # returned None because of a rate-limit that exhausted retries, skip
    # rather than fail — the compaction fallback machinery itself is sound.
    if result is None:
        for exc in _captured_exceptions:
            status_code = getattr(exc, "status_code", None)
            if status_code == 429:
                pytest.skip(
                    f"Rate-limited by provider (429) — skipping live fallback test. "
                    f"Exception: {exc}"
                )
            # Also check nested exceptions (ExceptionGroup / cause chains)
            cause = getattr(exc, "__cause__", None)
            if cause and getattr(cause, "status_code", None) == 429:
                pytest.skip(
                    f"Rate-limited by provider (429) — skipping live fallback test. "
                    f"Cause: {cause}"
                )

    # -- Assertions -----------------------------------------------------------

    # Run produced something
    assert result is not None, "run_with_mcp returned None"
    response_text = (
        getattr(result, "output", None) or getattr(result, "data", None) or ""
    )
    response_text = str(response_text)
    print(f"[response] {response_text[:200]!r}")
    assert response_text.strip(), "Empty response — model didnt complete the turn"

    # CORE INVARIANT 1: summarization was attempted
    assert summarize_spy["calls"] >= 1, (
        "SummarizingCompaction was never driven — the FallbackCompaction chain "
        "didnt route to summarization at all"
    )

    # CORE INVARIANT 2: summarization failed (raised)
    assert summarize_spy["raised"], (
        f"Summarization unexpectedly succeeded — the 500k payload should have "
        f"overflowed Kimi K2.6's 262k ctx. Spy: {summarize_spy}"
    )
    print(
        f"[summarize] attempts={summarize_spy['calls']} "
        f"raised={summarize_spy['raised']} ({summarize_spy['error_type']})"
    )

    # CORE INVARIANT 3: sliding-window fallback executed
    assert sliding_spy["calls"] >= 1, (
        "SlidingWindowCompaction was never driven — fallback path didnt fire. "
        f"Spy: {sliding_spy}"
    )
    assert sliding_spy["kept"] < sliding_spy["before"], (
        f"Fallback sliding window didnt drop anything: {sliding_spy}"
    )
    print(
        f"[sliding-fallback] calls={sliding_spy['calls']} "
        f"before={sliding_spy['before']} kept={sliding_spy['kept']}"
    )

    # CORE INVARIANT 4: history shrank dramatically
    after_history = lilac_agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after_history)
    print(
        f"[post-run] history: {len(after_history)} msgs, ~{after_tokens:,} tokens "
        f"(reduced {(1 - after_tokens / before_tokens) * 100:.1f}%)"
    )
    assert after_tokens < before_tokens, (
        f"History token count did not drop: {before_tokens:,} → {after_tokens:,}"
    )
    # After the sliding window the history must fit inside the model's window
    # with generous headroom (keep_tokens is patched to 20k, so anything near
    # 190k means the window barely slid at all).
    assert after_tokens < 190_000, (
        f"Slid history ({after_tokens:,} tokens) is nowhere near the "
        "20k protected tail — the sliding window didnt reduce enough."
    )

    # CORE INVARIANT 5: history integrity preserved
    orphan_calls, orphan_returns = _count_orphan_tool_ids(after_history)
    assert not orphan_calls, f"Orphan tool_calls in compacted history: {orphan_calls}"
    assert not orphan_returns, (
        f"Orphan tool_returns in compacted history: {orphan_returns}"
    )
    assert isinstance(after_history[-1], ModelRequest), (
        f"History must end with ModelRequest, got {type(after_history[-1]).__name__}"
    )
