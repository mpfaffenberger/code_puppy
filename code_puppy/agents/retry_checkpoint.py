"""Resume failed turns without counting user-input bookkeeping as progress."""

from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart

from code_puppy.agents._history import hash_message


class RetryCheckpoint:
    """Track distinct checkpointed responses across history compaction.

    A response enters persistent history at a subsequent model-step boundary.
    Replayed user requests, retries, and partial streaming text are not steps.
    Keep a cumulative count so compaction cannot move progress backwards.
    """

    def __init__(self, agent):
        self.agent = agent
        self.seen = {
            hash_message(message)
            for message in agent._message_history or []
            if isinstance(message, ModelResponse)
        }
        self.completed = 0

    def progress(self):
        for message in self.agent._message_history or []:
            if isinstance(message, ModelResponse) and message.parts:
                key = hash_message(message)
                if key not in self.seen:
                    self.seen.add(key)
                    self.completed += 1
        return self.completed


def resumable_call(agent, pydantic_agent, prompt, **kwargs):
    """One logical prompt: resend only if it never reached persistent history."""
    checkpointed = False

    async def call():
        nonlocal checkpointed
        previous_parts = {
            id(part)
            for message in agent._message_history or []
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
        }
        try:
            return await pydantic_agent.run(
                None if checkpointed else prompt,
                message_history=agent._message_history,
                **kwargs,
            )
        finally:
            checkpointed = checkpointed or any(
                isinstance(part, UserPromptPart) and id(part) not in previous_parts
                for message in agent._message_history or []
                if isinstance(message, ModelRequest)
                for part in message.parts
            )

    return call
