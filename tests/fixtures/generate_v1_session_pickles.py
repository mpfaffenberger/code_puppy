"""Generate golden pickle fixtures from pydantic-ai v1 message classes.

Run this ONLY while the project still depends on pydantic-ai 1.x. The
resulting ``.pkl`` files are committed to the repo and used by
``tests/test_session_format_migration.py`` to prove that the surrogate
unpickler + normalizer can migrate v1-era session pickles WITHOUT importing
(or even having installed) the pydantic-ai version that produced them.

Files produced (all in this directory):

- ``session_v1_plain.pkl``   -- raw ``pickle.dumps(history)`` (the modern
  pre-JSON session format written by ``session_storage.save_session``).
- ``session_v1_signed.pkl``  -- the legacy signed framing:
  ``CPSESSION\\x01`` header + 32 signature bytes + pickle payload.
- ``subagent_v1_history.pkl`` -- a bare history list written the way
  ``tools/agent_tools._save_session_history`` used to (plain pickle.dump).

Timestamps are pinned so tests can assert exact round-tripped values.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

FIXTURE_DIR = Path(__file__).parent

# Deterministic timestamp so tests can assert exact values post-migration.
TS = datetime(2025, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

PNG_BYTES = b"\x89PNG\r\n\x1a\nnot-really-a-png"

LEGACY_SIGNED_HEADER = b"CPSESSION\x01"
LEGACY_SIGNATURE_SIZE = 32


def build_history() -> list:
    """A realistic multi-turn history touching every part kind we migrate."""
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(
                    content="You are Biscuit, a digital puppy.", timestamp=TS
                ),
                UserPromptPart(
                    content=[
                        "What's in this image?",
                        BinaryContent(data=PNG_BYTES, media_type="image/png"),
                    ],
                    timestamp=TS,
                ),
            ]
        ),
        ModelResponse(
            parts=[
                ThinkingPart(content="pondering the png...", signature="sig-abc123"),
                TextPart(content="Looks like a PNG. Let me grep around."),
                ToolCallPart(
                    tool_name="grep",
                    args={"search_string": "puppy"},
                    tool_call_id="call_1",
                ),
            ],
            model_name="gpt-golden",
            timestamp=TS,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="grep",
                    content="3 matches",
                    tool_call_id="call_1",
                    timestamp=TS,
                )
            ]
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="please try again",
                    tool_name="grep",
                    tool_call_id="call_2",
                    timestamp=TS,
                )
            ]
        ),
        ModelResponse(
            parts=[TextPart(content="Found 3 matches. Woof.")],
            model_name="gpt-golden",
            timestamp=TS,
        ),
    ]


def main() -> None:
    history = build_history()
    payload = pickle.dumps(history)

    (FIXTURE_DIR / "session_v1_plain.pkl").write_bytes(payload)
    (FIXTURE_DIR / "session_v1_signed.pkl").write_bytes(
        LEGACY_SIGNED_HEADER + b"\x00" * LEGACY_SIGNATURE_SIZE + payload
    )
    with (FIXTURE_DIR / "subagent_v1_history.pkl").open("wb") as f:
        pickle.dump(history, f)

    print("Fixtures written to", FIXTURE_DIR)


if __name__ == "__main__":
    main()
