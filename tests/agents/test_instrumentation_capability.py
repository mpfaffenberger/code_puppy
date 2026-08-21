"""Contract tests for the explicit ``Instrumentation`` capability delivery.

Logfire tracing used to reach code_puppy's agents only through the
process-global ``Agent.instrument_all`` default installed by
``logfire.instrument_pydantic_ai()``. ``code_puppy/agents/_instrumentation.py``
promotes that to an explicit ``Instrumentation`` capability on the agents
code_puppy builds, carrying the *same* settings object. These tests pin:

* the builder contract (empty when uninstrumented, verbatim settings when
  instrumented, ``True`` normalisation);
* the private-attribute seam (``Agent._instrument_default``) so a pydantic-ai
  rename fails loudly here instead of silently degrading;
* span parity between the old (global-only) and new (explicit-capability)
  delivery, including the no-double-instrumentation guarantee;
* both real construction paths (main builder + sub-agent invoker);
* the documented build-time-snapshot divergence.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.capabilities import Instrumentation

# Private helper, but it is exactly what pydantic-ai's run layer uses for its
# explicit-capability-wins check -- introspecting with the same traversal
# keeps these assertions honest.
from pydantic_ai.capabilities._ordering import collect_leaves
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.test import TestModel

from code_puppy.agents._instrumentation import build_instrumentation


@pytest.fixture(autouse=True)
def _restore_global_instrument_default():
    """Never leak instrumentation state into the rest of the suite."""
    original = PydanticAgent._instrument_default
    yield
    PydanticAgent.instrument_all(original)


def _memory_settings():
    """InstrumentationSettings wired to an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return InstrumentationSettings(tracer_provider=provider), exporter


def _instrumentation_leaves(agent):
    return [
        leaf
        for leaf in collect_leaves(agent.root_capability)
        if isinstance(leaf, Instrumentation)
    ]


# ---------------------------------------------------------------------------
# build_instrumentation contract
# ---------------------------------------------------------------------------


def test_uninstrumented_process_builds_no_capability():
    PydanticAgent.instrument_all(False)
    assert build_instrumentation() == []


def test_instrument_all_settings_delivered_verbatim():
    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)
    (cap,) = build_instrumentation()
    assert isinstance(cap, Instrumentation)
    # Identity, not equality: the capability must deliver the exact object
    # logfire installed, or provider wiring could silently drift.
    assert cap.settings is settings


def test_instrument_all_true_normalizes_to_default_settings():
    PydanticAgent.instrument_all(True)
    (cap,) = build_instrumentation()
    assert isinstance(cap.settings, InstrumentationSettings)


def test_each_call_builds_a_fresh_capability():
    """Probe and final construction passes must not share per-run state."""
    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)
    (first,) = build_instrumentation()
    (second,) = build_instrumentation()
    assert first is not second


# ---------------------------------------------------------------------------
# pydantic-ai seam pins
# ---------------------------------------------------------------------------


def test_private_default_attribute_is_pinned():
    """``_instrument_default`` is the only source of logfire's exact settings.

    If a pydantic-ai bump renames it, ``build_instrumentation`` degrades to
    "no explicit capability" (covered by the run-layer fallback) -- this test
    makes that bump loud instead of silent.
    """
    assert hasattr(PydanticAgent, "_instrument_default")
    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)
    assert PydanticAgent._instrument_default is settings


def test_capability_orders_itself_outermost():
    """List position in ``capabilities=[...]`` is inert -- pinned here."""
    (ordering,) = [Instrumentation().get_ordering()]
    assert ordering.position == "outermost"


# ---------------------------------------------------------------------------
# span parity: old global-only path vs explicit capability path
# ---------------------------------------------------------------------------


def _text_model():
    def reply(_messages, _info):
        return ModelResponse(parts=[TextPart("woof")])

    return FunctionModel(reply)


@pytest.mark.asyncio
async def test_explicit_capability_matches_global_default_spans():
    """Same settings, same spans -- whether delivered globally or explicitly."""
    settings_a, exporter_a = _memory_settings()
    PydanticAgent.instrument_all(settings_a)
    old_path = PydanticAgent(model=_text_model(), name="parity-agent")
    await old_path.run("hello")
    old_spans = [
        (s.name, dict(s.attributes or {}).get("gen_ai.operation.name"))
        for s in exporter_a.get_finished_spans()
    ]

    settings_b, exporter_b = _memory_settings()
    PydanticAgent.instrument_all(settings_b)
    new_path = PydanticAgent(
        model=_text_model(),
        name="parity-agent",
        capabilities=[Instrumentation(settings=settings_b)],
    )
    await new_path.run("hello")
    new_spans = [
        (s.name, dict(s.attributes or {}).get("gen_ai.operation.name"))
        for s in exporter_b.get_finished_spans()
    ]

    assert old_spans == new_spans


@pytest.mark.asyncio
async def test_no_double_instrumentation_with_global_default_set():
    """Explicit capability + live global default must not duplicate spans."""
    settings, exporter = _memory_settings()
    PydanticAgent.instrument_all(settings)
    agent = PydanticAgent(
        model=_text_model(),
        name="dedupe-agent",
        capabilities=[Instrumentation(settings=settings)],
    )
    await agent.run("hello")
    run_spans = [
        s
        for s in exporter.get_finished_spans()
        if dict(s.attributes or {}).get("gen_ai.operation.name") == "invoke_agent"
    ]
    assert len(run_spans) == 1


# ---------------------------------------------------------------------------
# real construction paths
# ---------------------------------------------------------------------------


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config for driving the real build paths."""

    name = "code-puppy"
    display_name = "Code Puppy"

    def __init__(self):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None

    @contextmanager
    def temporary_model_name_override(self, _model_name):
        yield

    def get_model_name(self):
        return "test-model"

    def get_full_system_prompt(self):
        return "You are a test agent."

    def get_available_tools(self):
        return []

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: 0


def _fake_load_model_with_fallback(*_args, **_kwargs):
    return TestModel(custom_output_text="woof"), "test-model"


@contextmanager
def _builder_patches():
    from code_puppy.agents import _builder

    with (
        patch.object(
            _builder, "load_model_with_fallback", _fake_load_model_with_fallback
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        yield _builder


def test_main_builder_declares_capability_when_instrumented():
    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)
    with _builder_patches() as _builder:
        built = _builder.build_pydantic_agent(_FakeAgentConfig())
    (leaf,) = _instrumentation_leaves(built)
    assert leaf.settings is settings


def test_main_builder_omits_capability_when_uninstrumented():
    PydanticAgent.instrument_all(False)
    with _builder_patches() as _builder:
        built = _builder.build_pydantic_agent(_FakeAgentConfig())
    assert _instrumentation_leaves(built) == []


@pytest.mark.asyncio
async def test_subagent_path_declares_capability_when_instrumented():
    from code_puppy.tools import subagent_invocation as si

    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)

    cfg = _FakeAgentConfig()
    cfg.name = "web-retriever"
    captured = {}

    def capture_wrap(_agent_config, pydantic_agent, **_kwargs):
        captured["agent"] = pydantic_agent
        return pydantic_agent

    with (
        patch("code_puppy.agents.agent_manager.load_agent", return_value=cfg),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            _fake_load_model_with_fallback,
        ),
        patch("code_puppy.model_factory.make_model_settings", lambda *a, **k: None),
        patch("code_puppy.config.get_value", return_value="true"),  # no MCP
        patch.object(si, "on_wrap_pydantic_agent", capture_wrap),
    ):
        out = await si._invoke_agent_impl(
            context=SimpleNamespace(),
            agent_name="web-retriever",
            prompt="fetch me a stick",
        )

    assert out.error is None
    (leaf,) = _instrumentation_leaves(captured["agent"])
    assert leaf.settings is settings


# ---------------------------------------------------------------------------
# documented divergence: build-time snapshot
# ---------------------------------------------------------------------------


def test_snapshot_survives_later_global_disable():
    """Divergence pin (see _instrumentation.py docstring): an agent built
    while instrumented keeps its capability even if the global default is
    later cleared. Nothing in code_puppy flips the default after startup."""
    settings, _ = _memory_settings()
    PydanticAgent.instrument_all(settings)
    with _builder_patches() as _builder:
        built = _builder.build_pydantic_agent(_FakeAgentConfig())
    PydanticAgent.instrument_all(False)
    assert len(_instrumentation_leaves(built)) == 1
