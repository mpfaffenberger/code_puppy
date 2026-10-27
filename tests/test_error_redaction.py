"""Persisted errors.log text carries no credentials or home paths, and Args traversal is bounded."""

from __future__ import annotations

import time

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


QUOTED_SECRETS = {
    "whitespace": ('password="alpha beta gamma"', ("alpha", "beta", "gamma")),
    "comma-semicolon": ("{'api_key': 'alpha,beta;gamma'}", ("alpha", "beta", "gamma")),
    "escaped-quote": (r'secret="alpha \"beta\" gamma"', ("alpha", "beta", "gamma")),
    "single-quoted-source-line": ("token = 'alpha beta'", ("alpha", "beta")),
}


@pytest.mark.parametrize("case", QUOTED_SECRETS)
def test_a_quoted_credential_is_consumed_whole_in_every_persisted_field(case):
    text, fragments = QUOTED_SECRETS[case]
    error = ValueError(text)

    entry = EL._build_error_entry(error, text, True, "T")

    for fragment in fragments:
        assert fragment not in entry
    assert redact(redact(text)) == redact(text)  # a second pass changes nothing


def _spread_token_payloads() -> dict[str, str]:
    token = "ghp_" + "A" * 36
    return {
        # Cut points of reprlib's middle elision at maxstring 2048: head 1022, tail 1023.
        "straddles-the-head-cut": "x" * 1000 + " " + token + " " + "y" * 3000,
        "straddles-the-tail-cut": "y" * 3000 + " " + token + " " + "x" * 1000,
        "in-the-elided-middle": "x" * 2000 + " " + token + " " + "y" * 2000,
        "short": f"before {token} after",
    }


@pytest.mark.parametrize("case", _spread_token_payloads())
@pytest.mark.parametrize(
    "nest", [lambda s: (s,), lambda s: ({"k": [s]},)], ids=["flat", "nested"]
)
def test_a_token_cut_by_the_args_elision_leaves_no_fragment(case, nest):
    payload = _spread_token_payloads()[case]

    entry = EL.render_error_entry(ValueError(*nest(payload)), None, True)

    assert "ghp_" not in entry
    assert "AAAAAAAA" not in entry


class _LongRepr:
    def __repr__(self) -> str:
        return "x" * 1015 + " Bearer " + "S" * 40 + " " + "y" * 3000


def test_a_token_in_a_custom_repr_cut_by_the_elision_leaves_no_fragment():
    text = EL._args_text((_LongRepr(),))

    assert "SSSSSSSS" not in text
    assert text.endswith(EL._ELIDED_MARKER)


def _key_in_the_discarded_middle() -> dict[str, str]:
    filler = (
        "ordinary startup diagnostic " * 70
    )  # 1960 chars: key lands between the kept ends
    return {
        "bare": filler + "password=" + "A" * 5000,
        "single-quoted": filler + "password='" + "A" * 5000 + "'",
        "double-quoted": filler + 'password="' + "A" * 5000 + '"',
        # Past the whole-string scan budget only a head is kept, so the middle never shows.
        "beyond-the-scan-budget": "x" * (2 * EL._MAX_ARGS_SCAN_CHARS)
        + " password="
        + "A" * 5000,
    }


@pytest.mark.parametrize("case", _key_in_the_discarded_middle())
@pytest.mark.parametrize(
    "nest", [lambda s: (s,), lambda s: ({"k": [s]},)], ids=["flat", "nested"]
)
def test_a_secret_whose_key_was_elided_leaves_no_tail_in_args(case, nest):
    payload = _key_in_the_discarded_middle()[case]

    entry = EL.render_error_entry(ValueError(*nest(payload)), None, True)

    assert "AAAAAAAA" not in entry
    assert len(entry) <= EL._MAX_ENTRY_CHARS


BYTES_PASSWORDS = {
    "double-quote-inside-single-quoted": b"""password='alpha"beta'""",
    "single-quote-inside-double-quoted": b"""password="alpha'beta" """,
}


@pytest.mark.parametrize("case", BYTES_PASSWORDS)
def test_a_credential_in_a_bytes_repr_is_redacted_despite_escaped_delimiters(case):
    payload = BYTES_PASSWORDS[case]

    rendered = [
        redact(str(payload)),
        EL._args_text((payload,)),
        EL.render_error_entry(ValueError(payload), None, True),
    ]

    for text in rendered:
        assert "alpha" not in text
        assert "beta" not in text


def _interior_escape_payloads() -> dict[str, bytes | str]:
    """A credential whose interior quote follows a run of 1-4 literal backslashes.

    Whether that quote closes the value depends on escaping layers the text no longer
    shows, so every run must redact the whole remainder (never just up to the quote).
    """
    payloads: dict[str, bytes | str] = {}
    for run in range(1, 5):
        for quote, other in (("'", '"'), ('"', "'")):
            text = f"password={quote}alpha{chr(92) * run}{quote}beta{other}gamma{quote}"
            payloads[f"bytes-{quote}-run{run}"] = text.encode()
            payloads[f"str-{quote}-run{run}"] = text
    return payloads


INTERIOR_ESCAPES = _interior_escape_payloads()


@pytest.mark.parametrize("case", INTERIOR_ESCAPES)
def test_an_interior_quote_after_a_backslash_run_does_not_end_redaction(case):
    payload = INTERIOR_ESCAPES[case]

    rendered = [
        redact(str(payload)),
        EL._args_text((payload,)),
        EL.render_error_entry(ValueError(payload), None, True),
    ]

    for text in rendered:
        for fragment in ("alpha", "beta", "gamma"):
            assert fragment not in text
        assert "<entry could not be rendered>" not in text  # no rendering fallback


# Each unit is the worst case for one pattern: a quadratic scan turns 256 KB into minutes
# (the key-suffix pattern took 17s at 64 KB), a linear one into well under a second.
LINEAR_UNITS = {
    "key-suffix-token": "token",
    "key-suffix-dotted": "secret.",
    "key-suffix-api-key": "api_key",
    "backslash-run": "\\",
    "quote-backslash": "'\\",
    "escaped-opener": "password=\\'",
    "key-then-spaces": "token" + " " * 40,
    "home-prefix": "/Users/a",
    "url-userinfo": "://a:",
    # One per _TOKEN_SHAPE branch; the JWT branch needs a terminating dot, so it is the
    # one that can fail late and go quadratic.
    "jwt-prefix": "eyJ-",
    "jwt-two-segments": "eyJaaaaaaaa.aaaaaaaa ",
    "openai-prefix": "sk-",
    "github-prefix": "ghp_",
    "github-pat-prefix": "github_pat_",
    "aws-key-prefix": "AKIA",
    "slack-prefix": "xoxb-",
}
SCAN_SECONDS = 3.0


@pytest.mark.parametrize("case", LINEAR_UNITS)
def test_redaction_cost_is_linear_in_the_input_size(case):
    text = LINEAR_UNITS[case] * (256_000 // len(LINEAR_UNITS[case]))

    started = time.perf_counter()
    redact(text)

    assert time.perf_counter() - started < SCAN_SECONDS


def test_a_crash_with_a_huge_credential_named_argument_renders_quickly():
    started = time.perf_counter()
    EL.render_error_entry(ValueError("token" * 50_000), "ctx", True)

    assert time.perf_counter() - started < SCAN_SECONDS


def _redacted_sizes(monkeypatch) -> list[int]:
    sizes: list[int] = []

    def counting(text: str) -> str:
        sizes.append(len(text))
        return redact(text)

    monkeypatch.setattr(EL, "redact", counting)
    return sizes


def test_a_huge_bytes_or_custom_repr_is_never_redacted_whole(monkeypatch):
    sizes = _redacted_sizes(monkeypatch)

    EL._args_text((b"token" * 1_200_000,))  # a 6 MB repr, as in the review

    assert max(sizes) <= 4096


def test_the_scan_budget_is_shared_by_every_value_in_one_render(monkeypatch):
    sizes = _redacted_sizes(monkeypatch)

    EL._args_text(tuple(b"x" * 200_000 for _ in range(10)))

    assert sum(sizes) <= EL._MAX_ARGS_SCAN_CHARS + 16 * 1024


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/Users/bob/proj/x.py", "~/proj/x.py"),
        ("read /Users/bob: nope", "read ~: nope"),
        ("in /Users/bob.", "in ~."),
        # A longer or dotted name is another user: no part of it may survive.
        ("/Users/bobby/proj/x.py", "<home>/proj/x.py"),
        ("/Users/bob.old/x", "<home>/x"),
        ("/Users/Shared/tool", "<home>/tool"),
    ],
)
def test_own_home_needs_a_segment_boundary_and_other_homes_get_a_neutral_marker(
    monkeypatch, text, expected
):
    monkeypatch.setenv("HOME", "/Users/bob")
    monkeypatch.setenv("USERPROFILE", "/Users/bob")

    assert redact(text) == expected
