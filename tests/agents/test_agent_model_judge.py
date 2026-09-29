from code_puppy.agents.agent_model_judge import ModelJudgeAgent
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.tools import TOOL_REGISTRY


class TestAgentContract:
    def test_is_a_base_agent(self):
        assert issubclass(ModelJudgeAgent, BaseAgent)

    def test_instantiates_with_no_arguments(self):
        assert ModelJudgeAgent().name == "model-judge"

    def test_identity_fields_are_populated(self):
        agent = ModelJudgeAgent()

        assert agent.display_name.strip()
        assert agent.description.strip()
        assert agent.get_user_prompt().strip()

    def test_every_tool_exists_in_the_registry(self):
        unknown = [
            tool
            for tool in ModelJudgeAgent().get_available_tools()
            if tool not in TOOL_REGISTRY
        ]

        assert unknown == []

    def test_can_invoke_models_and_discover_them(self):
        tools = ModelJudgeAgent().get_available_tools()

        assert "invoke_agent_with_model" in tools
        assert "list_available_models" in tools
