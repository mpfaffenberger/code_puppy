"""i18n coverage for session_commands.py extraction.

Validates cmd.session.*, cmd.clear.*, cmd.compact.*, cmd.truncate.*,
cmd.quick_resume.*, cmd.dump_context.*, and cmd.load_context.* keys.
"""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

SESSION_PREFIXES = (
    "cmd.session.",
    "cmd.clear.",
    "cmd.compact.",
    "cmd.truncate.",
    "cmd.quick_resume.",
    "cmd.dump_context.",
    "cmd.load_context.",
)


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def _session_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if any(k.startswith(p) for p in SESSION_PREFIXES)]


def test_session_namespace_is_populated():
    assert len(_session_keys()) >= 35


def test_every_session_key_resolves():
    translate.set_locale("en-US")
    offenders = [
        k for k in _session_keys() if not translate.t(k) or translate.t(k) == k
    ]
    assert not offenders, f"session keys not resolving: {offenders}"


def test_every_session_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [k for k in _session_keys() if not translate.t(k).startswith("\u27e6")]
    assert not offenders, f"session keys not pseudolocalized: {offenders}"


def test_session_keys_interpolate():
    translate.set_locale("en-US")
    assert "mysess" in translate.t("cmd.session.info", name="mysess", prefix="/tmp/x")
    assert "newsess" in translate.t("cmd.session.new", name="newsess")


def test_clear_keys_interpolate():
    translate.set_locale("en-US")
    assert "abc123" in translate.t("cmd.clear.session_rotated", id="abc123")
    assert "3" in translate.t("cmd.clear.clipboard_cleared", count=3)


def test_compact_keys_interpolate():
    translate.set_locale("en-US")
    assert "20" in translate.t(
        "cmd.compact.compacting", count=20, strategy="summary", tokens="4,000"
    )
    truncation_success = translate.t(
        "cmd.compact.success.truncation",
        before_count=20,
        after_count=5,
        strategy="truncation",
        before_tokens="4,000",
        after_tokens="1,000",
        reduction_pct="75.0",
    )
    assert "truncation" in truncation_success
    assert "20" in truncation_success
    summarization_success = translate.t(
        "cmd.compact.success.summarization",
        before_count=20,
        after_count=5,
        before_tokens="4,000",
        after_tokens="1,000",
        reduction_pct="75.0",
    )
    assert "summarization" in summarization_success
    assert "75.0" in summarization_success
    assert "boom" in translate.t("cmd.compact.error", error="boom")


def test_truncate_keys_interpolate():
    translate.set_locale("en-US")
    assert "42" in translate.t("cmd.truncate.already_short", current=42, n=50)
    assert "10" in translate.t("cmd.truncate.success", before=15, after=10, kept=9)


def test_quick_resume_keys_interpolate():
    translate.set_locale("en-US")
    assert "main" in translate.t("cmd.quick_resume.searching", scope="myrepo/main")
    assert "7" in translate.t("cmd.quick_resume.success", count=7, tokens=1234)


def test_dump_context_keys_interpolate():
    translate.set_locale("en-US")
    assert "'bad'" in translate.t("cmd.dump_context.invalid_name", name="'bad'")
    assert "boom" in translate.t("cmd.dump_context.failed", error="boom")
    success = translate.t(
        "cmd.dump_context.success",
        message_count=10,
        total_tokens=2000,
        pickle_path="/tmp/ctx.pkl",
        metadata_path="/tmp/ctx.json",
    )
    assert "10" in success
    assert "/tmp/ctx.pkl" in success
    # Load-bearing emoji: the checkmark + folder are part of the /dump_context
    # UX. Regressing them silently is what triggered the review feedback the
    # first time -- keep them asserted so future extractions can't drop them.
    assert "\u2705" in success
    assert "\U0001f4c1" in success


def test_load_context_keys_interpolate():
    translate.set_locale("en-US")
    assert "/tmp/x.pkl" in translate.t("cmd.load_context.not_found", path="/tmp/x.pkl")
    assert "a, b" in translate.t("cmd.load_context.available", contexts="a, b")
    assert "boom" in translate.t("cmd.load_context.failed", error="boom")
    success = translate.t(
        "cmd.load_context.success",
        count=5,
        tokens=1000,
        path="/tmp/x.pkl",
        session_id="auto_session_123",
        file="x.pkl",
    )
    assert "5" in success and "auto_session_123" in success


def test_no_leftover_placeholders():
    translate.set_locale("en-US")
    src = catalog.load_catalog("en-US")
    for key in _session_keys():
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        if "{{" in text:
            continue
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{key} left an un-substituted placeholder: {rendered!r}"
        )


def test_session_commands_imports_cleanly():
    import code_puppy.command_line.session_commands  # noqa: F401
