"""Tests for boot-trace plugin identity, registry, end-to-end file sink and clocks."""

import json
import textwrap

import pytest

import code_puppy.boot_trace as bt
from tests.boot_trace_support import (
    EXTRA_NAMES,
    SUBPROCESS_TIMEOUT_S,
    HASHED,
    HEX32,
    OFFICIAL,
    _run_py,
    make_clock,
    traced_loader,
)


@pytest.fixture
def clock(monkeypatch):
    return make_clock(monkeypatch)


@pytest.fixture
def traced(clock):
    yield from traced_loader()


# --- plugin identity -----------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "name"),
    [("installed", "ollama"), ("builtin", "acp"), ("installed", "yolo_cli")],
)
def test_official_name_on_installed_or_builtin_is_plain(traced, tier, name):
    traced()
    assert bt.plugin_attrs(tier, name) == {"tier": tier, "plugin": name}


@pytest.mark.parametrize(
    ("tier", "name"),
    [
        ("user", "ollama"),
        ("project", "ollama"),
        ("installed", "unknown_plugin"),
        ("builtin", "unknown_plugin"),
        ("user", "my/private path"),
    ],
)
def test_identity_is_hashed_unless_official_on_installed_or_builtin(traced, tier, name):
    traced()
    attrs = bt.plugin_attrs(tier, name)
    assert (
        attrs["tier"],
        bool(HASHED.fullmatch(attrs["plugin"])),
        name in attrs["plugin"],
    ) == (tier, True, False)


@pytest.mark.parametrize(
    ("tier", "name"),
    [("bogus", "ollama"), ("installed", 5), (None, "ollama"), ("installed", None)],
)
def test_invalid_plugin_attrs_inputs_return_empty(traced, tier, name):
    traced()
    assert bt.plugin_attrs(tier, name) == {}


def test_hash_is_stable_per_tier_and_name_and_differs_across_tiers(traced):
    traced()
    first = bt.plugin_attrs("user", "ollama")
    assert (
        first == bt.plugin_attrs("user", "ollama"),
        first["plugin"] != bt.plugin_attrs("project", "ollama")["plugin"],
        first["plugin"] != bt.plugin_attrs("user", "acp")["plugin"],
    ) == (True, True, True)


PLUGIN_CHILD = textwrap.dedent(
    """
    import json
    from code_puppy import boot_trace as bt
    print(json.dumps(bt.plugin_attrs("user", "ollama")))
    """
)


def test_hash_differs_between_processes(tmp_path):
    runs = []
    for index in range(2):
        target = str(tmp_path / f"trace-{index}.jsonl")
        result = _run_py(PLUGIN_CHILD, target, tmp_path)
        assert result.returncode == 0
        runs.append(json.loads(result.stdout))
    assert (
        runs[0]["plugin"] != runs[1]["plugin"],
        [r["tier"] for r in runs],
        all(HASHED.fullmatch(r["plugin"]) for r in runs),
    ) == (True, ["user", "user"], True)


def test_initial_registry_is_the_seventy_official_names(traced):
    traced()
    installed = [bt.plugin_attrs("installed", n)["plugin"] for n in OFFICIAL]
    builtin = [bt.plugin_attrs("builtin", n)["plugin"] for n in OFFICIAL]
    user = [bt.plugin_attrs("user", n)["plugin"] for n in OFFICIAL]
    assert (
        len(OFFICIAL),
        installed == list(OFFICIAL),
        builtin == list(OFFICIAL),
        all(HASHED.fullmatch(p) for p in user),
    ) == (70, True, True, True)


def test_extra_plugins_turn_plain_only_after_registration(traced):
    traced()
    before = [bt.plugin_attrs("installed", n)["plugin"] for n in EXTRA_NAMES]
    bt.register_plugin_names(EXTRA_NAMES)
    after = [bt.plugin_attrs("installed", n)["plugin"] for n in EXTRA_NAMES]
    assert (
        [bool(HASHED.fullmatch(p)) for p in before],
        after,
    ) == ([True] * 18, list(EXTRA_NAMES))


@pytest.mark.parametrize(
    ("container", "name", "accepted"),
    [
        pytest.param(("t_tuple",), "t_tuple", True, id="tuple"),
        pytest.param(["l_list"], "l_list", True, id="list"),
        pytest.param({"s_set"}, "s_set", True, id="set"),
        pytest.param(frozenset({"f_fset"}), "f_fset", True, id="frozenset"),
        pytest.param("str_name", "str_name", False, id="bare-string"),
        pytest.param({"d_dict": 1}, "d_dict", False, id="dict"),
        pytest.param(("has space",), "has space", False, id="space"),
        pytest.param(("",), "", False, id="empty"),
        pytest.param(("x" * 65,), "x" * 65, False, id="too-long"),
        pytest.param(("a:b",), "a:b", False, id="colon"),
        pytest.param(("x" * 64,), "x" * 64, True, id="max-length"),
    ],
)
def test_register_accepts_only_valid_containers_and_names(
    traced, container, name, accepted
):
    traced()
    bt.register_plugin_names(container)
    assert (bt.plugin_attrs("installed", name)["plugin"] == name) == accepted


def test_registry_cap_is_128_including_official(traced):
    traced()
    new = [f"new_{i:03d}" for i in range(70)]
    bt.register_plugin_names(tuple(new))
    shape = [
        "plain" if bt.plugin_attrs("installed", n)["plugin"] == n else "hashed"
        for n in new
    ]
    assert (shape, bt.plugin_attrs("user", "new_000")["plugin"] == "new_000") == (
        ["plain"] * 58 + ["hashed"] * 12,
        False,
    )


# --- real subprocess end to end --------------------------------------------------

E2E_CHILD = textwrap.dedent(
    """
    import sys, threading, time
    from pathlib import Path
    from code_puppy import boot_trace as bt

    bt.begin_boot()
    with bt.span("a.step", attrs={"tier": "builtin", "plugin": "ollama"}) as step:
        step.update(count=2)
    bt.end_boot()

    trace = Path(sys.argv[1])

    def line_count():
        try:
            return trace.read_bytes().count(b"\\n")
        except FileNotFoundError:
            return 0  # the writer thread creates the file asynchronously

    pause = threading.Event()
    deadline = time.monotonic() + float(sys.argv[2])
    while line_count() < 5:
        assert time.monotonic() < deadline, "trace never reached 5 lines"
        pause.wait(0.005)
    """
)


def test_file_target_end_to_end_in_subprocess(tmp_path):
    trace = tmp_path / "boot.jsonl"
    result = _run_py(
        E2E_CHILD, str(trace), tmp_path, str(trace), str(SUBPROCESS_TIMEOUT_S)
    )
    lines = [
        json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()
    ]
    boot = lines[0]["bootId"]
    shaped = [
        {k: v for k, v in line.items() if k not in ("tMonoMs", "tWallMs", "durMs")}
        for line in lines
    ]
    durations_ok = all(line["durMs"] >= 0 for line in lines if "durMs" in line)
    expected = [
        {
            "v": 1,
            "bootId": boot,
            "seq": 1,
            "phase": "boot",
            "span": "1",
            "kind": "start",
            "attrs": {},
        },
        {
            "v": 1,
            "bootId": boot,
            "seq": 2,
            "phase": "py.main_reached",
            "span": "2",
            "parent": "1",
            "kind": "mark",
            "attrs": {},
        },
        {
            "v": 1,
            "bootId": boot,
            "seq": 3,
            "phase": "a.step",
            "span": "3",
            "parent": "1",
            "kind": "start",
            "attrs": {"tier": "builtin", "plugin": "ollama"},
        },
        {
            "v": 1,
            "bootId": boot,
            "seq": 4,
            "phase": "a.step",
            "span": "3",
            "parent": "1",
            "kind": "end",
            "attrs": {"tier": "builtin", "plugin": "ollama", "count": 2},
        },
        {
            "v": 1,
            "bootId": boot,
            "seq": 5,
            "phase": "boot",
            "span": "1",
            "kind": "end",
            "attrs": {},
        },
    ]
    assert (result.returncode, bool(HEX32.fullmatch(boot)), shaped, durations_ok) == (
        0,
        True,
        expected,
        True,
    )


# --- clock -----------------------------------------------------------------------


def test_duration_uses_monotonic_clock_not_wall_clock(traced, clock):
    sink = traced()
    clock.mono += 10_000_000
    wall_start = clock.wall
    with bt.span("t.clock"):
        clock.mono += 250_000_000
        clock.wall -= 3_600 * 1_000_000_000
    assert [
        (e["kind"], e["tMonoMs"], e["tWallMs"], e.get("durMs")) for e in sink.events
    ] == [
        ("start", 10.0, wall_start // 1_000_000, None),
        ("end", 260.0, (wall_start - 3_600 * 1_000_000_000) // 1_000_000, 250.0),
    ]
