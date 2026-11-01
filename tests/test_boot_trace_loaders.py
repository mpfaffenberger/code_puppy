"""Boot-trace instrumentation of the central plugin loaders (all four tiers)."""

import importlib
import sys
from pathlib import Path

import pytest

import code_puppy.boot_trace as bt
from code_puppy import plugins
from tests.boot_trace_support import make_clock, traced_loader

PLUGIN_PREFIXES = ("b_", "u_", "ollama", "project_plugins.p_")
EXPECTED_LOADED = {
    "builtin": ["ollama", "z_installed", "b_ok"],
    "user": ["u_ok", "u_pkg"],
    "project": ["p_ok"],
}


class FakeEntryPoint:
    def __init__(self, name, error=None):
        self.name, self._error = name, error

    def load(self):
        if self._error is not None:
            raise self._error


def _write(path: Path, source: str = "LOADED = True\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _marker_source(marker: Path) -> str:
    return f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"


@pytest.fixture
def traced(monkeypatch):
    make_clock(monkeypatch)
    yield from traced_loader()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Every tier populated with success, caught-error, skip and refusal cases."""
    markers = {name: tmp_path / f"{name}.ran" for name in ("super", "untrusted", "off")}

    builtin = tmp_path / "builtin"
    for name in ("b_ok", "b_bad", "z_installed"):
        _write(builtin / name / "register_callbacks.py")
    (builtin / "b_nocb").mkdir()
    _write(builtin / "_private" / "register_callbacks.py")
    _write(builtin / "__init__.py", "")

    user = tmp_path / "user"
    _write(user / "u_ok" / "register_callbacks.py")
    _write(user / "u_bad" / "register_callbacks.py", "raise RuntimeError('boom')\n")
    # official name, but already loaded by an earlier tier: skipped, never executed
    _write(user / "ollama" / "register_callbacks.py", _marker_source(markers["super"]))
    _write(user / "u_pkg" / "__init__.py")

    project = tmp_path / "proj" / ".code_puppy" / "plugins"
    _write(project / "p_ok" / "register_callbacks.py")
    _write(project / "p_imp" / "register_callbacks.py", "raise ImportError('nope')\n")
    _write(project / "p_rt" / "register_callbacks.py", "raise RuntimeError('boom')\n")
    _write(project / "p_off" / "register_callbacks.py", _marker_source(markers["off"]))
    _write(
        project / "p_untrusted" / "register_callbacks.py",
        _marker_source(markers["untrusted"]),
    )
    _write(project / "p_pyc" / "register_callbacks.py")
    _write(project / "p_pyc" / "__pycache__" / "x.pyc", "")

    entry_points = [
        FakeEntryPoint("z_installed"),
        FakeEntryPoint("token_ratio_learner"),
        FakeEntryPoint("ollama"),
        FakeEntryPoint("a_broken", ImportError("gone")),
    ]
    real_import = importlib.import_module

    def fake_import(name, package=None):
        if name.startswith("code_puppy.plugins.b_"):
            if name.split(".")[2] == "b_bad":
                raise ImportError("gone")
            return None
        return real_import(name, package)

    logged = []
    monkeypatch.setattr(plugins, "_PLUGINS_LOADED", False)
    monkeypatch.setattr(plugins, "_loaded_plugin_names", {})
    monkeypatch.setattr(plugins, "_project_plugin_status", {})
    monkeypatch.setattr(plugins, "__file__", str(builtin / "__init__.py"))
    monkeypatch.setattr(plugins, "entry_points", lambda group: entry_points)
    monkeypatch.setattr(plugins, "USER_PLUGINS_DIR", user)
    monkeypatch.setattr(plugins, "get_project_plugins_directory", lambda: project)
    monkeypatch.setattr(plugins, "log_error", lambda exc, **_: logged.append(exc))
    monkeypatch.setattr(plugins.importlib, "import_module", fake_import)
    monkeypatch.setattr(
        plugins._trust,
        "get_trust_status",
        lambda _root, name, _dir: (
            "untrusted" if name == "p_untrusted" else plugins._trust.TRUSTED
        ),
    )
    monkeypatch.setattr(
        plugins._trust, "is_plugin_trusted", lambda _r, name, _d: name != "p_untrusted"
    )
    monkeypatch.setattr(
        "code_puppy.plugins.config.is_plugin_disabled", lambda name: name == "p_off"
    )
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = set(sys.modules)
    yield {"markers": markers, "logged": logged, "builtin": builtin, "user": user}
    for name in set(sys.modules) - before:
        if name.startswith(PLUGIN_PREFIXES):
            del sys.modules[name]


def _rows(sink):
    """Non-root events as (phase, kind, parent phase, attrs, unit, reason)."""
    phase_of = {e["span"]: e["phase"] for e in sink.events}
    rows = []
    for e in sink.events:
        if e["phase"] in ("boot", "py.main_reached"):
            continue
        unit = e.get("unit")
        rows.append(
            (
                e["phase"],
                e["kind"],
                phase_of.get(e.get("parent")),
                e["attrs"],
                (unit["n"], unit["of"]) if unit else None,
                e.get("reason"),
            )
        )
    return rows


def _plugin_row(tier, name, kind, parent, ordinal=None, total=None, **extra):
    attrs = {**bt.plugin_attrs(tier, name), **extra}
    unit = None if total is None else (ordinal, total)
    reason = "disabled" if kind == "skip" else None
    return ("plugin.import", kind, parent, attrs, unit, reason)


def test_full_load_reports_every_tier_in_order(traced, world):
    sink = traced()
    bt.begin_boot()
    result = plugins.load_plugin_callbacks()
    load, inst, bltn, usr, proj = (
        "plugins.load",
        "plugins.tier.installed",
        "plugins.tier.builtin",
        "plugins.tier.user",
        "plugins.tier.project",
    )

    def plug(tier, name, parent, kind="end", n=None, of=None, **extra):
        return _plugin_row(tier, name, kind, parent, n, of, **extra)

    err = {"outcome": "error", "exceptionClass": "ImportError"}
    assert (result, _rows(sink)) == (
        EXPECTED_LOADED,
        [
            (load, "start", "boot", {}, None, None),
            (inst, "start", load, {}, (0, 4), None),
            # entry points are sorted by name, as before tracing existed
            plug("installed", "a_broken", inst, "start", 1, 4),
            plug("installed", "a_broken", inst, "error", 1, 4, **err),
            plug("installed", "ollama", inst, "start", 2, 4),
            plug("installed", "ollama", inst, "end", 2, 4),
            plug("installed", "token_ratio_learner", inst, "start", 3, 4),
            plug("installed", "token_ratio_learner", inst, "skip", 3, 4),
            plug("installed", "z_installed", inst, "start", 4, 4),
            plug("installed", "z_installed", inst, "end", 4, 4),
            (inst, "end", load, {"count": 2}, (4, 4), None),
            # z_installed was loaded by the installed tier: not a candidate here
            (bltn, "start", load, {}, (0, 2), None),
            plug("builtin", "b_bad", bltn, "start", 1, 2),
            plug("builtin", "b_bad", bltn, "error", 1, 2, **err),
            plug("builtin", "b_ok", bltn, "start", 2, 2),
            plug("builtin", "b_ok", bltn, "end", 2, 2),
            (bltn, "end", load, {"count": 1}, (2, 2), None),
        ]
        + _user_rows(usr, load)
        + _project_rows(proj, load),
    )


def _user_rows(usr, load):
    err = {"outcome": "error", "exceptionClass": "RuntimeError"}
    return [
        (usr, "start", load, {}, None, None),
        _plugin_row("user", "ollama", "start", usr),
        _plugin_row("user", "ollama", "skip", usr),
        _plugin_row("user", "u_bad", "start", usr),
        _plugin_row("user", "u_bad", "error", usr, **err),
        _plugin_row("user", "u_ok", "start", usr),
        _plugin_row("user", "u_ok", "end", usr),
        _plugin_row("user", "u_pkg", "start", usr),
        _plugin_row("user", "u_pkg", "end", usr),
        (usr, "end", load, {"count": 2}, None, None),
    ]


def _project_rows(proj, load):
    def plug(name, kind, **extra):
        return _plugin_row("project", name, kind, proj, **extra)

    return [
        (proj, "start", load, {}, None, None),
        plug("p_imp", "start"),
        plug("p_imp", "error", outcome="error", exceptionClass="ImportError"),
        plug("p_off", "start"),
        plug("p_off", "skip"),
        plug("p_ok", "start"),
        plug("p_ok", "end"),
        plug("p_pyc", "start"),
        plug("p_pyc", "skip"),
        plug("p_rt", "start"),
        plug("p_rt", "error", outcome="error", exceptionClass="RuntimeError"),
        plug("p_untrusted", "start"),
        plug("p_untrusted", "skip"),
        (proj, "end", load, {"count": 1}, None, None),
        ("plugins.load", "end", "boot", {}, None, None),
    ]


def test_user_names_are_salted_even_when_official(traced, world):
    sink = traced()
    plugins._load_user_plugins(world["user"])
    imports = [e for e in sink.events if e["phase"] == "plugin.import"]
    assert {e["attrs"]["plugin"][:2] for e in imports} == {"h:"}


@pytest.mark.parametrize("enabled", [True, False], ids=["tracing-on", "tracing-off"])
def test_loader_behavior_is_identical_with_tracing_on_or_off(traced, world, enabled):
    sink = traced() if enabled else traced(None)
    result = plugins.load_plugin_callbacks()
    ran = {name: path.exists() for name, path in world["markers"].items()}
    assert (
        result,
        ran,
        dict(plugins._project_plugin_status),
        [type(exc).__name__ for exc in world["logged"]],
        sink is not None,
    ) == (
        EXPECTED_LOADED,
        {"super": False, "untrusted": False, "off": False},
        {
            "p_untrusted": "untrusted",
            "p_off": "disabled",
            "p_ok": "loaded",
            "p_imp": "error",
            "p_rt": "error",
            "p_pyc": "error",
        },
        # one caught failure per bad plugin, logged once each
        ["ImportError", "ImportError", "RuntimeError", "ImportError", "RuntimeError"],
        enabled,
    )


def test_disabled_tracing_adds_no_directory_scans(traced, world, monkeypatch):
    traced(None)
    calls = {"iterdir": [], "exists": 0}
    real_iterdir, real_exists = Path.iterdir, Path.exists

    def counting_iterdir(self):
        calls["iterdir"].append(self)
        return real_iterdir(self)

    def counting_exists(self, *args, **kwargs):
        calls["exists"] += 1
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", counting_iterdir)
    monkeypatch.setattr(Path, "exists", counting_exists)
    plugins._load_builtin_plugins(world["builtin"], {"z_installed"})
    # b_ok, b_bad and b_nocb are probed once each; z_installed is skipped first
    assert (calls["iterdir"], calls["exists"]) == ([world["builtin"]], 3)


def test_second_load_is_a_cached_skip_with_unchanged_return(traced, world):
    sink = traced()
    plugins.load_plugin_callbacks()
    first_count = len(_rows(sink))
    second = plugins.load_plugin_callbacks()
    new = _rows(sink)[first_count:]
    assert (second, new) == (
        {"builtin": [], "user": [], "project": []},
        [
            ("plugins.load", "start", None, {}, None, None),
            ("plugins.load", "skip", None, {}, None, "cached"),
        ],
    )


def test_missing_user_and_project_dirs_skip_without_inventing_totals(
    traced, world, monkeypatch, tmp_path
):
    sink = traced()
    monkeypatch.setattr(plugins, "entry_points", lambda group: [])
    monkeypatch.setattr(plugins, "USER_PLUGINS_DIR", tmp_path / "absent")
    monkeypatch.setattr(plugins, "get_project_plugins_directory", lambda: None)
    plugins.load_plugin_callbacks()
    skips = [r for r in _rows(sink) if r[1] == "skip"]
    assert skips == [
        (
            "plugins.tier.user",
            "skip",
            "plugins.load",
            {"count": 0},
            None,
            "not_installed",
        ),
        (
            "plugins.tier.project",
            "skip",
            "plugins.load",
            {"count": 0},
            None,
            "not_installed",
        ),
    ]


def test_user_path_that_is_a_file_is_a_not_installed_skip(traced, world, tmp_path):
    sink = traced()
    not_a_dir = _write(tmp_path / "plain-file")
    assert (plugins._load_user_tier(not_a_dir, set()), _rows(sink)) == (
        [],
        [
            ("plugins.tier.user", "start", None, {}, None, None),
            ("plugins.tier.user", "skip", None, {"count": 0}, None, "not_installed"),
        ],
    )


def test_memory_error_propagates_and_closes_every_enclosing_span_as_error(
    traced, world, monkeypatch
):
    sink = traced()
    monkeypatch.setattr(
        plugins, "entry_points", lambda group: [FakeEntryPoint("ollama", MemoryError())]
    )
    with pytest.raises(MemoryError):
        plugins.load_plugin_callbacks()
    terminals = [(r[0], r[1]) for r in _rows(sink) if r[1] != "start"]
    assert (terminals, plugins._PLUGINS_LOADED) == (
        [
            ("plugin.import", "error"),
            ("plugins.tier.installed", "error"),
            ("plugins.load", "error"),
        ],
        False,
    )
