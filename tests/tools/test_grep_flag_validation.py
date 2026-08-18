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
