"""Visual question-answering for desktop screenshots."""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

from code_puppy.model_factory import ModelFactory


class DesktopVisualAnalysisResult(BaseModel):
    """Structured response from the desktop VQA agent."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    observations: str


@lru_cache(maxsize=1)
def _load_desktop_vqa_agent(
    model_name: str,
) -> Agent[None, DesktopVisualAnalysisResult]:
    """Create a cached agent instance for desktop visual analysis."""
    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    instructions = (
        "You are a desktop visual analysis specialist for desktop automation. "
        "Answer the user's question about the provided desktop screenshot. "
        "Always respond using the structured schema: answer, confidence (0-1 float), observations. "
        "Confidence reflects how certain you are about the answer. "
        "Observations should include useful, concise context about UI elements, windows, buttons, or any relevant desktop features. "
        "Important: If the screenshot includes multiple windows or any content not matching the requested window context, "
        "explicitly prefer the targeted window (by title if provided). If the requested element is not visible in the targeted window, "
        "respond with 'Not found' and explain briefly why (e.g., wrong window, full-screen mode, region too small). "
        "Never infer click coordinates—only describe locations relative to the image or grid labels if present. "
        "Be precise and actionable to guide automation tasks."
    )

    return Agent(
        model=model,
        instructions=instructions,
        output_type=DesktopVisualAnalysisResult,
        retries=2,
    )


def _get_model_for_vqa() -> str:
    """Determine which model to use for VQA.

    Priority:
    1. GUI-Cub VQA model override (if configured)
    2. Current global model (user's selection)
    3. Default vision-capable model from models.json
    """
    from code_puppy.tools.gui_cub.config_manager import get_vqa_model_name

    # Use GUI-Cub's VQA config (handles fallback internally)
    return get_vqa_model_name()


def _get_desktop_vqa_agent() -> Agent[None, DesktopVisualAnalysisResult]:
    """Return a cached desktop VQA agent configured with the current model."""
    model_name = _get_model_for_vqa()
    # lru_cache keyed by model_name ensures refresh when configuration changes
    return _load_desktop_vqa_agent(model_name)


def run_desktop_vqa_analysis(
    question: str,
    image_bytes: bytes,
    media_type: str = "image/png",
) -> DesktopVisualAnalysisResult:
    """Execute the desktop VQA agent synchronously against screenshot bytes."""
    from code_puppy.messaging import emit_warning
    from .rich_emit import emit_rich

    # Use internal model selection logic (prefers current global model)
    model_name = _get_model_for_vqa()
    image_size_mb = len(image_bytes) / 1_000_000

    emit_rich(
        f"[bold cyan]🤖 VQA REQUEST[/bold cyan]\n"
        f"[dim]   Model: {model_name}[/dim]\n"
        f"[dim]   Image size: {image_size_mb:.2f} MB[/dim]\n"
        f"[dim]   Media type: {media_type}[/dim]\n"
        f"[dim]   Question: {question[:100]}{'...' if len(question) > 100 else ''}[/dim]"
    )

    agent = _get_desktop_vqa_agent()

    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        # Check if we're already in an event loop
        try:
            asyncio.get_running_loop()

            # We're in an async context - run in a separate thread with fresh event loop
            # This completely isolates the sync call from the parent event loop
            def _run_vqa_in_new_loop():
                # Create a completely fresh event loop in this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return agent.run_sync(
                        [
                            question,
                            BinaryContent(data=image_bytes, media_type=media_type),
                        ]
                    )
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(None)

            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_run_vqa_in_new_loop).result()
        except RuntimeError:
            # No running loop, safe to use run_sync directly
            result = agent.run_sync(
                [
                    question,
                    BinaryContent(data=image_bytes, media_type=media_type),
                ]
            )

        emit_rich(
            f"[bold green]✅ VQA RESPONSE[/bold green]\n"
            f"[dim]   Answer: {result.output.answer[:150]}{'...' if len(result.output.answer) > 150 else ''}[/dim]\n"
            f"[dim]   Confidence: {result.output.confidence:.2%}[/dim]\n"
            f"[dim]   Observations: {result.output.observations[:100]}{'...' if len(result.output.observations) > 100 else ''}[/dim]"
        )

        return result.output

    except Exception as e:
        emit_warning(
            f"[red]❌ VQA FAILED[/red]\n"
            f"[dim]   Error: {str(e)[:200]}[/dim]\n"
            f"[dim]   Question was: {question[:100]}[/dim]"
        )
        raise
