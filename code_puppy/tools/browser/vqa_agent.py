"""Utilities for running visual question-answering via pydantic-ai."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, PartDeltaEvent, PartStartEvent, RunContext
from pydantic_ai.messages import TextPart, TextPartDelta

from code_puppy.config import get_use_dbos, get_vqa_model_name


class VisualAnalysisResult(BaseModel):
    """Structured response from the VQA agent."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    observations: str


DEFAULT_VQA_INSTRUCTIONS = (
    "You are a visual analysis specialist. Answer the user's question about the provided image. "
    "Always respond using the structured schema: answer, confidence (0-1 float), observations. "
    "Confidence reflects how certain you are about the answer. Observations should include useful, concise context."
)


async def run_vqa_analysis(
    question: str,
    image_bytes: bytes,
    media_type: str = "image/png",
) -> str:
    """Execute the VQA agent asynchronously against screenshot bytes.

    Follows the same pattern as agent_tools.py for prompt preparation
    and model configuration.

    Args:
        question: The question to ask about the image.
        image_bytes: The raw image bytes.
        media_type: The MIME type of the image (default: "image/png").
        system_prompt: Optional custom system prompt. If None, uses default VQA instructions.

    Returns:
        str: The answer from the VQA analysis.
    """
    from code_puppy import callbacks
    from code_puppy.model_factory import ModelFactory
    from code_puppy.model_utils import prepare_prompt_for_model

    # Get model configuration
    model_name = get_vqa_model_name()
    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    # Build instructions: custom system_prompt or default VQA instructions
    instructions = DEFAULT_VQA_INSTRUCTIONS

    # Apply prompt additions (like file permission handling) - same as agent_tools.py
    prompt_additions = callbacks.on_load_prompt()
    if prompt_additions:
        instructions += "\n" + "\n".join(prompt_additions)

    # Handle claude-code models: swap instructions, prepend system prompt to user question
    # Following the exact pattern from agent_tools.py
    prepared = prepare_prompt_for_model(
        model_name, instructions, question, prepend_system_to_user=True
    )
    instructions = prepared.instructions
    question = prepared.user_prompt

    # Create the VQA agent with string output
    vqa_agent = Agent(
        model=model,
        instructions=instructions,
    )

    # Wrap with DBOS if enabled
    if get_use_dbos():
        from pydantic_ai.durable_exec.dbos import DBOSAgent

        vqa_agent = DBOSAgent(vqa_agent, name="vqa-agent")

    # Run the agent with the image
    result = await vqa_agent.run(
        [
            question,
            BinaryContent(data=image_bytes, media_type=media_type),
        ]
    )
    return result.output


def _create_vqa_stream_handler(
    accumulator: list[str],
):
    """Create an event stream handler that accumulates text.

    Args:
        accumulator: List to accumulate text chunks into (pass empty list).

    Returns:
        Async event stream handler function.
    """

    async def vqa_event_stream_handler(
        ctx: RunContext,
        events: AsyncIterable[Any],
    ) -> None:
        """Handle streaming events - print text as it arrives."""
        async for event in events:
            # Handle text part start - might have initial content
            if isinstance(event, PartStartEvent):
                if isinstance(event.part, TextPart) and event.part.content:
                    accumulator.append(event.part.content)

            # Handle text deltas - the streaming bits
            elif isinstance(event, PartDeltaEvent):
                if isinstance(event.delta, TextPartDelta) and event.delta.content_delta:
                    accumulator.append(event.delta.content_delta)

    return vqa_event_stream_handler


async def run_vqa_analysis_stream(
    question: str,
    image_bytes: bytes,
    media_type: str = "image/png",
) -> str:
    """Execute the VQA agent with streaming output.

    Streams text to console as it arrives and accumulates the full response.

    Args:
        question: The question to ask about the image.
        image_bytes: The raw image bytes.
        media_type: The MIME type of the image (default: "image/png").

    Returns:
        str: The accumulated answer from the VQA analysis.
    """
    from code_puppy import callbacks
    from code_puppy.model_factory import ModelFactory
    from code_puppy.model_utils import prepare_prompt_for_model

    # Get model configuration
    model_name = get_vqa_model_name()
    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    # Build instructions
    instructions = DEFAULT_VQA_INSTRUCTIONS

    # Apply prompt additions (like file permission handling)
    prompt_additions = callbacks.on_load_prompt()
    if prompt_additions:
        instructions += "\n" + "\n".join(prompt_additions)

    # Handle claude-code models: swap instructions, prepend system prompt to user question
    prepared = prepare_prompt_for_model(
        model_name, instructions, question, prepend_system_to_user=True
    )
    instructions = prepared.instructions
    question = prepared.user_prompt

    # Create the VQA agent
    vqa_agent = Agent(
        model=model,
        instructions=instructions,
    )

    # Wrap with DBOS if enabled
    if get_use_dbos():
        from pydantic_ai.durable_exec.dbos import DBOSAgent

        vqa_agent = DBOSAgent(vqa_agent, name="vqa-agent-stream")

    # Accumulator for streamed text (use list to allow mutation in handler)
    accumulated_chunks: list[str] = []

    # Create the stream handler
    stream_handler = _create_vqa_stream_handler(accumulated_chunks)

    # Run the agent with event_stream_handler
    result = await vqa_agent.run(
        [
            question,
            BinaryContent(data=image_bytes, media_type=media_type),
        ],
        event_stream_handler=stream_handler,
    )
    return result.output
