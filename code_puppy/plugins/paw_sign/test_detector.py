"""Tests for the paw-sign command detector."""

from code_puppy.plugins.paw_sign.detector import (
    PAW_SIGN,
    _is_commit_with_message,
    _split_segments,
    paw_sign_command,
)


# --- the happy path: commands that should get signed ------------------------


def test_simple_commit_gets_signed():
    out = paw_sign_command('git commit -m "fix the thing"')
    assert out == "git commit -m \"fix the thing\" -m '%s'" % PAW_SIGN


def test_add_then_commit_signs_the_commit():
    out = paw_sign_command('git add . && git commit -m "wip"')
    assert out is not None
    assert out.endswith("-m '%s'" % PAW_SIGN)
    # original commit body untouched
    assert 'git commit -m "wip"' in out


def test_long_message_flag():
    out = paw_sign_command('git commit --message "hello"')
    assert out is not None
    assert out.endswith("-m '%s'" % PAW_SIGN)


def test_message_equals_form():
    out = paw_sign_command('git commit --message="hello"')
    assert out is not None
    assert out.endswith("-m '%s'" % PAW_SIGN)


def test_combined_short_flags():
    out = paw_sign_command('git commit -am "quick"')
    assert out is not None
    assert out.endswith("-m '%s'" % PAW_SIGN)


def test_amend_with_message_is_signed():
    out = paw_sign_command('git commit --amend -m "redo"')
    assert out is not None
    assert out.endswith("-m '%s'" % PAW_SIGN)


def test_paw_sign_contains_emoji_glyph():
    # The escape really does resolve to the paw-print glyph at runtime.
    assert "\U0001f43e" in PAW_SIGN


# --- the conservative path: commands we must leave alone --------------------


def test_editor_commit_not_signed():
    assert paw_sign_command("git commit") is None
    assert paw_sign_command("git commit --amend") is None


def test_commit_not_last_in_chain_not_signed():
    # Appending at the end would attach to `git push`, so we bail.
    assert paw_sign_command('git commit -m "wip" && git push') is None


def test_non_commit_command_not_signed():
    assert paw_sign_command("git status") is None
    assert paw_sign_command("echo hello") is None
    assert paw_sign_command("ls -la") is None


def test_empty_or_none_not_signed():
    assert paw_sign_command("") is None
    assert paw_sign_command(None) is None


def test_unbalanced_quotes_not_signed():
    assert paw_sign_command('git commit -m "unterminated') is None


def test_idempotent_already_signed():
    once = paw_sign_command('git commit -m "fix"')
    assert once is not None
    # Running it again must be a no-op (no double paw).
    assert paw_sign_command(once) is None


def test_commit_word_in_string_not_misfired():
    # "commit" appears but it's not a git commit command.
    assert paw_sign_command('echo "let us commit to this"') is None


def test_trailing_operator_not_signed():
    # A trailing ; leaves an empty last segment -> not safe to append.
    assert paw_sign_command('git commit -m "wip" ;') is None


def test_signoff_no_message_not_signed():
    assert paw_sign_command("git commit -s") is None


# --- helper-level unit tests ------------------------------------------------


def test_split_segments_basic():
    segs = _split_segments(["git", "add", ".", "&&", "git", "commit"])
    assert segs == [["git", "add", "."], ["git", "commit"]]


def test_is_commit_with_message_rejects_long_m_flags():
    # --amend contains an "m" but must NOT count as a message flag.
    assert _is_commit_with_message(["git", "commit", "--amend"]) is False
    assert _is_commit_with_message(["git", "commit", "-m", "x"]) is True
