"""Live integration test for summarization-failure → truncation fallback.

Pins both the main agent and the summarization sub-agent to ``synthetic-GLM-5.1``
(200k context window via SYN_API_KEY), then stuffs ~500k tokens of synthetic
message history into the agent and sends a trivial prompt.

Expected flow:
    1. ``compact()`` sees 500k > 200k * 0.5 threshold → strategy=summarization.
    2. ``split_for_protected_summarization`` carves off ~20k of recent tail.
    3. The summarization sub-agent gets ~480k tokens shoved at it.
    4. GLM-5.1's 200k context window rejects the request server-side.
    5. ``_run_summarization_core`` raises → ``compact()`` catches → falls back
       to ``_truncate_with_dropped``.
    6. Truncated history fits, main agent completes the "hi" turn cleanly.

What we assert:
    - Summarization was *attempted* (not silently skipped).
    - Summarization actually *failed* (raised an exception).
    - The truncation fallback path *executed*.
    - History shrank to fit inside the context window.
    - Run completed and produced a response.
    - History integrity preserved (no orphan tool pairs, ends with ModelRequest).

Skips gracefully if ``SYN_API_KEY`` is not set.

Run:

    SYN_API_KEY=xxx uv run pytest \
        tests/integration/test_compaction_summarization_fallback_live.py -v -s
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from pydantic_ai.messages import ModelRequest

from tests.integration.test_compaction_live import (
    _build_huge_history,
    _count_orphan_tool_ids,
)

# -- Gate on SYN_API_KEY ------------------------------------------------------


# CI injects fake placeholder values for unset secrets (see .github/workflows/*.yml).
# Treat those as "not set" so we skip instead of trying to auth against the real API
# and getting a 401 that we then swallow in run_with_mcp's broad except*.
_FAKE_CI_KEYS = {"fake-key-for-ci-testing", ""}


def _syn_key_available() -> bool:
    """True if SYN_API_KEY is set to a real-looking value (env OR puppy.cfg)."""
    env_key = os.environ.get("SYN_API_KEY", "").strip()
    if env_key and env_key not in _FAKE_CI_KEYS:
        return True
    try:
        from code_puppy.model_factory import get_api_key

        cfg_key = (get_api_key("SYN_API_KEY") or "").strip()
        return bool(cfg_key) and cfg_key not in _FAKE_CI_KEYS
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _syn_key_available(),
    reason="SYN_API_KEY not set (env or puppy.cfg); GLM-5.1 fallback test skipped.",
)


# Override the autouse pexpect-gating fixture from tests/integration/conftest.py;
# this file is SDK-based, no TTY required.
@pytest.fixture(autouse=True)
def _require_integration_env_vars():
    yield


# -- Agent fixture pinned to synthetic-GLM-5.1 --------------------------------


@pytest.fixture
def glm51_agent(monkeypatch):
    """Fresh CodePuppyAgent pinned to synthetic-GLM-5.1 (200k ctx)."""
    from code_puppy import config as cp_config
    from code_puppy import summarization_agent as _sum_mod
    from code_puppy.agents import _builder, _runtime
    from code_puppy.agents import base_agent as _base_agent_mod
    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    pinned = "synthetic-GLM-5.1"

    # `from code_puppy.config import foo` captures bindings at import time, so
    # patch every site that re-imports the model-name getters.
    for mod in (cp_config, _base_agent_mod):
        if hasattr(mod, "get_global_model_name"):
            monkeypatch.setattr(mod, "get_global_model_name", lambda: pinned)
        if hasattr(mod, "get_agent_pinned_model"):
            monkeypatch.setattr(mod, "get_agent_pinned_model", lambda _n: pinned)

    # Critical: summarizer ALSO uses GLM-5.1 (200k ctx) so it will choke on the
    # 480k-token summarization payload — that's the whole point of this test.
    monkeypatch.setattr(_sum_mod, "get_summarization_model_name", lambda: pinned)

    # No MCP / no DBOS — keep the test surface small.
    monkeypatch.setenv("disable_mcp_servers", "true")
    for mod in (cp_config, _builder, _runtime):
        if hasattr(mod, "get_use_dbos"):
            monkeypatch.setattr(mod, "get_use_dbos", lambda: False)

    return CodePuppyAgent()


# -- The test -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarization_oversize_falls_back_to_truncation(
    glm51_agent, monkeypatch
):
    """500k-token history + GLM-5.1 (200k ctx) + summarization strategy →
    summarization sub-agent rejects the oversized payload → compact() catches
    the failure and falls back to truncation → main run still completes.
    """
    from code_puppy.agents import _compaction
    from code_puppy.agents._history import estimate_tokens_for_message

    # Force summarization strategy with a low threshold so compaction fires
    # immediately, and a small protected window so the summarizer is asked
    # to chew on a payload that DEFINITELY wont fit in 200k.
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "summarization")
    monkeypatch.setattr(_compaction, "get_compaction_threshold", lambda: 0.5)
    monkeypatch.setattr(_compaction, "get_protected_token_count", lambda: 20_000)

    # -- Spies ----------------------------------------------------------------
    # We need to confirm BOTH that summarization was attempted AND raised,
    # AND that the truncation fallback executed. Spy on the two functions
    # compact() calls directly post-refactor.

    summarize_spy = {"calls": 0, "raised": False, "error_type": None}
    orig_summarize_core = _compaction._run_summarization_core

    def spy_summarize_core(*args, **kwargs):
        summarize_spy["calls"] += 1
        try:
            return orig_summarize_core(*args, **kwargs)
        except Exception as e:
            summarize_spy["raised"] = True
            summarize_spy["error_type"] = type(e).__name__
            raise

    monkeypatch.setattr(_compaction, "_run_summarization_core", spy_summarize_core)

    truncate_spy = {"calls": 0, "kept": 0, "dropped": 0}
    orig_truncate_fallback = _compaction._truncate_with_dropped

    def spy_truncate_fallback(*args, **kwargs):
        truncate_spy["calls"] += 1
        result, dropped = orig_truncate_fallback(*args, **kwargs)
        truncate_spy["kept"] = len(result)
        truncate_spy["dropped"] = len(dropped)
        return result, dropped

    monkeypatch.setattr(_compaction, "_truncate_with_dropped", spy_truncate_fallback)

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
    # 500k tokens — well over the 200k ctx window. The summarization payload
    # (history minus ~20k protected tail) will be ~480k → guaranteed reject.
    history = _build_huge_history(target_tokens=500_000)
    before_tokens = sum(estimate_tokens_for_message(m) for m in history)
    before_len = len(history)

    print(f"\n[pre-run]  history: {before_len} msgs, ~{before_tokens:,} tokens")
    assert before_tokens > 400_000, (
        f"Test setup bug: only built {before_tokens:,} tokens, need >400k to "
        "guarantee summarizer overflow."
    )

    glm51_agent.set_message_history(list(history))

    # -- Kick the run ---------------------------------------------------------
    result = await glm51_agent.run_with_mcp("hi")

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
        "_run_summarization_core was never called — compact() didnt route to "
        "summarization at all"
    )

    # CORE INVARIANT 2: summarization failed (raised)
    assert summarize_spy["raised"], (
        f"Summarization unexpectedly succeeded — the 500k payload should have "
        f"overflowed GLM-5.1's 200k ctx. Spy: {summarize_spy}"
    )
    print(
        f"[summarize] attempts={summarize_spy['calls']} "
        f"raised={summarize_spy['raised']} ({summarize_spy['error_type']})"
    )

    # CORE INVARIANT 3: truncation fallback executed
    assert truncate_spy["calls"] >= 1, (
        "_truncate_with_dropped was never called — fallback path didnt fire. "
        f"Spy: {truncate_spy}"
    )
    assert truncate_spy["dropped"] > 0, (
        f"Fallback truncation didnt drop anything: {truncate_spy}"
    )
    print(
        f"[truncate-fallback] calls={truncate_spy['calls']} "
        f"kept={truncate_spy['kept']} dropped={truncate_spy['dropped']}"
    )

    # CORE INVARIANT 4: history shrank dramatically
    after_history = glm51_agent.get_message_history()
    after_tokens = sum(estimate_tokens_for_message(m) for m in after_history)
    print(
        f"[post-run] history: {len(after_history)} msgs, ~{after_tokens:,} tokens "
        f"(reduced {(1 - after_tokens / before_tokens) * 100:.1f}%)"
    )
    assert after_tokens < before_tokens, (
        f"History token count did not drop: {before_tokens:,} → {after_tokens:,}"
    )
    # After truncation the history must fit inside GLM-5.1's window with room
    # to spare for the response. 200k * 0.95 = 190k headroom check.
    assert after_tokens < 190_000, (
        f"Truncated history ({after_tokens:,} tokens) still wouldnt fit in "
        "GLM-5.1's 200k ctx window — truncation didnt reduce enough."
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
