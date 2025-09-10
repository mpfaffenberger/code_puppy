from dataclasses import dataclass, field
from typing import Any, Callable, AsyncIterator, List
from contextlib import asynccontextmanager, suppress
from pydantic_ai.models import Model, ModelMessage, ModelSettings, ModelRequestParameters, ModelResponse, StreamedResponse
from pydantic_ai.models.fallback import KnownModelName, infer_model, merge_model_settings
from pydantic_ai.result import RunContext

@dataclass(init=False)
class RoundRobinModel(Model):
    """A model that cycles through multiple models in a round-robin fashion.
    
    This model distributes requests across multiple candidate models to help
    overcome rate limits or distribute load.
    """
    
    models: List[Model]
    _current_index: int = field(default=0, repr=False)
    _model_name: str = field(repr=False)

    def __init__(
        self,
        *models: Model | KnownModelName | str,
    ):
        """Initialize a round-robin model instance.
        
        Args:
            models: The names or instances of models to cycle through.
        """
        super().__init__()
        if not models:
            raise ValueError("At least one model must be provided")
        self.models = [infer_model(m) for m in models]
        self._current_index = 0

    @property
    def model_name(self) -> str:
        """The model name showing this is a round-robin model with its candidates."""
        return f'round_robin:{",".join(model.model_name for model in self.models)}'

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
        self._current_index = (self._current_index + 1) % len(self.models)
        return model

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request using the next model in the round-robin sequence."""
        current_model = self._get_next_model()
        merged_settings = merge_model_settings(current_model.settings, model_settings)
        customized_model_request_parameters = current_model.customize_request_parameters(model_request_parameters)
        
        try:
            response = await current_model.request(messages, merged_settings, customized_model_request_parameters)
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
        merged_settings = merge_model_settings(current_model.settings, model_settings)
        customized_model_request_parameters = current_model.customize_request_parameters(model_request_parameters)
        
        async with current_model.request_stream(
            messages, merged_settings, customized_model_request_parameters, run_context
        ) as response:
            self._set_span_attributes(current_model)
            yield response

    def _set_span_attributes(self, model: Model):
        """Set span attributes for observability."""
        with suppress(Exception):
            span = get_current_span()
            if span.is_recording():
                attributes = getattr(span, 'attributes', {})
                if attributes.get('gen_ai.request.model') == self.model_name:
                    span.set_attributes(model.model_attributes(model))