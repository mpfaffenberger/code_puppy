"""Tests for the static i18n extraction audit (code_puppy.i18n.audit)."""

from code_puppy.i18n import audit


def _kinds(source: str):
    return [s.kind for s in audit.audit_source(source, "x.py")]


# --- classification -------------------------------------------------------
def test_raw_string_literal_is_flagged():
    assert _kinds('emit_info("hello world")') == ["raw"]


def test_fstring_is_raw():
    assert _kinds('emit_warning(f"hi {name}")') == ["raw"]


def test_string_concat_is_raw():
    assert _kinds('emit_error("bad: " + detail)') == ["raw"]


def test_translation_call_is_extracted():
    assert _kinds('emit_info(t("startup.welcome"))') == ["extracted"]


def test_i18n_dotted_translation_call_is_extracted():
    assert _kinds('emit_info(i18n.t("startup.welcome"))') == ["extracted"]


def test_ngettext_and_lazy_are_extracted():
    src = 'emit_info(ngettext("files.deleted", n))\nemit_info(lazy("k"))'
    assert _kinds(src) == ["extracted", "extracted"]


def test_bare_variable_is_dynamic():
    assert _kinds("emit_info(msg)") == ["dynamic"]


def test_no_args_is_dynamic():
    assert _kinds("emit_info()") == ["dynamic"]


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
    assert len(report.raw) > 0  # extraction is still very much in progress
    assert 0.0 <= report.coverage <= 100.0
