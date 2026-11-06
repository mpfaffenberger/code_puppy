"""Input handling for scripts/boot_trace_report.py: bounds, privacy, numerics, identities.

The helpers at the top are shared with test_boot_trace_report.py.
"""

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "boot_trace_report.py"
_SPEC = importlib.util.spec_from_file_location("boot_trace_report", SCRIPT)
REPORT = importlib.util.module_from_spec(_SPEC)
sys.modules["boot_trace_report"] = REPORT  # dataclasses resolve their module by name
_SPEC.loader.exec_module(REPORT)

TAG = "CODE_PUPPY_BOOT_TRACE "
BOOT = "ab" * 16
SECRET_LINE = "sk-SECRET-123 password=hunter2"
MISSING = object()


def record(kind, phase, span_id, *, dur=None, parent=None, attrs=None, **extra):
    rec = {
        "v": 1,
        "bootId": BOOT,
        "seq": 0,
        "phase": phase,
        "span": span_id,
        "kind": kind,
        "tMonoMs": 1.0,
        "tWallMs": 1_700_000_000_000,
        "attrs": attrs or {},
    }
    if parent is not None:
        rec["parent"] = parent
    if dur is not None:
        rec["durMs"] = dur
    rec.update(extra)
    return rec


def span_pair(phase, dur, span_id, *, attrs=None, parent=None, kind="end"):
    return [
        record("start", phase, span_id, parent=parent, attrs=attrs),
        record(kind, phase, span_id, dur=dur, parent=parent, attrs=attrs),
    ]


def numbered(records, start=1):
    for seq, rec in enumerate(records, start=start):
        rec["seq"] = seq
    return records


def encode(rec) -> str:
    return json.dumps(rec, separators=(",", ":"))


def tagged(rec) -> str:
    return TAG + encode(rec)


def write_lines(tmp_path, lines, name="trace.txt") -> Path:
    path = tmp_path / name
    encoded = [
        line.encode("utf-8") if isinstance(line, str) else line for line in lines
    ]
    path.write_bytes(b"\n".join(encoded) + b"\n")
    return path


def run_report(capsys, *argv):
    code = REPORT.main([str(arg) for arg in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def report_row(out, label):
    """Return the table row that carries ``label`` as a whole token."""
    for line in out.splitlines():
        if label in line.split():
            return line
    raise AssertionError(f"no row for {label!r} in report")


def row_cells(row):
    """Split a fixed-width table row on runs of two or more spaces."""
    return re.split(r"\s{2,}", row.strip())


def test_secret_shaped_noise_is_ignored_in_tagged_streams(tmp_path, capsys):
    records = numbered(span_pair("cli.parse", 1.0, "1"))
    lines = [SECRET_LINE, "", tagged(records[0]), tagged(records[1])]
    code, out, err = run_report(capsys, write_lines(tmp_path, lines))

    assert code == 0
    assert "INCOMPLETE" not in out
    assert "cli.parse" in out
    assert SECRET_LINE not in out + err


@pytest.mark.parametrize("tag", [False, True], ids=["raw-jsonl", "tagged"])
def test_secret_shaped_garbage_is_malformed_and_never_echoed(tmp_path, capsys, tag):
    wrap = tagged if tag else encode
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    garbage = TAG + SECRET_LINE if tag else SECRET_LINE
    lines = [wrap(start), garbage, wrap(end)]
    code, out, err = run_report(capsys, write_lines(tmp_path, lines))

    assert code == 1
    assert "malformed=1" in out
    assert "cli.parse" in out
    assert "hunter2" not in out + err
    assert SECRET_LINE not in out + err


def test_oversized_line_is_malformed_drained_and_never_parsed(tmp_path, capsys):
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    oversized = dict(start, attrs={"pad": "x" * 3000})
    lines = [tagged(oversized), tagged(start), tagged(end)]
    code, out, err = run_report(capsys, write_lines(tmp_path, lines))

    assert code == 1
    assert "malformed=1" in out
    assert "xxxx" not in out + err
    assert "cli.parse" in out  # lines after the oversized one still parse


@pytest.mark.parametrize(
    ("total_bytes", "accepted"),
    [(2048, True), (2049, False)],
    ids=["at-limit", "over-limit"],
)
def test_line_bound_counts_tag_and_newline(tmp_path, capsys, total_bytes, accepted):
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    end["attrs"] = {"pad": ""}
    base = len(tagged(end).encode("utf-8")) + 1
    end["attrs"] = {"pad": "x" * (total_bytes - base)}
    line = tagged(end)
    assert len(line.encode("utf-8")) + 1 == total_bytes

    code, out, _ = run_report(capsys, write_lines(tmp_path, [tagged(start), line]))

    assert ("cli.parse" in out) is accepted
    assert ("malformed=1" in out) is not accepted
    assert code == (0 if accepted else 1)


@pytest.mark.parametrize("payload", ["[" * 1000 + "]" * 1000, "{" * 1500])
def test_pathological_nesting_is_malformed_without_crashing(tmp_path, capsys, payload):
    code, out, err = run_report(capsys, write_lines(tmp_path, [TAG + payload]))

    assert code == 2  # no usable event, reported cleanly
    assert "no usable v1 boot trace events" in err
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (2, "unknown_version=1"),
        (0, "unknown_version=1"),
        ("1", "malformed=1"),
        (True, "malformed=1"),
        (1.0, "malformed=1"),
        (MISSING, "malformed=1"),
    ],
    ids=["v2", "v0", "string", "bool", "float", "missing"],
)
def test_schema_version_must_be_integer_one(tmp_path, capsys, version, expected):
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    other = record("start", "cli.other", "9", seq=2)
    if version is MISSING:
        del other["v"]
    else:
        other["v"] = version
    lines = [tagged(start), tagged(other), tagged(end)]
    code, out, _ = run_report(capsys, write_lines(tmp_path, lines))

    assert code == 1
    assert expected in out
    assert "cli.parse" in out
    assert "cli.other" not in out


@pytest.mark.parametrize(
    ("token", "accepted"),
    [
        ("0", True),
        ("1.5", True),
        ("9007199254740991", True),
        ("-1", False),
        ("9007199254740992", False),
        ("true", False),
        ('"5"', False),
        ("null", False),
        ("NaN", False),
        ("Infinity", False),
        ("-Infinity", False),
        ("1e400", False),
    ],
    ids=[
        "zero",
        "fraction",
        "max-safe",
        "negative",
        "over-max-safe",
        "bool",
        "string",
        "null",
        "nan",
        "infinity",
        "neg-infinity",
        "overflow-to-inf",
    ],
)
def test_duration_must_be_finite_nonnegative_safe_number(
    tmp_path, capsys, token, accepted
):
    start = numbered(span_pair("cli.parse", 1.0, "1"))[0]
    end_line = (
        '{"v":1,"bootId":"%s","seq":2,"phase":"cli.parse","span":"1",'
        '"kind":"end","tMonoMs":1.0,"tWallMs":1,"durMs":%s,"attrs":{}}' % (BOOT, token)
    )
    lines = [tagged(start), TAG + end_line]
    code, out, _ = run_report(capsys, write_lines(tmp_path, lines))

    assert ("cli.parse" in out) is accepted
    assert ("malformed=1" in out) is not accepted
    assert code == (0 if accepted else 1)


@pytest.mark.parametrize(
    ("phase", "accepted"),
    [
        ("future.phase_x", True),
        ("Bad.Phase", False),
        ("cli.\u001bparse", False),
        ("a" * 65, False),
        ("1abc", False),
        ("", False),
        ("cli..parse", False),
    ],
    ids=[
        "unknown-valid",
        "uppercase",
        "escape",
        "too-long",
        "leading-digit",
        "empty",
        "double-dot",
    ],
)
def test_phase_must_be_dotted_lowercase_and_bounded(tmp_path, capsys, phase, accepted):
    anchor = span_pair("cli.parse", 1.0, "1")
    candidate = span_pair(phase, 4.0, "2")
    lines = [tagged(rec) for rec in numbered(anchor + candidate)]
    code, out, err = run_report(capsys, write_lines(tmp_path, lines))

    assert code == (0 if accepted else 1)
    assert ("4.000" in out) is accepted
    assert ("malformed=2" in out) is not accepted  # start and terminal both invalid
    assert "\x1b" not in out + err


@pytest.mark.parametrize(
    ("identity", "shown"),
    [
        ("acp", "acp"),
        ("my-plugin.v2_x", "my-plugin.v2_x"),
        ("h:0123456789abcdef", "h:0123456789abcdef"),
        ("x" * 64, "x" * 64),
        ("x" * 65, "invalid"),
        ("bad name", "invalid"),
        ("h:0123456789ABCDEF", "invalid"),
        ("h:0123", "invalid"),
        ("\u001b[31mred", "invalid"),
        ("\u00fcn\u00ef", "invalid"),
        (42, "invalid"),
    ],
    ids=[
        "official",
        "dotted",
        "hashed",
        "max-length",
        "too-long",
        "space",
        "uppercase-hash",
        "short-hash",
        "escape",
        "unicode",
        "not-a-string",
    ],
)
def test_plugin_identity_printed_only_when_it_matches_allowed_shapes(
    tmp_path, capsys, identity, shown
):
    attrs = {"tier": "builtin", "plugin": identity}
    start, end = numbered(span_pair("plugin.import", 2.0, "1", attrs=attrs))
    code, out, err = run_report(
        capsys, write_lines(tmp_path, [tagged(start), tagged(end)])
    )

    assert code == 0
    assert row_cells(report_row(out, shown))[1] == shown
    assert "\x1b" not in out + err
    assert str(identity) not in out or identity == shown


@pytest.mark.parametrize(
    ("tier", "shown"),
    [("project", "project"), ("weird", "?"), (3, "?"), (None, "?")],
    ids=["valid", "unknown-string", "number", "null"],
)
def test_tier_printed_only_from_known_enum(tmp_path, capsys, tier, shown):
    attrs = {"tier": tier, "plugin": "acp"}
    start, end = numbered(span_pair("plugin.import", 2.0, "1", attrs=attrs))
    _, out, _ = run_report(capsys, write_lines(tmp_path, [tagged(start), tagged(end)]))

    assert row_cells(report_row(out, "acp"))[0] == shown


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        ("remote", "ok outcome=remote"),
        ("bogus", "ok"),
        (7, "ok"),
        ("\u001b[2J", "ok"),
    ],
    ids=["valid", "unknown", "number", "escape"],
)
def test_outcome_shown_only_when_known(tmp_path, capsys, outcome, status):
    attrs = {"outcome": outcome}
    start, end = numbered(span_pair("catalog.load", 3.0, "1", attrs=attrs))
    _, out, err = run_report(
        capsys, write_lines(tmp_path, [tagged(start), tagged(end)])
    )

    assert "\x1b" not in out + err
    assert row_cells(report_row(out, "catalog.load"))[1] == status


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_crlf_and_lf_line_endings_both_parse(tmp_path, capsys, ending):
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    path = tmp_path / "trace.txt"
    path.write_bytes((tagged(start) + ending + tagged(end) + ending).encode("ascii"))

    code, out, _ = run_report(capsys, path)

    assert code == 0
    assert "cli.parse" in out


def test_untagged_jsonl_without_any_tag_parses(tmp_path, capsys):
    start, end = numbered(span_pair("cli.parse", 1.0, "1"))
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [encode(start), encode(end)])
    )

    assert code == 0
    assert "cli.parse" in out


def test_unreadable_input_reports_fixed_message_without_path(tmp_path, capsys):
    missing = tmp_path / "secret-dir-name" / "trace.jsonl"
    code, out, err = run_report(capsys, missing)

    assert code == 2
    assert "cannot read input" in err
    assert "secret-dir-name" not in out + err


def test_empty_input_is_an_invocation_error(tmp_path, capsys):
    code, out, err = run_report(capsys, write_lines(tmp_path, [""]))

    assert code == 2
    assert "no usable v1 boot trace events" in err
    assert out == ""


def test_script_imports_nothing_from_code_puppy():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    assert not [name for name in names if name.split(".")[0] == "code_puppy"]
