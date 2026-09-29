"""Tests for the static i18n extraction audit (code_puppy.i18n.audit)."""

import ast

import pytest

from code_puppy.i18n import audit


def _kinds(source: str):
    return [s.kind for s in audit.audit_source(source, "x.py")]


# classification: (source, expected kinds), one per emit shape — was one test
# per case before consolidating into this matrix.
_CLASSIFICATION_CASES = [
    # raw string literals / concatenations must be flagged
    ('emit_info("hello world")', ["raw"]),
    # f-strings with literal content are raw
    ('emit_warning(f"hi {name}")', ["raw"]),
    ('emit_error(f"Error: {e}")', ["raw"]),
    # non-whitespace punctuation (an arrow) counts as literal content
    ('emit_info(f"-> {item}")', ["raw"]),
    ('emit_error("bad: " + detail)', ["raw"]),
    # pure-variable / whitespace-only f-strings are not translatable
    ('emit_info(f"{result}")', ["dynamic"]),
    ('emit_info(f"   {msg}")', ["dynamic"]),
    # t() / i18n.t() calls are the extracted path
    ('emit_info(t("startup.welcome"))', ["extracted"]),
    ('emit_info(i18n.t("startup.welcome"))', ["extracted"]),
    # bare variables / no args have nothing to translate
    ("emit_info(msg)", ["dynamic"]),
    ("emit_info()", ["dynamic"]),
    # qualified emit sinks and console printers are user-facing
    ('messaging.emit_info("x")', ["raw"]),
    ('console.print("boom")', ["raw"]),
    ('self.console.print("boom")', ["raw"]),
]


@pytest.mark.parametrize("source,expected", _CLASSIFICATION_CASES)
def test_classification(source: str, expected: list[str]) -> None:
    """Every user-facing emit shape must be classified exactly once and
    with the right kind (raw / dynamic / extracted)."""
    assert _kinds(source) == expected


def test_fstring_wrapped_literal_is_raw():
    """f"{'literal'}" wraps a Constant inside a FormattedValue.

    The classifier used to only inspect direct Constant children of
    JoinedStr, so this parsed as ``JoinedStr([FormattedValue(Constant)])``
    and was silently classified as dynamic — a false negative. Recurse
    into FormattedValue.value so it now shows up as raw.
    """
    src = "emit_info(f\"{'Error: connection refused'}\")"
    # Direct AST check so we're not relying on the higher-level pipeline.
    tree = ast.parse(src, mode="eval")
    call = tree.body
    assert isinstance(call, ast.Call)
    joined = call.args[0]
    assert isinstance(joined, ast.JoinedStr)
    assert isinstance(joined.values[0], ast.FormattedValue)
    # And end-to-end through the classifier.
    assert audit._classify(joined) == "raw"
    assert _kinds(src) == ["raw"]


def test_ngettext_and_lazy_are_extracted():
    src = 'emit_info(ngettext("files.deleted", n))\nemit_info(lazy("k"))'
    assert _kinds(src) == ["extracted", "extracted"]


# --- callee detection -----------------------------------------------------
def test_emit_prefix_variants_detected():
    src = 'emit_success("a")\nemit_prompt("b")\nemit_system_message("c")'
    assert _kinds(src) == ["raw", "raw", "raw"]


def test_module_qualified_emit_detected():
    assert _kinds('messaging.emit_info("x")') == ["raw"]


def test_console_print_detected():
    assert _kinds('console.print("boom")') == ["raw"]


def test_self_console_print_detected():
    assert _kinds('self.console.print("boom")') == ["raw"]


def test_unrelated_calls_ignored():
    # logging.info / print() / arbitrary calls are not user-facing emit sinks.
    src = 'logging.info("x")\nprint("y")\nfoo("z")'
    assert _kinds(src) == []


def test_emit_definition_not_counted_as_site():
    # A `def emit_info(...)` is a definition, not a call site.
    assert _kinds("def emit_info(msg):\n    pass") == []


# --- aggregation / coverage ----------------------------------------------
def test_coverage_math():
    src = 'emit_info(t("a"))\nemit_info("raw1")\nemit_info("raw2")\nemit_info(x)'
    report = audit.Report(sites=audit.audit_source(src, "x.py"))
    assert len(report.extracted) == 1
    assert len(report.raw) == 2
    assert len(report.dynamic) == 1
    # dynamic excluded from the denominator: 1 / (1 + 2)
    assert round(report.coverage, 1) == 33.3


def test_empty_module_is_full_coverage():
    report = audit.Report(sites=[])
    assert report.coverage == 100.0


# --- CLI entrypoint -------------------------------------------------------
def test_fail_under_gate(tmp_path, capsys):
    mod = tmp_path / "m.py"
    mod.write_text('emit_info("raw only, 0% coverage")\n', encoding="utf-8")
    # Coverage is 0% here, so a 50% floor must fail (exit 1).
    assert audit.main([str(tmp_path), "--fail-under", "50"]) == 1
    # And a 0% floor passes.
    assert audit.main([str(tmp_path), "--fail-under", "0"]) == 0


def test_json_output_is_valid(tmp_path, capsys):
    import json

    mod = tmp_path / "m.py"
    mod.write_text('emit_info(t("k"))\nemit_info("raw")\n', encoding="utf-8")
    assert audit.main([str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["extracted"] == 1
    assert payload["raw"] == 1
    assert payload["coverage"] == 50.0


def test_single_file_path_is_accepted(tmp_path, capsys):
    """Passing a .py file directly must produce a non-empty report.

    Previously ``_iter_py_files`` called ``os.walk(file)`` which yields
    nothing, so every per-file audit silently returned 0 sites.
    """
    import json

    mod = tmp_path / "solo.py"
    mod.write_text('emit_info("raw string")\n', encoding="utf-8")
    assert audit.main([str(mod), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["raw"] == 1, "single-file audit must find the raw site"


def test_single_file_pure_variable_fstring_not_raw(tmp_path, capsys):
    """Single-file audit: f"{var}" must NOT be counted as raw."""
    import json

    mod = tmp_path / "mod.py"
    mod.write_text('emit_info(f"{result}")\n', encoding="utf-8")
    assert audit.main([str(mod), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["raw"] == 0
    assert payload["dynamic"] == 1


def test_nonexistent_path_raises(tmp_path, capsys):
    """A typo'd path must not silently report 100% coverage.

    Previously ``audit_tree('/does/not/exist')`` returned an empty
    ``Report`` whose ``coverage`` property is ``100.0``, so
    ``--fail-under`` would happily pass on a typo'd path and tell CI
    everything was fine. Fail loud instead: this is a
    programming/config error, so ``FileNotFoundError`` propagates all
    the way out of ``main()`` and produces a nonzero exit.
    """
    import pytest

    missing = tmp_path / "totally-not-real"
    assert not missing.exists()

    # audit_tree raises directly.
    with pytest.raises(FileNotFoundError):
        audit.audit_tree(str(missing))

    # And main() lets it propagate — no accidental swallow, no exit 0.
    with pytest.raises(FileNotFoundError):
        audit.main([str(missing)])


# --- integration smoke ----------------------------------------------------
def test_audits_the_real_package_without_error():
    """The tool must stay runnable against the live tree as it evolves.

    Guards against the AST classifier silently breaking on new syntax: it
    should find real emit sites and report a sane coverage percentage.
    """
    import os

    from code_puppy import i18n

    root = os.path.dirname(os.path.dirname(os.path.abspath(i18n.__file__)))
    report = audit.audit_tree(root)
    assert report.sites, "expected to find user-facing emit sites"
    assert 0.0 <= report.coverage <= 100.0
