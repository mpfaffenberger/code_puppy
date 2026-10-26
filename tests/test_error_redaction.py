"""Persisted errors.log text carries no credentials or home paths, and Args traversal is bounded."""

from __future__ import annotations

import pytest

from code_puppy import error_format as EL
from code_puppy.error_redaction import redact

SECRET = "SYNTHETIC_API_TOKEN_123"
HOMES = {
    "macos": "/Users/alice",
    "linux": "/home/alice",
    "windows": "C:\\Users\\alice",
}


def _failing_error(home: str) -> RuntimeError:
    """Chained error whose frames come from a file under *home* and whose text/Args hold the secret."""
    source = (
        "def f():\n"
        "    try:\n"
        "        raise ValueError(f'password={secret}')\n"
        "    except ValueError as cause:\n"
        "        raise RuntimeError(\n"
        "            f'Authorization: Bearer {secret}', {'api_key': secret}\n"
        "        ) from cause\n"
    )
    namespace = {"secret": SECRET}
    exec(compile(source, f"{home}\\plugin.py", "exec"), namespace)
    try:
        namespace["f"]()
    except RuntimeError as error:
        return error
    raise AssertionError("unreachable")


@pytest.mark.parametrize("home", HOMES.values(), ids=HOMES)
def test_no_persisted_field_keeps_a_credential_or_identifying_home_path(home):
    entry = EL._build_error_entry(
        _failing_error(home), f"load {home}\\plugin.py token={SECRET}", True, "T"
    )

    assert SECRET not in entry
    assert "alice" not in entry
    # Layout survives: every field is still present, and the chained cause is too.
    for field in (
        "Error Type: RuntimeError",
        "Error Message:",
        "Context:",
        "Traceback:",
        "Args:",
    ):
        assert field in entry
    assert "ValueError" in entry
    assert EL.render_message_entry(f"Bearer {SECRET}", None).count(SECRET) == 0


def test_the_users_own_nonstandard_home_is_redacted_too(monkeypatch, tmp_path):
    home = tmp_path / "profiles" / "bob"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    entry = EL._build_error_entry(
        ValueError(f"cannot read {home}/x.txt"), None, False, "T"
    )

    assert "bob" not in entry
    assert "cannot read ~/x.txt" in entry


def test_a_secret_straddling_the_cap_is_not_left_as_a_prefix():
    message = "m" * (EL._MAX_MESSAGE_CHARS - 5) + f" Bearer {SECRET}"

    entry = EL._build_error_entry(ValueError(message), None, False, "T")

    assert "SYNTH" not in entry
    assert "…[truncated" in entry


@pytest.mark.parametrize(
    "text",
    [
        "plain failure at /srv/app/main.py line 3",
        "GET https://api.example.com/home/alice/users/7 -> 404",
        "max length is 4096",
    ],
)
def test_ordinary_text_is_left_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("OPENAI_API_KEY=sk-abcdefghijklmnop1234", "OPENAI_API_KEY=[REDACTED]"),
        ("{'Authorization': 'Bearer abc.def-123'}", "{'Authorization': '[REDACTED]'}"),
        (
            "curl -H 'x-api-key: abc123' https://h",
            "curl -H 'x-api-key: [REDACTED]' https://h",
        ),
        ("got bearer abcdefgh12345678 back", "got bearer [REDACTED] back"),
        ("https://user:hunter2@host/path", "https://user:[REDACTED]@host/path"),
        ("leaked ghp_" + "a" * 36 + " here", "leaked [REDACTED] here"),
    ],
)
def test_credential_shapes_are_replaced_and_their_surroundings_kept(text, expected):
    assert redact(text) == expected


class _Leaf:
    visits = 0

    def __repr__(self) -> str:
        type(self).visits += 1
        return "leaf"


def test_a_shared_nested_graph_is_visited_a_bounded_number_of_times():
    nested: list = [_Leaf()]
    for _ in range(4):
        nested = [nested] * 32  # 32**4 leaf references, one list object per level
    _Leaf.visits = 0

    text = EL._args_text((nested,))

    assert _Leaf.visits <= EL._MAX_ARGS_NODES
    assert text.endswith(EL._ELIDED_MARKER)
    assert len(text) <= EL._MAX_ARGS_CHARS + len(EL._ELIDED_MARKER)
