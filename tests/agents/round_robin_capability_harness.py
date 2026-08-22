"""Shared harness for the ``RoundRobinRequests`` capability test files.

Leaf fabrication (FunctionModel + a scripted self-preparing Model), suspended
continuation responses, request-context construction, and eager-path spies.
"""

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.round_robin_model import RoundRobinModel


def make_leaf(name: str, hits: dict[str, int]) -> FunctionModel:
    """A FunctionModel leaf that records how often it served a request."""

    def respond(messages: list, info: AgentInfo) -> ModelResponse:
        hits[name] = hits.get(name, 0) + 1
        return ModelResponse(parts=[TextPart(f"reply from {name}")])

    async def stream_respond(messages: list, info: AgentInfo):
        hits[name] = hits.get(name, 0) + 1
        yield f"reply from {name}"

    return FunctionModel(respond, stream_function=stream_respond, model_name=name)


class ScriptedLeaf(Model):
    """A minimal leaf Model with a scripted response sequence.

    Mirrors real provider leaves: ``request`` calls ``self.prepare_request``
    internally before serving, and records what it received so parity
    assertions can compare the eager and capability-owned delivery paths.
    """

    def __init__(self, name: str, script):
        super().__init__()
        self._name = name
        self.script = list(script)
        self.calls = 0
        self.customize_calls = 0
        self.received: list[tuple] = []

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "test"

    def customize_request_parameters(self, model_request_parameters):
        # Deliberately observable (non-idempotent counter): parity between
        # eager and owned paths must show the SAME application count at the
        # moment the request is served.
        self.customize_calls += 1
        return model_request_parameters

    async def request(self, messages, model_settings, model_request_parameters):
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        self.calls += 1
        self.received.append((model_settings, self.customize_calls))
        return self.script.pop(0)()


def suspended_response(name: str) -> ModelResponse:
    return ModelResponse(
        parts=[TextPart(f"partial from {name}")],
        state="suspended",
        provider_response_id="job-1",
    )


def complete_response(name: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(f"final from {name}")])


def request_context(model, prompt: str = "hi") -> ModelRequestContext:
    return ModelRequestContext(
        model=model,
        messages=[ModelRequest(parts=[UserPromptPart(content=prompt)])],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )


async def passthrough_handler(req_ctx: ModelRequestContext) -> ModelResponse:
    return ModelResponse(parts=[TextPart("handled")])


def spy_eager_requests(rr: RoundRobinModel) -> list[str]:
    """Instance-level spies counting eager RoundRobinModel request entries."""
    calls: list[str] = []
    original_request = rr.request
    original_stream = rr.request_stream

    async def spying_request(*args, **kwargs):
        calls.append("request")
        return await original_request(*args, **kwargs)

    def spying_stream(*args, **kwargs):
        calls.append("request_stream")
        return original_stream(*args, **kwargs)

    rr.request = spying_request  # type: ignore[method-assign]
    rr.request_stream = spying_stream  # type: ignore[method-assign]
    return calls
