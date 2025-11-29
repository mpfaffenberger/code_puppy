from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, List

from pydantic_ai._run_context import RunContext
from pydantic_ai.models import (
    Model,
    ModelMessage,
    ModelRequestParameters,
    ModelResponse,
    ModelSettings,
    StreamedResponse,
)

try:
    from opentelemetry.context import get_current_span
except ImportError:
    # If opentelemetry is not installed, provide a dummy implementation
    def get_current_span():
        class DummySpan:
            def is_recording(self):
                return False

            def set_attributes(self, attributes):
                pass

        return DummySpan()


@dataclass(init=False)
class RoundRobinModel(Model):
    """A model that cycles through multiple models in a round-robin fashion.

    This model distributes requests across multiple candidate models to help
    overcome rate limits or distribute load.
    """

    models: List[Model]
    _current_index: int = field(default=0, repr=False)
    _model_name: str = field(repr=False)
    _rotate_every: int = field(default=1, repr=False)
    _request_count: int = field(default=0, repr=False)

    def __init__(
        self,
        *models: Model,
        rotate_every: int = 1,
        settings: ModelSettings | None = None,
    ):
        """Initialize a round-robin model instance.

        Args:
            models: The model instances to cycle through.
            rotate_every: Number of requests before rotating to the next model (default: 1).
            settings: Model settings that will be used as defaults for this model.
        """
        super().__init__(settings=settings)
        if not models:
            raise ValueError("At least one model must be provided")
        if rotate_every < 1:
            raise ValueError("rotate_every must be at least 1")
        self.models = list(models)
        self._current_index = 0
        self._request_count = 0
        self._rotate_every = rotate_every

    @property
    def model_name(self) -> str:
        """The model name showing this is a round-robin model with its candidates."""
        base_name = f"round_robin:{','.join(model.model_name for model in self.models)}"
        if self._rotate_every != 1:
            return f"{base_name}:rotate_every={self._rotate_every}"
        return base_name

    @property
    def system(self) -> str:
        """System prompt from the current model."""
        return self.models[self._current_index].system

    @property
    def base_url(self) -> str | None:
        """Base URL from the current model."""
        return self.models[self._current_index].base_url

    def _get_next_model(self) -> Model:
        """Get the next model in the round-robin sequence and update the index."""
        model = self.models[self._current_index]
        self._request_count += 1
        if self._request_count >= self._rotate_every:
            self._current_index = (self._current_index + 1) % len(self.models)
            self._request_count = 0
        return model

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request using the next model in the round-robin sequence."""
        current_model = self._get_next_model()
        # Use prepare_request to merge settings and customize parameters
        merged_settings, prepared_params = current_model.prepare_request(
            model_settings, model_request_parameters
        )

        try:
            response = await current_model.request(
                messages, merged_settings, prepared_params
            )
            self._set_span_attributes(current_model)
            return response
        except Exception as exc:
            # Unlike FallbackModel, we don't try other models here
            # The round-robin strategy is about distribution, not failover
            raise exc

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Make a streaming request using the next model in the round-robin sequence."""
        current_model = self._get_next_model()
        # Use prepare_request to merge settings and customize parameters
        merged_settings, prepared_params = current_model.prepare_request(
            model_settings, model_request_parameters
        )

        async with current_model.request_stream(
            messages, merged_settings, prepared_params, run_context
        ) as response:
            self._set_span_attributes(current_model)
            yield response

    def _set_span_attributes(self, model: Model):
        """Set span attributes for observability."""
        with suppress(Exception):
            span = get_current_span()
            if span.is_recording():
                attributes = getattr(span, "attributes", {})
                if attributes.get("gen_ai.request.model") == self.model_name:
                    span.set_attributes(model.model_attributes(model))
