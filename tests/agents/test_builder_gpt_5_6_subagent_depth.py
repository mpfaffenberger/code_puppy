"""Tests for the GPT-5.6 max sub-agent recursion depth guard.

Covers ``_gpt_5_6_subagent_depth_should_block`` and the integration in
``_invoke_agent_impl``. The rule: GPT-5.6 family models cap sub-agent
recursion at depth 1 - the first level (depth 0 -> 1) is allowed, but
any further delegation (depth 1 -> 2) is blocked.

Tests use ``subagent_context`` from ``code_puppy.tools.subagent_context``
to manipulate the running depth without spinning up real agents.
"""

from __future__ import annotations

import pytest

from code_puppy.agents import _builder
from code_puppy.tools.subagent_context import subagent_context


class TestGpt56SubagentDepthShouldBlock:
    """The depth classifier: only blocks when model is GPT-5.6 AND depth >= 1."""

    def test_returns_false_at_depth_zero(self):
        # Depth 0 (main agent) with a GPT-5.6 model - the first sub-agent
        # is allowed, so we should NOT block.
        assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.6-sol") is False
        assert (
            _builder._gpt_5_6_subagent_depth_should_block("codex-gpt-5.6-sol") is False
        )

    def test_returns_true_for_gpt_5_6_at_depth_one(self):
        with subagent_context("first-sub-agent"):
            assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.6-sol") is True

    def test_returns_true_for_gpt_5_6_at_depth_two(self):
        with subagent_context("first-sub-agent"):
            with subagent_context("second-sub-agent"):
                assert (
                    _builder._gpt_5_6_subagent_depth_should_block("codex-gpt-5.6-luna")
                    is True
                )

    def test_returns_false_for_non_gpt_5_6_at_depth_one(self):
        with subagent_context("first-sub-agent"):
            assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.5") is False
            assert (
                _builder._gpt_5_6_subagent_depth_should_block("claude-sonnet-4-5")
                is False
            )

    def test_returns_false_for_non_gpt_5_6_at_depth_two(self):
        with subagent_context("first-sub-agent"):
            with subagent_context("second-sub-agent"):
                assert (
                    _builder._gpt_5_6_subagent_depth_should_block("claude-opus-4-7")
                    is False
                )

    @pytest.mark.parametrize("model_name", ["", None, 0])
    def test_returns_false_for_empty_or_none_model(self, model_name):
        assert _builder._gpt_5_6_subagent_depth_should_block(model_name) is False

    def test_returns_false_for_unrelated_gpt_5_family(self):
        with subagent_context("first-sub-agent"):
            assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.5") is False
            assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5") is False
            assert (
                _builder._gpt_5_6_subagent_depth_should_block("gpt-5.4-mini") is False
            )


class TestHelperMirrorsCallSiteSemantics:
    """Sanity-check that the helper matches the inline call-site logic.

    The integration in ``_invoke_agent_impl`` is effectively:

        if model is GPT-5.6 and get_subagent_depth() >= 1: block

    These tests verify the helper returns ``True`` only when both
    conditions hold simultaneously.
    """

    def test_helper_false_at_depth_zero_even_for_gpt_5_6(self):
        # At depth 0, we always allow the first sub-agent invocation.
        assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.6-sol") is False

    def test_helper_true_for_gpt_5_6_only_after_first_level(self):
        with subagent_context("parent"):
            # Inside subagent_context we're at depth >= 1.
            assert _builder._gpt_5_6_subagent_depth_should_block("gpt-5.6-sol") is True

    def test_helper_false_for_non_gpt_5_6_at_depth_one(self):
        with subagent_context("parent"):
            assert (
                _builder._gpt_5_6_subagent_depth_should_block("claude-sonnet-4-5")
                is False
            )
            assert (
                _builder._gpt_5_6_subagent_depth_should_block("gpt-5.5-mini") is False
            )
