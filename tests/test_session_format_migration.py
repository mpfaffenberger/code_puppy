"""Tests for the pickle -> JSON session format migration (Phase A.1).

Covers:
- golden-fixture migration (plain + legacy signed framing) generated with
  pydantic-ai 1.x classes -- see tests/fixtures/generate_v1_session_pickles.py
- the no-pydantic-ai-import guarantee of the surrogate unpickler module
- the one-time startup sweep (idempotency, quarantine, marker short-circuit)
- JSON round-trips through save_session/load_session and the sub-agent path
- quick-resume resolution across the format boundary
"""

from __future__ import annotations

import json
import pickle
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from code_puppy import config as cp_config
from code_puppy import session_format_migration as sfm
from code_puppy import session_storage
from code_puppy.session_storage import (
    ENCODING_JSON,
    ENCODING_MESSAGES,
    SESSION_FORMAT_VERSION,
    load_session,
    save_session,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PLAIN_FIXTURE = FIXTURE_DIR / "session_v1_plain.pkl"
SIGNED_FIXTURE = FIXTURE_DIR / "session_v1_signed.pkl"
SUBAGENT_FIXTURE = FIXTURE_DIR / "subagent_v1_history.pkl"

PNG_BYTES = b"\x89PNG\r\n\x1a\nnot-really-a-png"


def _assert_golden_history(history: list) -> None:
    """The full checklist for a migrated golden fixture."""
    from pydantic_ai.messages import (
        BinaryContent,
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
    )

    assert len(history) == 5
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)

    system_part, user_part = history[0].parts
    assert system_part.content == "You are Biscuit, a digital puppy."
    attachment = user_part.content[1]
    assert isinstance(attachment, BinaryContent)
    assert attachment.data == PNG_BYTES  # bytes survive base64 round-trip
    assert attachment.media_type == "image/png"

    thinking, text, tool_call = history[1].parts
    assert isinstance(thinking, ThinkingPart)
    assert thinking.signature == "sig-abc123"  # signature survives
    assert text.content == "Looks like a PNG. Let me grep around."
    assert isinstance(tool_call, ToolCallPart)
    assert tool_call.args == {"search_string": "puppy"}

    tool_return = history[2].parts[0]
    assert isinstance(tool_return, ToolReturnPart)
    assert tool_return.tool_call_id == tool_call.tool_call_id == "call_1"
    assert tool_return.content == "3 matches"

    retry = history[3].parts[0]
    assert isinstance(retry, RetryPromptPart)
    assert retry.tool_name == "grep"
    assert retry.tool_call_id == "call_2"


class TestGoldenFixtureMigration:
    @pytest.mark.parametrize("fixture", [PLAIN_FIXTURE, SIGNED_FIXTURE])
    def test_migrate_file_produces_valid_envelope(self, tmp_path, fixture):
        pkl_path = tmp_path / "golden.pkl"
        shutil.copy(fixture, pkl_path)

        result = sfm.migrate_pickle_file(pkl_path)

        assert result.success, result.error
        envelope = session_storage.read_envelope_file(result.json_path)
        assert envelope["format"] == SESSION_FORMAT_VERSION
        assert envelope["encoding"] == ENCODING_MESSAGES
        _assert_golden_history(session_storage.decode_envelope(envelope))
        # Originals are the caller's to archive -- migrate never deletes.
        assert pkl_path.exists()

    def test_load_session_lazy_migrates_pkl_only_session(self, tmp_path):
        shutil.copy(PLAIN_FIXTURE, tmp_path / "mysess.pkl")

        history = load_session("mysess", tmp_path)

        _assert_golden_history(history)
        assert (tmp_path / "mysess.json").exists()
        # Original pickle archived, never deleted.
        assert not (tmp_path / "mysess.pkl").exists()
        assert (tmp_path / "pre_v2_backup" / "mysess.pkl").exists()

    def test_migration_repoints_meta_sidecar(self, tmp_path):
        pkl_path = tmp_path / "named.pkl"
        shutil.copy(PLAIN_FIXTURE, pkl_path)
        meta_path = tmp_path / "named_meta.json"
        meta_path.write_text(
            json.dumps({"session_name": "named", "file_path": str(pkl_path)}),
            encoding="utf-8",
        )

        result = sfm.migrate_pickle_file(pkl_path)

        assert result.success
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["file_path"] == str(tmp_path / "named.json")

    def test_plain_builtin_pickle_migrates_verbatim(self, tmp_path):
        history = [{"role": "user", "content": "plain dict history"}]
        pkl_path = tmp_path / "plain.pkl"
        pkl_path.write_bytes(pickle.dumps(history))

        result = sfm.migrate_pickle_file(pkl_path)

        assert result.success
        envelope = session_storage.read_envelope_file(result.json_path)
        assert envelope["encoding"] == ENCODING_JSON
        assert session_storage.decode_envelope(envelope) == history

    def test_non_list_payload_fails_cleanly(self, tmp_path):
        pkl_path = tmp_path / "scalar.pkl"
        pkl_path.write_bytes(pickle.dumps({"not": "a list"}))

        result = sfm.migrate_pickle_file(pkl_path)

        assert not result.success
        assert "expected a list" in result.error


class _WeirdTz(tzinfo):
    """A tzinfo from a module the unpickler will never allowlist."""

    def utcoffset(self, dt):
        return timedelta(hours=2)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "WEIRD"


class TestTzAwareDatetimes:
    """Regression: surrogated tzinfo classes must not quarantine sessions.

    Real-world failure: pickled timestamps carried
    ``pydantic_core._pydantic_core.TzInfo``; surrogating it made datetime's
    C constructor raise ``TypeError: bad tzinfo state arg``.
    """

    def test_pydantic_core_tzinfo_maps_to_stdlib_timezone(self):
        from pydantic_core import TzInfo

        from code_puppy import session_surrogate_unpickler as ssu

        aware = datetime(2025, 5, 1, 12, 30, tzinfo=TzInfo(3600))
        history, _ = ssu.load_surrogate_pickle(pickle.dumps([aware]))

        restored = history[0]
        assert restored.tzinfo == timezone(timedelta(hours=1))
        assert restored.isoformat() == "2025-05-01T12:30:00+01:00"

    def test_unknown_tzinfo_degrades_to_naive_datetime(self):
        from code_puppy import session_surrogate_unpickler as ssu

        aware = datetime(2025, 5, 1, 12, 30, tzinfo=_WeirdTz())
        history, had_surrogates = ssu.load_surrogate_pickle(pickle.dumps([aware]))

        # Lossy naive timestamp beats a quarantined session.
        assert had_surrogates
        assert history[0] == datetime(2025, 5, 1, 12, 30)
        assert history[0].tzinfo is None

    def test_migrate_file_with_pydantic_core_tzinfo_timestamps(self, tmp_path):
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            TextPart,
            UserPromptPart,
        )
        from pydantic_core import TzInfo

        aware = datetime(2025, 5, 1, 12, 30, tzinfo=TzInfo(3600))
        history = [
            ModelRequest(parts=[UserPromptPart(content="hi", timestamp=aware)]),
            ModelResponse(parts=[TextPart(content="woof")], timestamp=aware),
        ]
        pkl_path = tmp_path / "tzaware.pkl"
        pkl_path.write_bytes(pickle.dumps(history))

        result = sfm.migrate_pickle_file(pkl_path)

        assert result.success, result.error
        restored = load_session("tzaware", tmp_path)
        assert restored[0].parts[0].timestamp == aware
        assert restored[1].timestamp == aware


class TestNoPydanticAiImportGuard:
    def test_unpickler_module_migrates_fixture_without_pydantic_ai(self):
        """The surrogate unpickler must work with pydantic_ai fully absent."""
        module_path = (
            Path(__file__).parent.parent
            / "code_puppy"
            / "session_surrogate_unpickler.py"
        )
        script = f"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ssu", {str(module_path)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
payload = open({str(PLAIN_FIXTURE)!r}, "rb").read()
history, had_surrogates = module.load_surrogate_pickle(payload)
messages = module.normalize_history(history)
assert had_surrogates and len(messages) == 5, messages
leaked = sorted(
    name for name in sys.modules
    if name.split(".")[0] in ("pydantic_ai", "pydantic", "pydantic_core")
)
assert not leaked, f"forbidden imports leaked: {{leaked}}"
print("clean")
"""
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        assert completed.returncode == 0, completed.stderr
        assert "clean" in completed.stdout


@pytest.fixture
def sweep_dirs(tmp_path, monkeypatch):
    """Point every sweep directory + the marker at isolated temp dirs."""
    autosaves = tmp_path / "autosaves"
    contexts = tmp_path / "contexts"
    data = tmp_path / "data"
    config = tmp_path / "config"
    for directory in (autosaves, contexts, data, config):
        directory.mkdir()
    monkeypatch.setattr(cp_config, "AUTOSAVE_DIR", str(autosaves))
    monkeypatch.setattr(cp_config, "CONTEXTS_DIR", str(contexts))
    monkeypatch.setattr(cp_config, "DATA_DIR", str(data))
    monkeypatch.setattr(cp_config, "CONFIG_DIR", str(config))
    return autosaves, contexts, data, config


class TestStartupSweep:
    def test_sweep_migrates_quarantines_and_marks(self, sweep_dirs):
        autosaves, _contexts, _data, config = sweep_dirs
        shutil.copy(PLAIN_FIXTURE, autosaves / "good.pkl")
        (autosaves / "bad.pkl").write_bytes(b"definitely not a pickle")

        sfm.sweep_legacy_pickle_sessions()

        # Good file migrated + archived; bad file quarantined; both kept.
        assert (autosaves / "good.json").exists()
        assert (autosaves / "pre_v2_backup" / "good.pkl").exists()
        assert (autosaves / "pre_v2_backup" / "failed" / "bad.pkl").exists()
        assert not (autosaves / "good.pkl").exists()
        assert not (autosaves / "bad.pkl").exists()
        assert (config / ".session_format_v2_migrated").exists()

    def test_marker_short_circuits_second_run(self, sweep_dirs):
        autosaves, _contexts, _data, _config = sweep_dirs
        sfm.sweep_legacy_pickle_sessions()  # writes the marker (no-op sweep)

        shutil.copy(PLAIN_FIXTURE, autosaves / "late.pkl")
        sfm.sweep_legacy_pickle_sessions()

        # Marker short-circuit: the late arrival is untouched by the sweep...
        assert (autosaves / "late.pkl").exists()
        assert not (autosaves / "late.json").exists()
        # ...but the lazy load_session fallback still rescues it.
        history = load_session("late", autosaves)
        _assert_golden_history(history)

    def test_sweep_covers_subagent_and_acp_dirs(self, sweep_dirs):
        autosaves, contexts, data, _config = sweep_dirs
        subagent_dir = data / "subagent_sessions"
        acp_dir = autosaves / "acp"
        subagent_dir.mkdir()
        acp_dir.mkdir()
        shutil.copy(SUBAGENT_FIXTURE, subagent_dir / "sub-task.pkl")
        shutil.copy(PLAIN_FIXTURE, acp_dir / "sess_1.pkl")
        shutil.copy(PLAIN_FIXTURE, contexts / "old_ctx.pkl")

        sfm.sweep_legacy_pickle_sessions()

        assert (subagent_dir / "sub-task.json").exists()
        assert (acp_dir / "sess_1.json").exists()
        assert (contexts / "old_ctx.json").exists()

    def test_sweep_skips_pkl_with_existing_json_twin(self, sweep_dirs):
        autosaves, _contexts, _data, _config = sweep_dirs
        shutil.copy(PLAIN_FIXTURE, autosaves / "twin.pkl")
        (autosaves / "twin.json").write_text("{}", encoding="utf-8")

        sfm.sweep_legacy_pickle_sessions()

        # Dual-format pair left exactly as found.
        assert (autosaves / "twin.pkl").exists()
        assert (autosaves / "twin.json").read_text(encoding="utf-8") == "{}"

    def test_failures_produce_single_summary_warning(self, sweep_dirs, monkeypatch):
        autosaves, _contexts, _data, _config = sweep_dirs
        (autosaves / "bad1.pkl").write_bytes(b"garbage one")
        (autosaves / "bad2.pkl").write_bytes(b"garbage two")
        warnings: list[str] = []
        from code_puppy import messaging

        monkeypatch.setattr(
            messaging, "emit_warning", lambda msg, **kw: warnings.append(msg)
        )

        sfm.sweep_legacy_pickle_sessions()

        # Per-file details are debug-only; users get ONE summary line.
        assert len(warnings) == 1
        assert "2 session(s)" in warnings[0]


class TestQuarantineRecovery:
    """The retry pass must rescue quarantined pickles once the unpickler
    learns new tricks -- even after the one-time marker exists."""

    def test_retry_rescues_quarantined_sessions(self, sweep_dirs):
        autosaves, _contexts, _data, _config = sweep_dirs
        sfm.sweep_legacy_pickle_sessions()  # writes the marker
        failed_dir = autosaves / "pre_v2_backup" / "failed"
        failed_dir.mkdir(parents=True)
        shutil.copy(PLAIN_FIXTURE, failed_dir / "rescued.pkl")
        (failed_dir / "stuck.pkl").write_bytes(b"still not a pickle")

        sfm.sweep_legacy_pickle_sessions()

        # Rescued: JSON in the sessions dir, pkl graduated out of failed/.
        assert (autosaves / "rescued.json").exists()
        assert (autosaves / "pre_v2_backup" / "rescued.pkl").exists()
        assert not (failed_dir / "rescued.pkl").exists()
        # Stuck: left in quarantine, no exception, no churn.
        assert (failed_dir / "stuck.pkl").exists()
        _assert_golden_history(load_session("rescued", autosaves))

    def test_retry_never_clobbers_existing_json_twin(self, sweep_dirs):
        autosaves, _contexts, _data, _config = sweep_dirs
        sfm.sweep_legacy_pickle_sessions()
        failed_dir = autosaves / "pre_v2_backup" / "failed"
        failed_dir.mkdir(parents=True)
        shutil.copy(PLAIN_FIXTURE, failed_dir / "twin.pkl")
        (autosaves / "twin.json").write_text("{}", encoding="utf-8")

        sfm.sweep_legacy_pickle_sessions()

        # Live JSON wins; the quarantined pkl stays put untouched.
        assert (autosaves / "twin.json").read_text(encoding="utf-8") == "{}"
        assert (failed_dir / "twin.pkl").exists()


class TestJsonRoundTrip:
    @staticmethod
    def _real_history():
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            TextPart,
            UserPromptPart,
        )

        return [
            ModelRequest(parts=[UserPromptPart(content="hi puppy")]),
            ModelResponse(parts=[TextPart(content="woof")]),
        ]

    def test_save_and_load_real_messages(self, tmp_path):
        history = self._real_history()
        metadata = save_session(
            history=history,
            session_name="roundtrip",
            base_dir=tmp_path,
            timestamp="2026-01-01T00:00:00",
            token_estimator=lambda _m: 1,
        )

        assert metadata.json_path.exists()
        envelope = session_storage.read_envelope_file(metadata.json_path)
        assert envelope["format"] == SESSION_FORMAT_VERSION
        assert envelope["encoding"] == ENCODING_MESSAGES
        assert load_session("roundtrip", tmp_path) == history
        # Metadata sidecar points at the JSON file now.
        meta = json.loads(metadata.metadata_path.read_text(encoding="utf-8"))
        assert meta["file_path"] == str(metadata.json_path)

    def test_save_and_load_plain_payload(self, tmp_path):
        history = [{"role": "user", "content": "not a ModelMessage"}]
        save_session(
            history=history,
            session_name="plain",
            base_dir=tmp_path,
            timestamp="2026-01-01T00:00:00",
            token_estimator=lambda _m: 0,
        )
        assert load_session("plain", tmp_path) == history

    def test_list_and_cleanup_handle_both_formats(self, tmp_path):
        (tmp_path / "old_style.pkl").write_bytes(b"dummy")
        (tmp_path / "new_style.json").write_text("{}", encoding="utf-8")
        (tmp_path / "new_style_meta.json").write_text("{}", encoding="utf-8")

        assert session_storage.list_sessions(tmp_path) == [
            "new_style",
            "old_style",
        ]

        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=1)
        assert removed == ["old_style"]
        assert not (tmp_path / "old_style.pkl").exists()
        assert (tmp_path / "new_style.json").exists()

    def test_subagent_session_roundtrip_and_lazy_migration(self, tmp_path, monkeypatch):
        from code_puppy.tools import agent_tools

        monkeypatch.setattr(agent_tools, "_get_subagent_sessions_dir", lambda: tmp_path)

        # Lazy migration of a legacy pickle written by the old code path.
        shutil.copy(SUBAGENT_FIXTURE, tmp_path / "legacy-session.pkl")
        history = agent_tools._load_session_history("legacy-session")
        _assert_golden_history(history)
        assert (tmp_path / "legacy-session.json").exists()

        # Save-back writes the shared JSON envelope, no pickle.
        agent_tools._save_session_history(
            session_id="legacy-session",
            message_history=history,
            agent_name="tester",
            initial_prompt="hello",
        )
        assert not (tmp_path / "legacy-session.pkl").exists()
        assert agent_tools._load_session_history("legacy-session") == history


class TestQuickResumeAcrossFormats:
    def _resolve(self, monkeypatch, autosave_dir: Path, session_name: str):
        monkeypatch.setattr(cp_config, "AUTOSAVE_DIR", str(autosave_dir))
        monkeypatch.setattr(
            cp_config,
            "get_last_directory_session",
            lambda *_a, **_k: session_name,
        )
        return cp_config.resolve_quick_resume_pickle(".")

    def test_resolves_json_first(self, tmp_path, monkeypatch):
        (tmp_path / "auto_session_x.json").write_text("{}", encoding="utf-8")
        (tmp_path / "auto_session_x.pkl").write_bytes(b"dummy")
        resolved = self._resolve(monkeypatch, tmp_path, "auto_session_x")
        assert resolved == str(tmp_path / "auto_session_x.json")

    def test_falls_back_to_pkl_and_load_migrates(self, tmp_path, monkeypatch):
        shutil.copy(PLAIN_FIXTURE, tmp_path / "auto_session_y.pkl")
        resolved = self._resolve(monkeypatch, tmp_path, "auto_session_y")
        assert resolved == str(tmp_path / "auto_session_y.pkl")

        # The -r/-qr load path: stem + parent through load_session.
        resolved_path = Path(resolved)
        history = load_session(resolved_path.stem, resolved_path.parent)
        _assert_golden_history(history)
        assert (tmp_path / "auto_session_y.json").exists()

    def test_returns_none_when_nothing_on_disk(self, tmp_path, monkeypatch):
        assert self._resolve(monkeypatch, tmp_path, "auto_session_z") is None
