"""Prompt-cache contracts for sub-agent instruction assembly.

Scope, stated precisely:

* A sub-agent is re-instantiated on every ``invoke_agent`` call (``load_agent``
  mints a fresh ``BaseAgent.id`` -> a fresh identity UUID). The old code baked
  that UUID (and the depth/chain nesting text) into the single *static*
  ``instructions`` block, which is exactly the block pydantic-ai marks with the
  Anthropic ``cache_control`` breakpoint. So two constructions of the *same*
  sub-agent produced different cacheable prefixes and could not reuse one
  another's cache.

* ``build_subagent_instructions`` keeps the stable prompt as a static literal
  and returns the volatile identity/nesting as a *dynamic* instruction, which
  the Anthropic mapper orders after the breakpoint.

What this does NOT claim: it does not make one agent's cached prefix reusable by
a *different* agent (different system prompt and/or tools). A first sub-agent
whose parent is a different agent still cold-writes its own prefix; that write is
expected and correct. ``test_distinct_agents_*`` and
``test_parent_vs_first_child_*`` lock that in.

All tests are offline and metadata-only: no prompt text is logged, no
credentials, no network.
"""

from __future__ import annotations

import asyncio

from pydantic_ai.messages import InstructionPart, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings

from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.agents.agent_planning import PlanningAgent
from code_puppy.tools.subagent_invocation import build_subagent_instructions

MODEL = "plain-model"  # no claude-code splitting; static literal == stable prompt


def _assemble(agent, agent_name):
    """Return (static_literal, volatile_text) as build_subagent_instructions does."""
    _, instruction_items = build_subagent_instructions(
        agent,
        agent_name,
        MODEL,
        user_prompt="do the thing",
        is_new_session=True,
    )
    static_literal, volatile_callable = instruction_items
    assert isinstance(static_literal, str)
    assert callable(volatile_callable)
    return static_literal, volatile_callable()


def test_repeated_constructions_of_same_subagent_share_static_prefix():
    """Two sequential constructions of the SAME sub-agent produce an identical
    cacheable static prefix, even though each instance has a distinct UUID."""
    agent_a = PlanningAgent()
    agent_b = PlanningAgent()
    assert agent_a.id != agent_b.id  # distinct instances -> distinct identity UUIDs

    static_a, _ = _assemble(agent_a, "planning-agent")
    static_b, _ = _assemble(agent_b, "planning-agent")

    assert static_a == static_b


def test_identity_and_nesting_delivered_dynamically_not_in_static_prefix():
    """UUID + depth/chain are still delivered (in the dynamic instruction), but
    never appear in the cacheable static prefix."""
    agent = PlanningAgent()
    static_literal, volatile_text = _assemble(agent, "planning-agent")

    # Identity UUID: present in the volatile suffix, absent from the prefix.
    assert agent.get_identity() in volatile_text
    assert agent.get_identity() not in static_literal
    # Nesting context (depth + invocation chain) is per-invocation too.
    assert "nesting depth" in volatile_text
    assert "Invocation chain:" in volatile_text
    assert "nesting depth" not in static_literal
    assert "Invocation chain:" not in static_literal


def _cached_system_blocks(parts):
    """Run the real pydantic-ai Anthropic mapper offline; return cached blocks."""

    async def _run():
        model = AnthropicModel("claude-sonnet-4-5")
        mrp = ModelRequestParameters()
        mrp.instruction_parts = parts
        messages = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        settings = AnthropicModelSettings(anthropic_cache_instructions="1h")
        system_prompt, _ = await model._map_message(messages, mrp, settings)
        blocks = system_prompt if isinstance(system_prompt, list) else []
        return [dict(b) for b in blocks if dict(b).get("cache_control")]

    return asyncio.run(_run())


def test_cache_breakpoint_covers_stable_prefix_and_excludes_volatile_suffix():
    """End-to-end through the Anthropic mapper: with the fix's static+dynamic
    parts, the 1h cache_control lands on the stable prefix and no cached block
    contains the volatile identity."""
    agent = PlanningAgent()
    static_literal, volatile_text = _assemble(agent, "planning-agent")

    # Mirror how pydantic-ai classifies Agent(instructions=[literal, callable]):
    # literals -> static (dynamic=False), callables -> dynamic (dynamic=True).
    cached = _cached_system_blocks(
        [
            InstructionPart(content=static_literal, dynamic=False),
            InstructionPart(content=volatile_text, dynamic=True),
        ]
    )
    assert cached, "expected at least one cached system block"
    for block in cached:
        assert agent.get_identity() not in block.get("text", "")
    assert cached[-1]["text"] == static_literal
    assert cached[-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_prefixed_old_style_single_block_would_cache_the_volatile_identity():
    """Guard: the pre-fix shape (identity inside one static block) puts the UUID
    inside the cached block. Proves the fix targets a real divergence and that
    the assertions above are not vacuous."""
    agent = PlanningAgent()
    # Reconstruct the exact pre-fix assembly: full prompt + nesting, one block.
    from code_puppy.tools.subagent_invocation import _subagent_identity_prompt

    old_single = (
        agent.get_full_system_prompt()
        + f"\n\n{_subagent_identity_prompt('planning-agent')}"
    )
    cached = _cached_system_blocks([InstructionPart(content=old_single, dynamic=False)])
    assert cached and agent.get_identity() in cached[-1]["text"]


def test_distinct_agents_keep_distinct_cacheable_prefixes():
    """Isolation: genuinely different agents (different system prompt AND tools)
    are NOT falsely made cache-compatible."""
    planning = PlanningAgent()
    main = CodePuppyAgent()

    planning_static, _ = _assemble(planning, "planning-agent")
    main_static, _ = _assemble(main, "code-puppy")

    assert planning_static != main_static
    assert set(planning.get_available_tools()) != set(main.get_available_tools())


def test_parent_vs_first_child_prefixes_differ_so_first_cold_write_is_expected():
    """Parent (main ``code-puppy``) vs. its first ``planning`` child: their
    cacheable system prefixes and tool sets differ, so the child's first request
    cannot reuse the parent cache. That cold write is expected and correct; the
    fix does not (and must not) change it. The fix only lets *repeated planning
    children* share a prefix (see the first test)."""
    parent = CodePuppyAgent()
    child = PlanningAgent()

    parent_static, _ = _assemble(parent, "code-puppy")
    child_static, _ = _assemble(child, "planning-agent")

    # Different system component -> different cacheable prefix.
    assert parent_static != child_static
    # Different tool component -> different tool-definitions cache segment.
    assert set(parent.get_available_tools()) != set(child.get_available_tools())


def test_full_system_prompt_is_stable_prefix_plus_identity():
    """Refactor safety: ``get_full_system_prompt`` output is unchanged \u2014 exactly
    ``get_stable_system_prompt`` followed by ``get_identity_prompt``."""
    agent = PlanningAgent()
    assert (
        agent.get_full_system_prompt()
        == agent.get_stable_system_prompt() + agent.get_identity_prompt()
    )
