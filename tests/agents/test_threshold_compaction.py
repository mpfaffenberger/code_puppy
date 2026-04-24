from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.agents import _compaction
from code_puppy.agents.threshold_compaction import engine
from code_puppy.agents.threshold_compaction.settings import (
    ThresholdSettings,
    load_threshold_settings,
)
from code_puppy.agents.threshold_compaction.storage import (
    DURABLE_MEMORY_MARKER,
    MASKED_OBSERVATION_MARKER,
    STRUCTURED_SUMMARY_MARKER,
    cleanup_observation_archives,
    observations_dir,
)


class _FakeAgent:
    name = "threshold-agent"
    id = "threshold-agent-id"
    session_id = "threshold-session"

    def __init__(self):
        self._threshold_compaction_stats = {
            "previous_total_tokens": None,
            "turn_growth_history": [],
        }

    def get_model_name(self):
        return "fake-model"


def _sys_msg(text: str = "system prompt") -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _user_msg(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


def _tool_call(tool_name: str, args: dict, call_id: str) -> ModelMessage:
    return ModelResponse(
        parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=call_id)]
    )


def _tool_return(tool_name: str, content: str, call_id: str) -> ModelMessage:
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name,
                content=content,
                tool_call_id=call_id,
            )
        ]
    )


def _message_text(messages: list[ModelMessage]) -> str:
    chunks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            content = getattr(part, "content", None)
            if content is not None:
                chunks.append(str(content))
    return "\n".join(chunks)


def _tool_pair_ids(messages: list[ModelMessage]) -> tuple[set[str], set[str]]:
    calls: set[str] = set()
    returns: set[str] = set()
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            tool_call_id = getattr(part, "tool_call_id", None)
            if not tool_call_id:
                continue
            if getattr(part, "part_kind", None) == "tool-call":
                calls.add(tool_call_id)
            elif getattr(part, "part_kind", None) == "tool-return":
                returns.add(tool_call_id)
    return calls, returns


def _archive_text(agent: _FakeAgent) -> str:
    chunks: list[str] = []
    for archive_file in sorted(observations_dir(agent).glob("obs_*.json")):
        chunks.append(archive_file.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _bulky_history() -> list[ModelMessage]:
    return [
        _sys_msg(),
        _user_msg("Fix auth login. Do not change public API."),
        _tool_call("run_shell_command", {"command": "pytest tests/auth"}, "call-old"),
        _tool_return(
            "run_shell_command",
            "AssertionError in test_auth_login at tests/auth_test.py\n" + "x" * 12000,
            "call-old",
        ),
        _assistant_text("The router layer is not the issue. Next inspect auth.py."),
        _user_msg("latest request must remain raw " + "y" * 9000),
    ]


def _patch_threshold_strategy(monkeypatch):
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "threshold")


def test_threshold_settings_scale_from_percentages():
    settings = load_threshold_settings(200_000)
    assert settings.soft_trigger == 165_000
    assert settings.emergency_trigger == 180_000
    assert settings.target_after_compaction == 115_000
    assert settings.recent_raw_floor == 40_000
    assert settings.predicted_growth_floor == 12_000


def test_noop_below_predictive_threshold(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    agent = _FakeAgent()
    messages = [_sys_msg(), _user_msg("small request")]

    new_messages, dropped = _compaction.compact(
        agent, messages, model_max=100_000, context_overhead=0
    )

    assert new_messages is messages
    assert dropped == []
    assert DURABLE_MEMORY_MARKER not in _message_text(new_messages)


def test_predictive_trigger_can_fire_below_legacy_threshold(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    agent = _FakeAgent()
    messages = _bulky_history()

    new_messages, dropped = _compaction.compact(
        agent, messages, model_max=10_000, context_overhead=0
    )

    assert len(dropped) > 0
    rendered = _message_text(new_messages)
    assert DURABLE_MEMORY_MARKER in rendered
    assert MASKED_OBSERVATION_MARKER in rendered
    assert "latest request must remain raw" in rendered


def test_old_tool_returns_are_archived_and_masked(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    agent = _FakeAgent()
    messages = _bulky_history()

    new_messages, dropped = _compaction.compact(
        agent, messages, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert MASKED_OBSERVATION_MARKER in rendered
    assert "x" * 1000 not in rendered
    assert "latest request must remain raw" in rendered
    assert len(dropped) > 0

    archive_files = list(observations_dir(agent).glob("obs_*.json"))
    assert len(archive_files) == 1
    with archive_files[0].open(encoding="utf-8") as f:
        archive = json.load(f)
    assert "AssertionError in test_auth_login" in archive["content"]
    assert archive["status"] == "failed"

    calls, returns = _tool_pair_ids(new_messages)
    assert calls == returns


def test_durable_memory_snapshot_is_injected_once(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    agent = _FakeAgent()
    messages = _bulky_history()
    first, _ = _compaction.compact(
        agent, messages, model_max=10_000, context_overhead=0, force=True
    )
    second, _ = _compaction.compact(
        agent, first, model_max=10_000, context_overhead=0, force=True
    )

    assert _message_text(second).count(DURABLE_MEMORY_MARKER) == 1


def test_structured_fallback_summarizes_masked_band(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "run_summarization_sync",
        lambda _prompt, message_history: [
            _user_msg("Goal:\nFix auth login.\nArchive References:\n- obs_test")
        ],
    )
    monkeypatch.setattr(
        engine,
        "load_threshold_settings",
        lambda context_window: ThresholdSettings(
            context_window=context_window,
            soft_trigger=1,
            emergency_trigger=context_window,
            target_after_compaction=300,
            recent_raw_floor=100,
            predicted_growth_floor=0,
            growth_history_window=10,
            archive_retention_days=30,
            archive_retention_count=500,
            mask_min_tokens=250,
        ),
    )
    agent = _FakeAgent()

    new_messages, _ = _compaction.compact(
        agent, _bulky_history(), model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert STRUCTURED_SUMMARY_MARKER in rendered
    assert "Archive References" in rendered


def test_emergency_trim_keeps_latest_user_request(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "run_summarization_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no model")),
    )
    monkeypatch.setattr(
        engine,
        "load_threshold_settings",
        lambda context_window: ThresholdSettings(
            context_window=context_window,
            soft_trigger=1,
            emergency_trigger=500,
            target_after_compaction=300,
            recent_raw_floor=100,
            predicted_growth_floor=0,
            growth_history_window=10,
            archive_retention_days=30,
            archive_retention_count=500,
            mask_min_tokens=250,
        ),
    )
    agent = _FakeAgent()

    new_messages, _ = _compaction.compact(
        agent, _bulky_history(), model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert "latest request must remain raw" in rendered
    assert DURABLE_MEMORY_MARKER in rendered


def test_emergency_trim_keeps_current_error_and_pair(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "run_summarization_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no model")),
    )
    monkeypatch.setattr(
        engine,
        "load_threshold_settings",
        lambda context_window: ThresholdSettings(
            context_window=context_window,
            soft_trigger=1,
            emergency_trigger=500,
            target_after_compaction=300,
            recent_raw_floor=100,
            predicted_growth_floor=0,
            growth_history_window=10,
            archive_retention_days=30,
            archive_retention_count=500,
            mask_min_tokens=250,
        ),
    )
    history = [
        _sys_msg(),
        _user_msg("Fix the current error in current_error.py."),
        _tool_call("run_shell_command", {"command": "pytest"}, "call-current"),
        _tool_return(
            "run_shell_command",
            "RuntimeError: current failure in current_error.py\n" + "z" * 5000,
            "call-current",
        ),
    ]

    new_messages, _ = _compaction.compact(
        _FakeAgent(), history, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert "RuntimeError: current failure" in rendered
    calls, returns = _tool_pair_ids(new_messages)
    assert calls == returns == {"call-current"}


def test_precision_probes_survive_ten_compaction_cycles(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_threshold_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "load_threshold_settings",
        lambda context_window: ThresholdSettings(
            context_window=context_window,
            soft_trigger=1,
            emergency_trigger=context_window,
            target_after_compaction=20_000,
            recent_raw_floor=500,
            predicted_growth_floor=0,
            growth_history_window=10,
            archive_retention_days=30,
            archive_retention_count=100,
            mask_min_tokens=100,
        ),
    )
    agent = _FakeAgent()
    history: list[ModelMessage] = [
        _sys_msg(),
        _user_msg(
            "Project goal precision probe GOAL-KEY-ROOT. "
            "Must preserve constraint key CONSTRAINT-KEY-ROOT."
        ),
    ]
    direct_prompt_keys = {"GOAL-KEY-ROOT", "CONSTRAINT-KEY-ROOT"}
    direct_observation_keys: set[str] = set()
    archive_only_keys: set[str] = set()
    first_loss_cycle: int | None = None
    loss_details: list[str] = []

    for cycle in range(1, 11):
        request_key = f"REQUEST-KEY-{cycle:02d}"
        signal_key = f"SIGNAL-KEY-{cycle:02d}"
        archive_key = f"ARCHIVE-ONLY-KEY-{cycle:02d}"
        direct_prompt_keys.add(request_key)
        direct_observation_keys.add(signal_key)
        archive_only_keys.add(archive_key)

        call_id = f"precision-call-{cycle:02d}"
        history.extend(
            [
                _user_msg(
                    f"Cycle {cycle}: must preserve {request_key}; "
                    "do not lose GOAL-KEY-ROOT."
                ),
                _tool_call(
                    "run_shell_command",
                    {"command": f"pytest tests/precision_{cycle}.py"},
                    call_id,
                ),
                _tool_return(
                    "run_shell_command",
                    (
                        f"AssertionError {signal_key} in tests/precision_{cycle}.py\n"
                        + "diagnostic noise\n" * 240
                        + f"{archive_key}\n"
                    ),
                    call_id,
                ),
                _assistant_text(
                    f"Validation failed for {signal_key}. "
                    f"Next action: inspect precision_{cycle}.py."
                ),
            ]
        )

        history, _ = _compaction.compact(
            agent,
            history,
            model_max=50_000,
            context_overhead=0,
            force=True,
        )
        prompt_text = _message_text(history)
        archive_text = _archive_text(agent)

        missing_prompt = sorted(
            key
            for key in direct_prompt_keys | direct_observation_keys
            if key not in prompt_text
        )
        recoverable_text = prompt_text + "\n" + archive_text
        missing_recoverable = sorted(
            key for key in archive_only_keys if key not in recoverable_text
        )
        calls, returns = _tool_pair_ids(history)
        if missing_prompt or missing_recoverable or calls != returns:
            first_loss_cycle = cycle
            loss_details = [
                f"missing prompt keys: {missing_prompt}",
                f"missing recoverable archive keys: {missing_recoverable}",
                f"tool calls without matching returns: {sorted(calls - returns)}",
                f"tool returns without matching calls: {sorted(returns - calls)}",
            ]
            break

    assert first_loss_cycle is None, (
        f"Precision probe lost recoverability at cycle {first_loss_cycle}: "
        + "; ".join(loss_details)
    )
    final_prompt = _message_text(history)
    assert final_prompt.count(DURABLE_MEMORY_MARKER) == 1
    assert final_prompt.count(MASKED_OBSERVATION_MARKER) >= 9
    assert all(key in final_prompt for key in direct_prompt_keys)
    assert all(key in final_prompt for key in direct_observation_keys)
    final_recoverable_text = final_prompt + "\n" + _archive_text(agent)
    assert all(key in final_recoverable_text for key in archive_only_keys)


def test_archive_retention_cleanup(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    agent = _FakeAgent()
    path = observations_dir(agent)
    old_file = path / "obs_old.json"
    old_file.write_text("{}", encoding="utf-8")
    old_time = time.time() - 3 * 24 * 60 * 60
    os.utime(old_file, (old_time, old_time))
    newest_files = []
    for idx in range(3):
        entry = path / f"obs_new_{idx}.json"
        entry.write_text("{}", encoding="utf-8")
        newest_files.append(entry)

    cleanup_observation_archives(
        agent,
        ThresholdSettings(
            context_window=10_000,
            soft_trigger=1,
            emergency_trigger=9_000,
            target_after_compaction=5_000,
            recent_raw_floor=1_000,
            predicted_growth_floor=500,
            growth_history_window=10,
            archive_retention_days=1,
            archive_retention_count=2,
            mask_min_tokens=250,
        ),
    )

    remaining = sorted(item.name for item in path.glob("obs_*.json"))
    assert old_file.name not in remaining
    assert len(remaining) == 2
