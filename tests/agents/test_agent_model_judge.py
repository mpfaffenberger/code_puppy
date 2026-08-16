"""Tests for the builtin Model Judge agent."""

from code_puppy.agents.agent_model_judge import ModelJudgeAgent
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.tools import TOOL_REGISTRY


class TestAgentContract:
    """The agent must satisfy what discovery and the runtime expect."""

    def test_is_a_base_agent(self):
        assert issubclass(ModelJudgeAgent, BaseAgent)

    def test_instantiates_with_no_arguments(self):
        """Discovery calls ``attr()`` with no args to read ``.name``."""
        assert ModelJudgeAgent().name == "model-judge"

    def test_identity_fields_are_populated(self):
        agent = ModelJudgeAgent()

        assert agent.display_name.strip()
        assert agent.description.strip()
        assert agent.get_user_prompt().strip()

    def test_every_tool_exists_in_the_registry(self):
        """A typo here would silently drop a tool at runtime."""
        unknown = [
            tool
            for tool in ModelJudgeAgent().get_available_tools()
            if tool not in TOOL_REGISTRY
        ]

        assert unknown == []

    def test_can_invoke_models_and_discover_them(self):
        """Benchmarking is impossible without these two."""
        tools = ModelJudgeAgent().get_available_tools()

        assert "invoke_agent_with_model" in tools
        assert "list_available_models" in tools


class TestSystemPrompt:
    """The persona carries the cost-reporting rules; they must survive."""

    def test_documents_the_billable_buckets(self):
        prompt = ModelJudgeAgent().get_system_prompt()

        for bucket in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "output_tokens",
        ):
            assert bucket in prompt

    def test_forbids_inventing_a_blended_total(self):
        """Buckets are priced differently, so a sum cannot become a cost."""
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "NO `total_tokens`" in prompt

    def test_explains_cache_write_estimation_for_openai(self):
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "Estimating cache writes" in prompt
        # The delta form, NOT the raw next-call read.
        assert "cache_read(call i+1) - cache_read(call i)" in prompt

    def test_requires_estimates_be_labelled_as_such(self):
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "Label it an ESTIMATE" in prompt
        assert "never fabricate" in prompt.lower()


class TestCacheWriteEstimation:
    """Pins the arithmetic the prompt tells the agent to use.

    Reads are CUMULATIVE, so a write is the DIFFERENCE between consecutive
    reads. Using the next call's raw read re-counts the prefix every time.
    """

    @staticmethod
    def _estimate(reads):
        return [reads[i + 1] - reads[i] for i in range(len(reads) - 1)]

    @staticmethod
    def _formula_from_prompt():
        """Pull the formula line out of the shipped prompt.

        Reading it back means the tests below cannot drift away from what the
        agent is actually told to do.
        """
        for line in ModelJudgeAgent().get_system_prompt().splitlines():
            if line.strip().startswith("estimated_write(call i)"):
                return line.strip()
        raise AssertionError("cache-write formula missing from the prompt")

    def test_prompt_specifies_the_delta_form(self):
        """The formula must be the difference, not the next raw read."""
        formula = self._formula_from_prompt()

        assert formula == (
            "estimated_write(call i) = cache_read(call i+1) - cache_read(call i)"
        )

    def test_delta_recovers_the_true_writes(self):
        true_writes = [1000, 300, 250]
        reads = [0, 1000, 1300, 1550]

        assert self._estimate(reads) == true_writes

    def test_raw_next_read_overstates_writes(self):
        """The tempting-but-wrong version, kept as a counter-example."""
        reads = [0, 1000, 1300, 1550]

        naive = reads[1:]

        assert naive == [1000, 1300, 1550]
        assert naive != self._estimate(reads)

    def test_first_call_estimate_equals_the_second_calls_read(self):
        """With no prior cache, the delta collapses to the next read."""
        reads = [0, 1000, 1300]

        assert self._estimate(reads)[0] == reads[1]


class TestPromptMatchesTheSchema:
    """Every metric the prompt names must exist on the tool's output.

    The persona already fell behind the schema once. Telling the judge to read
    a missing field produces confident nonsense.
    """

    def test_every_metric_field_is_documented(self):
        from code_puppy.tools.agent_tools import AgentInvokeWithModelOutput

        metrics = {
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "output_tokens",
            "num_requests",
            "per_request_usage",
            "final_context_tokens",
        }
        # Guard the guard: these must really be on the model.
        assert metrics <= set(AgentInvokeWithModelOutput.model_fields)

        prompt = ModelJudgeAgent().get_system_prompt()
        undocumented = sorted(f for f in metrics if f not in prompt)

        assert undocumented == []

    def test_prompt_does_not_reference_removed_fields(self):
        """``total_tokens`` was removed; the prompt must not resurrect it."""
        prompt = ModelJudgeAgent().get_system_prompt()

        # Mentioned only to forbid inventing one.
        assert "NO `total_tokens`" in prompt


class TestCacheWritePricingClaim:
    """OpenAI and Gemini do not charge for cache writes.

    genai-prices lists ``cache_write_mtok`` for 0 of 71 OpenAI models, and every
    Google entry with one is Claude-on-Vertex, not a gemini-*. Pricing an
    estimated write there invents a cost and biases the verdict.
    """

    def test_prompt_says_writes_are_free_there(self):
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "writes are free" in prompt
        assert "NEVER price it for OpenAI or Gemini" in prompt

    def test_prompt_does_not_claim_they_charge_a_premium(self):
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "charges a premium rate for cache writes" not in prompt

    def test_anthropic_is_still_described_as_billable(self):
        """The asymmetry is the point -- don't over-correct into the reverse."""
        prompt = ModelJudgeAgent().get_system_prompt()

        assert "Anthropic bills for cache writes" in prompt
