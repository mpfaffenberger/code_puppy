"""Z.AI (GLM) chat model: an OpenAI-compatible endpoint with one quirk.

Lives in its own module so ``model_factory`` can import it lazily -- the
``OpenAIChatModel`` base class pulls in the whole ``openai`` SDK, which
only Z.AI / OpenAI-family runs should pay for.
"""

from pydantic_ai.models.openai import OpenAIChatModel


class ZaiChatModel(OpenAIChatModel):
    """Z.AI omits ``object: chat.completion``; restore it so the SDK parses."""

    def _process_response(self, response):
        response.object = "chat.completion"
        return super()._process_response(response)
