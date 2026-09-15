"""Flag handling for the local ripgrep grep path (``_build_grep_args``)."""

from code_puppy.tools.file_operations import (
    _build_backend_matcher,
    _build_grep_args,
    _carries_type_filter,
)


def test_build_grep_args_rejects_unsupported_flags():
    """A flag the tool does not understand is dropped, not forwarded to ripgrep."""
    args, error = _build_grep_args("--pre echo hi")
    assert "--pre" not in args
    assert error is not None
    assert "--pre" in error


def test_build_grep_args_rejects_unsupported_flags_with_inline_value():
    """The ``--flag=value`` form is evaluated on its flag part, then rejected."""
    args, error = _build_grep_args("--pre=echo")
    assert "--pre=echo" not in args
    assert "--pre" not in args
    assert error is not None
    assert "--pre" in error


def test_build_grep_args_allows_supported_flag():
    """A supported content flag still reaches ripgrep unchanged."""
    args, error = _build_grep_args("-i foo")
    assert error is None
    assert args == ["-i", "foo"]


def test_build_grep_args_plain_pattern_unaffected():
    """A normal search string is still passed verbatim via ``-e``."""
    args, error = _build_grep_args("foo bar")
    assert error is None
    assert args == ["-e", "foo bar"]


def test_build_grep_args_value_flag_as_last_token_errors():
    """A trailing value-taking flag must error, not eat the target directory."""
    args, error = _build_grep_args("-e")
    assert args == []
    assert error is not None
    assert "-e" in error and "value" in error


def test_build_grep_args_expands_clustered_short_flags():
    """-iw and -C3 cluster the way ripgrep itself parses them."""
    args, error = _build_grep_args("-iw foo")
    assert error is None
    assert args == ["-i", "-w", "foo"]

    args, error = _build_grep_args("-C3 foo")
    assert error is None
    assert args == ["-C", "3", "foo"]

    args, error = _build_grep_args("-tpy foo")
    assert error is None
    assert args == ["-t", "py", "foo"]


def test_build_grep_args_expanded_invert_and_smart_case():
    args, error = _build_grep_args("-vS foo")
    assert error is None
    assert args == ["-v", "-S", "foo"]


def test_build_grep_args_unknown_cluster_member_still_rejected():
    args, error = _build_grep_args("-iZ foo")
    assert args == []
    assert error is not None


def test_build_grep_args_rejects_short_type_not():
    """ripgrep's -T is --type-not (value-taking), never a --trim alias."""
    args, error = _build_grep_args("-T 'def foo'")
    assert args == []
    assert error is not None
    assert "-T" in error


def test_build_grep_args_trim_is_long_only():
    """--trim has only a long form and stays supported."""
    args, error = _build_grep_args("--trim foo")
    assert error is None
    assert args == ["--trim", "foo"]


def test_build_grep_args_value_not_shredded():
    """A value that looks like a flag cluster reaches ripgrep verbatim."""
    args, error = _build_grep_args("-e -in")
    assert error is None
    assert args == ["-e", "-in"]


def test_build_grep_args_value_keeps_cluster_literal():
    """``-e '-C3'`` searches the literal ``-C3``; it is not read as ``-C 3``."""
    args, error = _build_grep_args("-e '-C3'")
    assert error is None
    assert args == ["-e", "-C3"]


def test_build_grep_args_flag_only_errors():
    """A supported flag with no pattern errors, and both paths agree verbatim."""
    args, error = _build_grep_args("-w")
    assert args == []
    assert error == "no search pattern provided"

    _pattern, _exts, backend_error = _build_backend_matcher("-w")
    assert backend_error == error


def test_carries_type_filter_matches_short_equals():
    """``-t=VALUE`` counts as a type filter, alongside the other type forms."""
    assert _carries_type_filter(["-t=py", "def"]) is True
    assert _carries_type_filter(["-t", "py", "def"]) is True
    assert _carries_type_filter(["--type=py", "def"]) is True
    assert _carries_type_filter(["-e", "def foo"]) is False


def test_build_backend_matcher_value_not_shredded():
    """The backend path agrees with the local path: the value stays intact."""
    pattern, _exts, error = _build_backend_matcher("-e -in")
    assert error is None
    assert pattern is not None
    assert pattern.pattern == "-in"
    # A shredded "-i" search would have matched the bare "-i" line below.
    assert pattern.search("-in") is not None
    assert pattern.search("-i") is None
