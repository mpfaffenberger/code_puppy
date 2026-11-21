"""Tests for sbx/wizard.py (stdlib-only script, imported by path)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

WIZARD_PATH = Path(__file__).resolve().parents[1] / "sbx" / "wizard.py"
PLAN_CMD = ["code-puppy", "--setup", "sbx", "plan", "--json"]


@pytest.fixture
def wizard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("sbx_wizard", WIZARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OWNED_FILE", tmp_path / "owned-secrets.json")
    bindings = tmp_path / "credentials.yaml"
    monkeypatch.setattr(module, "bindings_path", lambda: bindings)
    return module


class FakeRun:
    """Records ``run`` calls; ``fail`` lists names whose ``rm`` fails."""

    def __init__(self, stdout: str = "", fail: tuple[str, ...] = ()) -> None:
        self.calls: list[tuple[list[str], bool]] = []
        self.stdout = stdout
        self.fail = fail

    def __call__(
        self,
        cmd: list[str],
        *,
        dry: bool,
        input_text: str | None = None,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        self.calls.append((cmd, dry))
        if dry:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        code = 1 if any(name in cmd for name in self.fail) else 0
        return subprocess.CompletedProcess(cmd, code, self.stdout, "")

    def rm_calls(self, dry: bool = False) -> list[list[str]]:
        return [
            c for c, d in self.calls if c[:3] == ["sbx", "secret", "rm"] and d is dry
        ]


def _plan(**extra: object) -> dict:
    return {
        "credentials": [
            {
                "service": "anthropic",
                "env_var": "ANTHROPIC_API_KEY",
                "domain": "api.anthropic.com",
            }
        ],
        "oauth": [],
        "egress": ["api.anthropic.com"],
        "unsupported": [],
        **extra,
    }


def _use(wizard: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: FakeRun) -> FakeRun:
    monkeypatch.setattr(wizard, "run", fake)
    return fake


def _answer(monkeypatch: pytest.MonkeyPatch, reply: str) -> list[str]:
    """Answer every confirmation with ``reply``; returns the prompts shown.

    Unpatched, pytest's captured stdin makes any unexpected prompt fail.
    """
    prompts: list[str] = []

    def _input(prompt: str) -> str:
        prompts.append(prompt)
        return reply

    monkeypatch.setattr("builtins.input", _input)
    return prompts


def test_fetch_plan_is_read_only(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = _use(
        wizard, monkeypatch, FakeRun(json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    )

    plan = wizard.fetch_plan("code-puppy", False)

    assert fake.calls == [(PLAN_CMD, False)]
    assert plan["stale_sbx_secrets"] == ["oldkey"]
    assert "pruned" not in capsys.readouterr().out


def test_fetch_plan_dry_run_returns_empty_plan(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _use(wizard, monkeypatch, FakeRun())

    plan = wizard.fetch_plan("code-puppy", True)

    assert fake.calls == [(PLAN_CMD, True)]
    assert plan == {"credentials": [], "oauth": [], "egress": [], "unsupported": []}


def test_fetch_plan_without_stale_key(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(wizard, monkeypatch, FakeRun(json.dumps(_plan())))
    assert "stale_sbx_secrets" not in wizard.fetch_plan("code-puppy", False)


def test_prune_removes_only_owned_secrets(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())

    _answer(monkeypatch, "y")
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey", "groq"]), dry=False)

    assert fake.rm_calls() == [["sbx", "secret", "rm", "oldkey", "-f"]]
    out = capsys.readouterr().out
    assert "sbx secret 'oldkey': pruned" in out
    assert "sbx secret 'groq': stale but not created by the wizard; kept" in out
    assert wizard.load_owned()["secrets"] == []


def test_prune_dry_run_previews_without_deleting(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = wizard.bindings_path()
    original = "bindings:\n" + wizard.binding_block("oldkey", "api.old.example")
    path.write_text(original, encoding="utf-8")
    owned = {"secrets": ["oldkey"], "bindings": {"oldkey": "api.old.example"}}
    wizard.save_owned(owned)
    fake = _use(wizard, monkeypatch, FakeRun())

    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey", "groq"]), dry=True)

    assert fake.calls == [(["sbx", "secret", "rm", "oldkey", "-f"], True)]
    out = capsys.readouterr().out
    assert "prune: will remove sbx secret(s): oldkey\n" in out
    assert "sbx secret 'groq': stale but not created by the wizard; kept" in out
    assert "[dry-run] would remove binding for oldkey" in out
    assert wizard.load_owned() == owned
    assert path.read_text(encoding="utf-8") == original


def test_prune_runs_on_oauth_only_plan(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())
    oauth = [{"id": "copilot", "transport": "auth-in-sandbox", "domains": []}]

    _answer(monkeypatch, "y")
    wizard.prune_owned_secrets(
        _plan(credentials=[], oauth=oauth, stale_sbx_secrets=["oldkey"]),
        dry=False,
    )

    assert fake.rm_calls() == [["sbx", "secret", "rm", "oldkey", "-f"]]


def test_extended_binding_is_not_partially_removed(wizard: ModuleType) -> None:
    path = wizard.bindings_path()
    extended = (
        "bindings:\n"
        + wizard.binding_block("oldkey", "api.old.example")
        + "      extra: true\n"
        + wizard.binding_block("groq", "api.groq.com")
    )
    path.write_text(extended, encoding="utf-8")

    assert wizard.remove_binding("oldkey", "api.old.example") is False
    assert path.read_text(encoding="utf-8") == extended


def test_binding_followed_by_sibling_is_removed_exactly(wizard: ModuleType) -> None:
    path = wizard.bindings_path()
    path.write_text(
        "bindings:\n"
        + wizard.binding_block("oldkey", "api.old.example")
        + wizard.binding_block("groq", "api.groq.com"),
        encoding="utf-8",
    )

    assert wizard.remove_binding("oldkey", "api.old.example") is True
    assert path.read_text(encoding="utf-8") == (
        "bindings:\n  groq:\n    apiKey:\n      domains: [api.groq.com]\n"
    )


def test_already_approved_binding_is_not_claimed(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = wizard.bindings_path()
    hand_written = "bindings:\n" + wizard.binding_block("oldkey", "api.old.example")
    path.write_text(hand_written, encoding="utf-8")

    wizard.ensure_binding("oldkey", "api.old.example", dry=False)
    assert wizard.load_owned()["bindings"] == {}

    # The wizard may own the secret, but never the hand-written binding.
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    _answer(monkeypatch, "y")
    _use(wizard, monkeypatch, FakeRun())
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey"]), dry=False)
    assert path.read_text(encoding="utf-8") == hand_written


def test_prune_refuses_degenerate_plan(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())

    empty = {"credentials": [], "oauth": [], "egress": [], "unsupported": []}
    wizard.prune_owned_secrets({**empty, "stale_sbx_secrets": ["oldkey"]}, dry=False)

    assert fake.calls == []


def test_prune_skips_when_plugin_reports_no_stale_key(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())

    wizard.prune_owned_secrets(_plan(), dry=False)

    assert fake.calls == []


@pytest.mark.parametrize(("reply", "accepted"), [("n", False), ("y", True)])
def test_prune_respects_confirmation(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch, reply: str, accepted: bool
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())
    _answer(monkeypatch, reply)

    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey"]), dry=False)

    assert fake.rm_calls() == (
        [["sbx", "secret", "rm", "oldkey", "-f"]] if accepted else []
    )
    assert wizard.load_owned()["secrets"] == ([] if accepted else ["oldkey"])


def test_confirm_returns_false_on_eof(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert wizard.confirm("x") is False

    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = _use(wizard, monkeypatch, FakeRun())
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey"]), dry=False)
    assert fake.rm_calls() == []


def test_prune_keeps_ownership_when_rm_fails(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wizard.save_owned({"secrets": ["a", "b"], "bindings": {"a": "api.a.example"}})
    fake = _use(wizard, monkeypatch, FakeRun(fail=("a",)))

    _answer(monkeypatch, "y")
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["a", "b"]), dry=False)

    assert len(fake.rm_calls()) == 2
    assert "warning: sbx secret rm a failed" in capsys.readouterr().out
    assert wizard.load_owned() == {"secrets": ["a"], "bindings": {"a": "api.a.example"}}


def test_binding_written_by_wizard_is_recorded_and_removed(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = wizard.bindings_path()
    path.write_text(
        "bindings:\n  groq:\n    apiKey:\n      domains: [api.groq.com]\n",
        encoding="utf-8",
    )
    wizard.ensure_binding("oldkey", "api.old.example", dry=False)
    assert wizard.load_owned()["bindings"] == {"oldkey": "api.old.example"}

    wizard.record_owned_secret("oldkey")
    _answer(monkeypatch, "y")
    _use(wizard, monkeypatch, FakeRun())
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey"]), dry=False)

    text = path.read_text(encoding="utf-8")
    assert "oldkey" not in text
    assert "  groq:\n    apiKey:\n      domains: [api.groq.com]\n" in text
    assert wizard.load_owned() == {"secrets": [], "bindings": {}}


@pytest.mark.parametrize(
    "domains",
    [
        "\n        - api.old.example",
        " [api.new.example]",
        " [api.old.example, api.extra.example]",
    ],
)
def test_edited_binding_is_kept_and_reported(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    domains: str,
) -> None:
    path = wizard.bindings_path()
    edited = f"bindings:\n  oldkey:\n    apiKey:\n      domains:{domains}\n"
    path.write_text(edited, encoding="utf-8")
    wizard.save_owned(
        {"secrets": ["oldkey"], "bindings": {"oldkey": "api.old.example"}}
    )
    _use(wizard, monkeypatch, FakeRun())

    _answer(monkeypatch, "y")
    wizard.prune_owned_secrets(_plan(stale_sbx_secrets=["oldkey"]), dry=False)

    assert path.read_text(encoding="utf-8") == edited
    assert "clean up" in capsys.readouterr().out
    assert wizard.load_owned() == {
        "secrets": [],
        "bindings": {"oldkey": "api.old.example"},
    }


def test_remove_binding_missing_file_returns_false(wizard: ModuleType) -> None:
    assert wizard.remove_binding("oldkey", "api.old.example") is False


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, {"secrets": [], "bindings": {}}),
        ("not json", {"secrets": [], "bindings": {}}),
        ("[]", {"secrets": [], "bindings": {}}),
        (
            '{"secrets": [1, null, "b", "a", "a"]}',
            {"secrets": ["a", "b"], "bindings": {}},
        ),
        ('{"secrets": "ab", "bindings": ["a"]}', {"secrets": [], "bindings": {}}),
        (
            '{"bindings": {"a": 1, "b": "api.b.example"}}',
            {"secrets": [], "bindings": {"b": "api.b.example"}},
        ),
    ],
)
def test_load_owned_tolerates_corrupt_manifest(
    wizard: ModuleType, content: str | None, expected: dict
) -> None:
    if content is not None:
        wizard.OWNED_FILE.write_text(content, encoding="utf-8")
    assert wizard.load_owned() == expected


def test_ensure_secret_records_ownership_only_when_stored(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(wizard, monkeypatch, FakeRun())
    monkeypatch.setattr(wizard, "secret_stored", lambda _s: False)
    monkeypatch.setenv("FOO_API_KEY", "value")

    wizard.ensure_secret("foo", "FOO_API_KEY", dry=True)
    assert wizard.load_owned()["secrets"] == []

    wizard.ensure_secret("foo", "FOO_API_KEY", dry=False)
    assert wizard.load_owned()["secrets"] == ["foo"]

    monkeypatch.setattr(wizard, "secret_stored", lambda _s: True)
    wizard.ensure_secret("bar", "BAR_API_KEY", dry=False)
    assert "bar" not in wizard.load_owned()["secrets"]


def _stub_main_env(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: FakeRun
) -> None:
    monkeypatch.setattr(wizard, "check_prereqs", lambda _o: "code-puppy")
    monkeypatch.setattr(wizard, "ensure_setup_cli", lambda _e: None)
    monkeypatch.setattr(wizard, "run", fake)
    monkeypatch.setattr(wizard, "ensure_secret", lambda *a: None)
    monkeypatch.setattr(wizard, "ensure_binding", lambda *a: None)
    monkeypatch.setattr(wizard, "build_creds_mixin", lambda *a: None)


def test_main_without_prune_never_deletes(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = FakeRun(json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)

    assert wizard.main(["--stock-config"]) == 0
    assert fake.rm_calls() == []
    assert (PLAN_CMD, False) in fake.calls


def test_main_plain_dry_run_does_not_execute_plan(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRun(json.dumps(_plan()))
    _stub_main_env(wizard, monkeypatch, fake)

    assert wizard.main(["--stock-config", "--dry-run"]) == 0
    assert (PLAN_CMD, True) in fake.calls
    assert all(dry for _cmd, dry in fake.calls)


@pytest.mark.parametrize(("reply", "deleted"), [("y", True), ("n", False)])
def test_main_prune_asks_before_deleting(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch, reply: str, deleted: bool
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = FakeRun(json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)
    prompts = _answer(monkeypatch, reply)

    assert wizard.main(["--stock-config", "--prune"]) == 0
    assert len(prompts) == 1
    assert fake.rm_calls() == (
        [["sbx", "secret", "rm", "oldkey", "-f"]] if deleted else []
    )
    assert wizard.load_owned()["secrets"] == ([] if deleted else ["oldkey"])


def test_main_dry_run_prune_reads_plan_to_preview(
    wizard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = FakeRun(json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)

    argv = ["--stock-config", "--prune", "--dry-run", "--live-plan"]
    assert wizard.main(argv) == 0

    assert [c for c in fake.calls if c[0] == PLAN_CMD] == [(PLAN_CMD, False)]
    assert fake.rm_calls() == []
    assert fake.rm_calls(dry=True) == [["sbx", "secret", "rm", "oldkey", "-f"]]


def test_main_dry_run_prune_executes_nothing_without_live_plan(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wizard.save_owned({"secrets": ["oldkey"], "bindings": {}})
    fake = FakeRun(json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)

    assert wizard.main(["--stock-config", "--prune", "--dry-run"]) == 0

    assert (PLAN_CMD, True) in fake.calls
    assert all(dry for _cmd, dry in fake.calls)
    assert "add --live-plan" in capsys.readouterr().out
    assert wizard.load_owned()["secrets"] == ["oldkey"]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ["anthropic"]),
        (["--dry-run"], []),
        (["--dry-run", "--live-plan"], []),
    ],
)
def test_main_hands_fetched_plan_downstream_only_on_live_runs(
    wizard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected: list[str],
) -> None:
    """A dry run never prompts for keys, even when --live-plan reads the plan."""
    _stub_main_env(wizard, monkeypatch, FakeRun(json.dumps(_plan())))
    services: list[str] = []
    monkeypatch.setattr(
        wizard, "ensure_secret", lambda service, *_a: services.append(service)
    )

    assert wizard.main(["--stock-config", *argv]) == 0
    assert services == expected


def test_main_rejects_prune_with_no_creds(wizard: ModuleType) -> None:
    with pytest.raises(SystemExit):
        wizard.main(["--prune", "--no-creds"])
