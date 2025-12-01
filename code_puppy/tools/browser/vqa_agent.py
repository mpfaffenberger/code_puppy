"""Utilities for running visual question-answering via pydantic-ai."""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

from code_puppy.config import get_use_dbos, get_vqa_model_name
from code_puppy.model_factory import ModelFactory


class VisualAnalysisResult(BaseModel):
    """Structured response from the VQA agent."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    observations: str


def _get_vqa_instructions() -> str:
    """Get the system instructions for the VQA agent."""
    return (
        "You are a visual analysis specialist. Answer the user's question about the provided image. "
        "Always respond using the structured schema: answer, confidence (0-1 float), observations. "
        "Confidence reflects how certain you are about the answer. Observations should include useful, concise context."
    )


@lru_cache(maxsize=1)
def _load_vqa_agent(model_name: str) -> Agent[None, VisualAnalysisResult]:
    """Create a cached agent instance for visual analysis."""
    from code_puppy.model_utils import prepare_prompt_for_model

    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    # Handle claude-code models: swap instructions (prompt prepending happens in run_vqa_analysis)
    instructions = _get_vqa_instructions()
    prepared = prepare_prompt_for_model(
        model_name, instructions, "", prepend_system_to_user=False
    )
    instructions = prepared.instructions

    vqa_agent = Agent(
        model=model,
        instructions=instructions,
        output_type=VisualAnalysisResult,
        retries=2,
    )

    if get_use_dbos():
        from pydantic_ai.durable_exec.dbos import DBOSAgent

        dbos_agent = DBOSAgent(vqa_agent, name="vqa-agent")
        return dbos_agent

    return vqa_agent


def _get_vqa_agent() -> Agent[None, VisualAnalysisResult]:
    """Return a cached VQA agent configured with the current model."""
    model_name = get_vqa_model_name()
    # lru_cache keyed by model_name ensures refresh when configuration changes
    return _load_vqa_agent(model_name)


def run_vqa_analysis(
    question: str,
    image_bytes: bytes,
    media_type: str = "image/png",
) -> VisualAnalysisResult:
    """Execute the VQA agent synchronously against screenshot bytes."""
    from code_puppy.model_utils import prepare_prompt_for_model

    agent = _get_vqa_agent()

    # Handle claude-code models: prepend system prompt to user question
    model_name = get_vqa_model_name()
    prepared = prepare_prompt_for_model(model_name, _get_vqa_instructions(), question)
    question = prepared.user_prompt

    result = agent.run_sync(
        [
            question,
            BinaryContent(data=image_bytes, media_type=media_type),
        ]
    )
    return result.output
