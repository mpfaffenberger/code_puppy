"""Flag handling for the local ripgrep grep path (``_build_grep_args``)."""

from code_puppy.tools.file_operations import _build_grep_args


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
