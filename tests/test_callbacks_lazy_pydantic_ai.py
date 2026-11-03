"""Importing code_puppy.callbacks must not load pydantic_ai (startup path)."""

import asyncio
import subprocess
import sys

from code_puppy import callbacks

PROBE = (
    "import sys, code_puppy.callbacks\n"
    "print(any(m == 'pydantic_ai' or m.startswith('pydantic_ai.') "
    "for m in sys.modules))"
)


def test_importing_callbacks_does_not_load_pydantic_ai():
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"


def test_transform_model_messages_still_forwards_real_messages():
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    seen = []

    def hook(agent_name, messages):
        seen.append((agent_name, list(messages)))

    message = ModelRequest(parts=[UserPromptPart(content="hi")])
    callbacks.register_callback("transform_model_messages", hook)
    try:
        asyncio.run(callbacks.on_transform_model_messages("agent-x", [message]))
    finally:
        callbacks.unregister_callback("transform_model_messages", hook)

    assert seen == [("agent-x", [message])]
