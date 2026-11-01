"""Ranking, pairing, boot selection, and exit codes for scripts/boot_trace_report.py."""

import io
import subprocess
import sys

import pytest

from tests.boot_trace_support import SUBPROCESS_TIMEOUT_S
from tests.test_boot_trace_report_input import (
    REPORT,
    SCRIPT,
    numbered,
    record,
    row_cells,
    run_report,
    span_pair,
    tagged,
    write_lines,
)

# Verbatim lines captured from code_puppy/boot_trace.py's file sink (not hand-built).
REAL_RECORDER_LINES = [
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":1,"phase":"boot","span":"1","kind":"start","tMonoMs":0.114,"tWallMs":1793497899599,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":2,"phase":"py.main_reached","span":"2","parent":"1","kind":"mark","tMonoMs":0.13,"tWallMs":1793497899599,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":3,"phase":"cli.parse","span":"3","parent":"1","kind":"start","tMonoMs":0.141,"tWallMs":1793497899599,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":4,"phase":"cli.argparse","span":"4","parent":"3","kind":"start","tMonoMs":0.15,"tWallMs":1793497899599,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":5,"phase":"cli.argparse","span":"4","parent":"3","kind":"end","tMonoMs":0.154,"tWallMs":1793497899599,"durMs":0.004,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":6,"phase":"cli.parse","span":"3","parent":"1","kind":"end","tMonoMs":0.158,"tWallMs":1793497899599,"durMs":0.017,"attrs":{}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":7,"phase":"plugin.import","span":"5","parent":"1","kind":"start","tMonoMs":0.166,"tWallMs":1793497899599,"attrs":{"tier":"builtin","plugin":"acp"}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":8,"phase":"plugin.import","span":"5","parent":"1","kind":"end","tMonoMs":0.168,"tWallMs":1793497899599,"durMs":0.002,"attrs":{"tier":"builtin","plugin":"acp"}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":9,"phase":"plugin.import","span":"6","parent":"1","kind":"start","tMonoMs":0.482,"tWallMs":1793497899599,"attrs":{"tier":"user","plugin":"h:01df1412162713fa"}}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":10,"phase":"plugin.import","span":"6","parent":"1","kind":"skip","tMonoMs":0.49,"tWallMs":1793497899599,"durMs":0.008,"attrs":{"tier":"user","plugin":"h:01df1412162713fa"},"reason":"disabled"}',
    '{"v":1,"bootId":"3496aaae560e4f009a930fe6c1c66870","seq":11,"phase":"boot","span":"1","kind":"end","tMonoMs":0.494,"tWallMs":1793497899599,"durMs":0.379,"attrs":{}}',
]
OTHER_BOOT = "cd" * 16


def section_rows(out, title):
    """Return each data row under the section ``title`` as a tuple of cells."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(title))
    rows = []
    for line in lines[start + 2 :]:
        if not line.strip():
            break
        rows.append(tuple(row_cells(line)))
    return rows


def phase_labels(out):
    return [row[2] for row in section_rows(out, "Phases") if len(row) == 3]


def in_boot(records, boot):
    for rec in records:
        rec["bootId"] = boot
    return records


def test_phases_rank_by_duration_then_start_order(tmp_path, capsys):
    records = numbered(
        span_pair("cli.fast", 1.0, "1")
        + span_pair("cli.tie_first", 4.0, "2")
        + span_pair("cli.tie_second", 4.0, "3")
        + span_pair("cli.slow", 9.0, "4")
    )
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 0
    assert phase_labels(out) == [
        "cli.slow",
        "cli.tie_first",
        "cli.tie_second",
        "cli.fast",
    ]


@pytest.mark.parametrize(
    ("kind", "attrs", "status"),
    [
        ("end", {}, "ok"),
        ("end", {"outcome": "remote"}, "ok outcome=remote"),
        ("error", {}, "error"),
        ("error", {"outcome": "timeout"}, "error outcome=timeout"),
    ],
    ids=["ok", "ok-with-outcome", "error", "error-with-outcome"],
)
def test_terminal_kind_and_valid_outcome_form_the_status(
    tmp_path, capsys, kind, attrs, status
):
    records = numbered(span_pair("cli.parse", 2.0, "1", kind=kind, attrs=attrs))
    _, out, _ = run_report(capsys, write_lines(tmp_path, [tagged(r) for r in records]))

    assert section_rows(out, "Phases") == [("2.000", status, "cli.parse")]


def test_plugin_rows_list_identity_and_skips_stay_unranked(tmp_path, capsys):
    records = numbered(
        span_pair("plugin.import", 2.0, "1", attrs={"tier": "builtin", "plugin": "acp"})
        + span_pair(
            "plugin.import",
            5.0,
            "2",
            attrs={"tier": "user", "plugin": "h:0123456789abcdef"},
        )
        + span_pair(
            "plugin.import",
            1.0,
            "3",
            kind="error",
            attrs={"tier": "project", "plugin": "proj-x", "outcome": "error"},
        )
        + span_pair(
            "plugin.import",
            99.0,
            "4",
            kind="skip",
            attrs={"tier": "project", "plugin": "proj-y"},
        )
        + span_pair("cli.parse", 3.0, "5")
    )
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 0
    assert section_rows(out, "Plugins") == [
        ("user", "h:0123456789abcdef", "5.000", "ok"),
        ("builtin", "acp", "2.000", "ok"),
        ("project", "proj-x", "1.000", "error outcome=error"),
    ]
    assert phase_labels(out) == ["cli.parse"]
    assert "skipped spans (not ranked): 1" in out
    assert "proj-y" not in out
    assert "99.000" not in out


def test_lifetime_phases_carry_the_not_boot_ready_label(tmp_path, capsys):
    records = numbered(
        span_pair("boot", 500.0, "1")
        + span_pair("cli.handle_args", 400.0, "2")
        + span_pair("cli.parse", 3.0, "3")
    )
    _, out, _ = run_report(capsys, write_lines(tmp_path, [tagged(r) for r in records]))

    assert phase_labels(out) == [
        f"boot {REPORT.LIFETIME_LABEL}",
        f"cli.handle_args {REPORT.LIFETIME_LABEL}",
        "cli.parse",
    ]


@pytest.mark.parametrize(
    ("extra_args", "expected_rows"),
    [([], 20), (["--top", "3"], 3), (["--top", "25"], 25)],
    ids=["default-20", "explicit-3", "explicit-25"],
)
def test_top_limits_rows_per_section(tmp_path, capsys, extra_args, expected_rows):
    spans = []
    for i in range(25):
        spans += span_pair(f"p.s{i:02d}", float(i), format(i + 1, "x"))
    path = write_lines(tmp_path, [tagged(r) for r in numbered(spans)])
    _, out, _ = run_report(capsys, path, *extra_args)

    labels = phase_labels(out)
    assert len(labels) == expected_rows
    assert labels == [f"p.s{i:02d}" for i in range(24, 24 - expected_rows, -1)]


@pytest.mark.parametrize("value", ["0", "-1", "abc"], ids=["zero", "negative", "text"])
def test_top_must_be_a_positive_integer(tmp_path, capsys, value):
    path = write_lines(
        tmp_path, [tagged(r) for r in numbered(span_pair("p", 1.0, "1"))]
    )
    with pytest.raises(SystemExit) as exc:
        REPORT.main([str(path), "--top", value])

    assert exc.value.code == 2
    assert "must be a positive integer" in capsys.readouterr().err


def test_multiple_boots_require_boot_id_and_never_mix(tmp_path, capsys):
    boot_a, boot_b = "aa" * 16, "bb" * 16
    records = in_boot(numbered(span_pair("a.only", 1.0, "1")), boot_a)
    records += in_boot(numbered(span_pair("b.only", 2.0, "1")), boot_b)
    path = write_lines(tmp_path, [tagged(r) for r in records])

    code, out, err = run_report(capsys, path)
    assert code == 2
    assert out == ""
    assert boot_a[:32] in err and boot_b[:32] in err
    assert "only" not in err

    code, out, _ = run_report(capsys, path, "--boot-id", boot_a)
    assert code == 0
    assert "a.only" in out and "b.only" not in out

    code, out, _ = run_report(capsys, path, "--boot-id", boot_b)
    assert code == 0
    assert "b.only" in out and "a.only" not in out


def test_unknown_boot_id_is_an_invocation_error_without_echo(tmp_path, capsys):
    path = write_lines(
        tmp_path, [tagged(r) for r in numbered(span_pair("p", 1.0, "1"))]
    )
    code, out, err = run_report(capsys, path, "--boot-id", OTHER_BOOT)

    assert code == 2
    assert "boot id not found" in err
    assert OTHER_BOOT not in out + err


def test_candidate_boot_ids_are_capped_at_thirty_two_characters(tmp_path, capsys):
    first, second = "a" * 40 + "1" * 24, "a" * 40 + "2" * 24
    records = in_boot(numbered(span_pair("x.one", 1.0, "1")), first)
    records += in_boot(numbered(span_pair("x.two", 1.0, "1")), second)
    code, _, err = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 2
    assert "a" * 32 in err
    assert "a" * 33 not in err


def _start(span, parent=None):
    return record("start", "cli.parse", span, parent=parent)


def _end(span, parent=None):
    return record("end", "cli.parse", span, dur=1.0, parent=parent)


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        (numbered([_start("1"), _start("1"), _end("1")]), "inconsistent=1"),
        (numbered([_end("9")]), "inconsistent=1"),
        (
            numbered([_start("1"), record("end", "cli.other", "1", dur=1.0)]),
            "inconsistent=1",
        ),
        (numbered([_start("2", parent="1"), _end("2")]), "inconsistent=1"),
        (numbered([_start("1"), _end("1"), _end("1")]), "inconsistent=1"),
        (numbered([_start("1")]), "unmatched_starts=1"),
        (numbered([_start("1"), _start("2"), _end("2")]), "unmatched_starts=1"),
        (
            numbered([_start("1"), _end("1")]) + [record("mark", "x.y", "f", seq=2)],
            "inconsistent=1",
        ),
        (
            numbered(
                span_pair("cli.parse", 1.0, "1")
                + [record("mark", "boot.dropped", "f", dropped=3)]
            ),
            "dropped_events=3",
        ),
    ],
    ids=[
        "duplicate-start",
        "terminal-without-start",
        "phase-mismatch",
        "parent-mismatch",
        "duplicate-terminal",
        "missing-end",
        "sibling-missing-end",
        "duplicate-seq",
        "drop-mark",
    ],
)
def test_span_inconsistencies_mark_the_trace_incomplete(
    tmp_path, capsys, records, expected
):
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 1
    assert "INCOMPLETE" in out
    assert expected in out


def test_lost_line_leaves_a_sequence_gap(tmp_path, capsys):
    records = numbered(span_pair("cli.a", 1.0, "1") + span_pair("cli.b", 2.0, "2"))
    del records[1]  # lose cli.a's terminal; seq 2 is never seen
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 1
    assert "seq_gaps=1" in out
    assert "unmatched_starts=1" in out


def test_missing_first_event_is_a_sequence_gap(tmp_path, capsys):
    records = numbered(span_pair("cli.parse", 1.0, "1"), start=2)
    code, out, _ = run_report(
        capsys, write_lines(tmp_path, [tagged(r) for r in records])
    )

    assert code == 1
    assert "seq_gaps=1" in out


def test_out_of_order_lines_without_loss_are_complete(tmp_path, capsys):
    records = numbered(span_pair("cli.a", 1.0, "1") + span_pair("cli.b", 2.0, "2"))
    lines = [tagged(r) for r in reversed(records)]
    code, out, _ = run_report(capsys, write_lines(tmp_path, lines))

    assert code == 0
    assert "INCOMPLETE" not in out
    assert phase_labels(out) == ["cli.b", "cli.a"]


def test_real_recorder_lines_produce_the_expected_report(tmp_path, capsys):
    code, out, _ = run_report(capsys, write_lines(tmp_path, REAL_RECORDER_LINES))

    assert code == 0
    assert phase_labels(out) == [
        f"boot {REPORT.LIFETIME_LABEL}",
        "cli.parse",
        "cli.argparse",
    ]
    assert section_rows(out, "Plugins") == [("builtin", "acp", "0.002", "ok")]
    assert "skipped spans (not ranked): 1" in out
    assert "h:01df1412162713fa" not in out


def test_stdin_dash_reads_standard_input(monkeypatch, capsys):
    payload = "\n".join(tagged(r) for r in numbered(span_pair("cli.parse", 1.0, "1")))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode())))

    code, out, _ = run_report(capsys, "-")

    assert code == 0
    assert "cli.parse" in out


COMPLETE = [tagged(r) for r in numbered(span_pair("cli.parse", 1.0, "1"))]
INCOMPLETE = [tagged(numbered([record("start", "cli.parse", "1")])[0])]
MULTI_BOOT = [
    tagged(r) for r in in_boot(numbered(span_pair("a.one", 1.0, "1")), "aa" * 16)
] + [tagged(r) for r in in_boot(numbered(span_pair("b.one", 1.0, "1")), "bb" * 16)]


@pytest.mark.parametrize(
    ("lines", "expected_code"),
    [(COMPLETE, 0), (INCOMPLETE, 1), ([""], 2), (MULTI_BOOT, 2)],
    ids=["complete", "incomplete", "no-usable-events", "multi-boot-no-flag"],
)
def test_script_entry_point_exit_codes(tmp_path, lines, expected_code):
    path = write_lines(tmp_path, lines)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )

    assert result.returncode == expected_code
