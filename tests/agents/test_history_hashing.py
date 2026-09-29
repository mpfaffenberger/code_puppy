"""Tests for the stable content-based hashing in code_puppy.agents._history.

Properties under test:
- Determinism: same content -> same hash across separate constructions
  (and across processes: the digest is sha256-based, not builtin hash()).
- Sensitivity: content / tool_call_id changes change the hash.
- BinaryContent bytes participate in the hash.
- Version resilience: hashing keys on ``part_kind``, NOT the class name, so
  a pydantic-ai class rename does not invalidate existing dedup hashes.
"""

import hashlib

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.agents._history import hash_message, stringify_part


def test_same_content_same_hash_across_constructions():
    msg_a = ModelRequest(parts=[UserPromptPart(content="hello puppy")])
    msg_b = ModelRequest(parts=[UserPromptPart(content="hello puppy")])
    assert hash_message(msg_a) == hash_message(msg_b)


def test_hash_ignores_timestamps():
    part_a = UserPromptPart(content="woof")
    part_b = UserPromptPart(content="woof")
    # Different timestamps must not affect the hash.
    assert part_a.timestamp != part_b.timestamp or True  # timestamps may collide
    assert hash_message(ModelRequest(parts=[part_a])) == hash_message(
        ModelRequest(parts=[part_b])
    )


def test_hash_is_16_char_hex_string():
    digest = hash_message(ModelRequest(parts=[UserPromptPart(content="x")]))
    assert isinstance(digest, str)
    assert len(digest) == 16
    int(digest, 16)  # raises if not hex


def test_hash_is_process_independent_sha256():
    """The digest is sha256 of the canonical string — NOT salted hash()."""
    msg = ModelRequest(parts=[UserPromptPart(content="hello")])
    canonical = stringify_part(msg.parts[0])
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    assert hash_message(msg) == expected


def test_hash_differs_when_content_differs():
    msg_a = ModelRequest(parts=[UserPromptPart(content="hello")])
    msg_b = ModelRequest(parts=[UserPromptPart(content="goodbye")])
    assert hash_message(msg_a) != hash_message(msg_b)


def test_hash_differs_when_tool_call_id_differs():
    msg_a = ModelResponse(
        parts=[ToolCallPart(tool_name="fetch", args="{}", tool_call_id="call_1")]
    )
    msg_b = ModelResponse(
        parts=[ToolCallPart(tool_name="fetch", args="{}", tool_call_id="call_2")]
    )
    assert hash_message(msg_a) != hash_message(msg_b)


def test_tool_return_hash_stable_and_id_sensitive():
    def make(tcid):
        return ModelRequest(
            parts=[ToolReturnPart(tool_name="fetch", content="ok", tool_call_id=tcid)]
        )

    assert hash_message(make("a")) == hash_message(make("a"))
    assert hash_message(make("a")) != hash_message(make("b"))


def test_binary_content_data_participates_in_hash():
    def make(data: bytes):
        return ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "look at this",
                        BinaryContent(data=data, media_type="image/png"),
                    ]
                )
            ]
        )

    assert hash_message(make(b"\x89PNG-one")) == hash_message(make(b"\x89PNG-one"))
    assert hash_message(make(b"\x89PNG-one")) != hash_message(make(b"\x89PNG-two"))


class _RenamedUserPromptPart:
    """Fake part: same part_kind/content as UserPromptPart, different class.

    Simulates pydantic-ai renaming its part classes in a new major version.
    Because hashing keys on ``part_kind``, the hash must be identical.
    """

    part_kind = "user-prompt"

    def __init__(self, content):
        self.content = content


def test_class_rename_does_not_change_hash():
    real = ModelRequest(parts=[UserPromptPart(content="stable across versions")])

    class _FakeMessage:
        parts = [_RenamedUserPromptPart("stable across versions")]

    assert hash_message(real) == hash_message(_FakeMessage())


def test_class_name_fallback_for_parts_without_part_kind():
    class _WeirdPart:
        content = "no part_kind here"

    assert stringify_part(_WeirdPart()).startswith("_WeirdPart|")


def test_text_part_uses_part_kind_not_class_name():
    s = stringify_part(TextPart(content="hi"))
    assert s.startswith("text|")
    assert "TextPart" not in s
