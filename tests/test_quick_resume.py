"""Focused tests for /quick-resume argument parsing and CLI wiring.

These cover the OS-agnostic path handling -- the key regression being that
Windows backslash paths must NOT be mangled (the old shlex POSIX parse turned
``C:\\Users\\Wes\\proj`` into ``C:UsersWesproj``).
"""

import argparse

import pytest

from code_puppy.cli_runner import apply_quick_resume
from code_puppy.command_line.session_commands import _parse_quick_resume_target


@pytest.mark.parametrize(
    "command, expected",
    [
        # Windows: backslashes must survive intact (the original bug).
        (r"/quick-resume C:\Users\Wes\proj", r"C:\Users\Wes\proj"),
        (r"/qr D:\repos\a b\c", r"D:\repos\a b\c"),
        (r'/qr "C:\Program Files\My App"', r"C:\Program Files\My App"),
        # macOS / Linux: absolute, quoted-with-spaces, and relative.
        ("/quick-resume /Users/me/proj", "/Users/me/proj"),
        ('/qr "/Users/me/My Project"', "/Users/me/My Project"),
        ("/quick-resume ./child/src", "./child/src"),
        ("/quick-resume '/tmp/quoted single'", "/tmp/quoted single"),
        # No path -> current directory; whitespace-only is treated as none.
        ("/quick-resume", "."),
        ("/qr", "."),
        ("/quick-resume   ", "."),
    ],
)
def test_parse_quick_resume_target(command, expected):
    assert _parse_quick_resume_target(command) == expected


def _args(**kwargs):
    """Build an argparse.Namespace with quick-resume-relevant defaults."""
    ns = argparse.Namespace(resume=None, quick_resume=None)
    for key, value in kwargs.items():
        setattr(ns, key, value)
    return ns


def test_apply_quick_resume_noop_when_unset():
    """No --quick-resume flag -> nothing happens, resume stays None."""
    args = _args()
    assert apply_quick_resume(args) is False
    assert args.resume is None


def test_apply_quick_resume_explicit_resume_wins():
    """An explicit --resume always takes precedence over --quick-resume."""
    args = _args(resume="/path/to/session.pkl", quick_resume=".")
    assert apply_quick_resume(args) is False
    assert args.resume == "/path/to/session.pkl"


def test_apply_quick_resume_sets_resume_on_hit(monkeypatch):
    """A resolvable scope populates args.resume with the pickle path."""
    monkeypatch.setattr(
        "code_puppy.config.get_quick_resume_location",
        lambda target: ("/repo", "main"),
    )
    monkeypatch.setattr(
        "code_puppy.config.resolve_quick_resume_pickle",
        lambda target: "/auto/auto_session_X.pkl",
    )
    args = _args(quick_resume=".")
    assert apply_quick_resume(args) is True
    assert args.resume == "/auto/auto_session_X.pkl"


def test_apply_quick_resume_graceful_miss(monkeypatch):
    """No matching session -> returns False and leaves resume unset."""
    monkeypatch.setattr(
        "code_puppy.config.get_quick_resume_location",
        lambda target: ("/repo", None),
    )
    monkeypatch.setattr(
        "code_puppy.config.resolve_quick_resume_pickle",
        lambda target: None,
    )
    args = _args(quick_resume="/some/where")
    assert apply_quick_resume(args) is False
    assert args.resume is None
