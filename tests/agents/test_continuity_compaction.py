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
from code_puppy.agents.continuity_compaction import engine
from code_puppy.agents.continuity_compaction import task_detection
from code_puppy.agents.continuity_compaction.settings import (
    ContinuityCompactionSettings,
    load_continuity_compaction_settings,
)
from code_puppy.agents.continuity_compaction.storage import (
    DURABLE_MEMORY_MARKER,
    MASKED_OBSERVATION_MARKER,
    STRUCTURED_SUMMARY_MARKER,
    cleanup_observation_archives,
    durable_state_path,
    observations_dir,
)
from code_puppy.agents.continuity_compaction.task_detection import SemanticTaskState


class _FakeAgent:
    name = "continuity-agent"
    id = "continuity-agent-id"
    session_id = "continuity-session"

    def __init__(self):
        self._continuity_compaction_stats = {
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


def _patch_continuity_strategy(monkeypatch):
    monkeypatch.setattr(_compaction, "get_compaction_strategy", lambda: "continuity")
    monkeypatch.setattr(engine, "resolve_semantic_task_state", lambda **_kwargs: None)


def test_continuity_settings_scale_from_percentages():
    settings = load_continuity_compaction_settings(200_000)
    assert settings.soft_trigger == 165_000
    assert settings.emergency_trigger == 180_000
    assert settings.target_after_compaction == 115_000
    assert settings.recent_raw_floor == 40_000
    assert settings.predicted_growth_floor == 12_000


def test_noop_below_predictive_threshold(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    emitted = []
    monkeypatch.setattr(
        engine,
        "emit_info",
        lambda content, **metadata: emitted.append(("info", str(content), metadata)),
    )
    monkeypatch.setattr(
        engine,
        "emit_success",
        lambda content, **metadata: emitted.append(("success", str(content), metadata)),
    )
    agent = _FakeAgent()
    messages = [_sys_msg(), _user_msg("small request")]

    new_messages, dropped = _compaction.compact(
        agent, messages, model_max=100_000, context_overhead=0
    )

    assert new_messages is messages
    assert dropped == []
    assert DURABLE_MEMORY_MARKER not in _message_text(new_messages)
    assert emitted == []


def test_predictive_trigger_can_fire_below_legacy_threshold(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
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


def test_continuity_compaction_emits_visible_status(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    emitted = []
    monkeypatch.setattr(
        engine,
        "emit_info",
        lambda content, **metadata: emitted.append(("info", str(content), metadata)),
    )
    monkeypatch.setattr(
        engine,
        "emit_success",
        lambda content, **metadata: emitted.append(("success", str(content), metadata)),
    )

    _compaction.compact(
        _FakeAgent(), _bulky_history(), model_max=10_000, context_overhead=0, force=True
    )

    assert len(emitted) == 2
    assert emitted[0][0] == "info"
    assert "Continuity compaction forced at" in emitted[0][1]
    assert "predicted next turn +" in emitted[0][1]
    assert "target" in emitted[0][1]
    assert emitted[0][2]["message_group"] == "token_context_status"
    assert emitted[1][0] == "success"
    assert "Continuity compaction complete:" in emitted[1][1]
    assert "context" in emitted[1][1]
    assert "messages" in emitted[1][1]
    assert "archived and masked 1 observation(s)" in emitted[1][1]
    assert emitted[1][2]["message_group"] == "token_context_status"


def test_old_tool_returns_are_archived_and_masked(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
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
    _patch_continuity_strategy(monkeypatch)
    agent = _FakeAgent()
    messages = _bulky_history()
    first, _ = _compaction.compact(
        agent, messages, model_max=10_000, context_overhead=0, force=True
    )
    second, _ = _compaction.compact(
        agent, first, model_max=10_000, context_overhead=0, force=True
    )

    assert _message_text(second).count(DURABLE_MEMORY_MARKER) == 1


def test_durable_memory_tracks_current_task_and_task_ledger(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    agent = _FakeAgent()
    history = [
        _user_msg("Task one: build import flow ROOT-TASK-ONE."),
        _assistant_text("Import flow is complete."),
        _user_msg("Switching tasks: build billing exporter ROOT-TASK-TWO."),
        _assistant_text("Billing exporter work started."),
        _user_msg("Run validation for billing exporter ROOT-LATEST-REQUEST."),
    ]

    new_messages, _ = _compaction.compact(
        agent, history, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert (
        "Current Task: Switching tasks: build billing exporter ROOT-TASK-TWO."
        in rendered
    )
    assert (
        "Latest User Request: Run validation for billing exporter ROOT-LATEST-REQUEST."
    ) in rendered
    assert "Task Ledger:" in rendered
    assert "ROOT-TASK-ONE" in rendered
    assert "ROOT-TASK-TWO" in rendered

    with durable_state_path(agent).open(encoding="utf-8") as f:
        durable_state = json.load(f)
    assert "ROOT-TASK-TWO" in durable_state["current_task"]
    assert "ROOT-LATEST-REQUEST" in durable_state["latest_user_request"]
    assert any("ROOT-TASK-ONE" in item for item in durable_state["task_ledger"])
    assert any("ROOT-TASK-TWO" in item for item in durable_state["task_ledger"])


def test_semantic_task_detection_can_override_regex_task_boundary(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)

    captured = {}

    def fake_semantic_task_state(**kwargs):
        captured.update(kwargs)
        return SemanticTaskState(
            current_task="Build dashboard analytics ROOT-SEMANTIC-TASK.",
            task_ledger=[
                "Initial task ROOT-TASK-ONE.",
                "Build dashboard analytics ROOT-SEMANTIC-TASK.",
            ],
        )

    monkeypatch.setattr(
        engine,
        "resolve_semantic_task_state",
        fake_semantic_task_state,
    )
    agent = _FakeAgent()
    history = [
        _user_msg("Initial task ROOT-TASK-ONE."),
        _assistant_text("Initial task complete."),
        _user_msg(
            "Okay about the dashboard now, wire up analytics ROOT-SUBTLE-SWITCH."
        ),
        _assistant_text("Dashboard analytics started."),
        _user_msg("Continue the chart validation ROOT-LATEST-REQUEST."),
    ]

    new_messages, _ = _compaction.compact(
        agent, history, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert "Current Task: Build dashboard analytics ROOT-SEMANTIC-TASK." in rendered
    assert (
        "Latest User Request: Continue the chart validation ROOT-LATEST-REQUEST."
        in rendered
    )
    assert "ROOT-TASK-ONE" in rendered
    assert "ROOT-SEMANTIC-TASK" in rendered
    assert "ROOT-LATEST-REQUEST" in captured["latest_user_request"]
    assert "ROOT-TASK-ONE" in captured["fallback_current_task"]


def test_semantic_task_detection_failure_falls_back_to_deterministic(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "resolve_semantic_task_state",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable")),
    )
    history = [
        _user_msg("Task one ROOT-TASK-ONE."),
        _assistant_text("Task one done."),
        _user_msg("Switching tasks: build billing exporter ROOT-TASK-TWO."),
        _user_msg("Continue billing exporter ROOT-LATEST-REQUEST."),
    ]

    new_messages, _ = _compaction.compact(
        _FakeAgent(), history, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert (
        "Current Task: Switching tasks: build billing exporter ROOT-TASK-TWO."
        in rendered
    )
    assert "ROOT-LATEST-REQUEST" in rendered


def test_semantic_task_detector_parses_json_text_response(monkeypatch):
    monkeypatch.setattr(
        task_detection,
        "get_continuity_compaction_semantic_task_detection",
        lambda: True,
    )
    monkeypatch.setattr(
        task_detection,
        "run_summarization_sync",
        lambda *_args, **_kwargs: [
            _assistant_text(
                '```json\n{"current_task":"Semantic task ROOT-LLM",'
                '"task_ledger":["Original ROOT-ONE","Semantic task ROOT-LLM"]}\n```'
            )
        ],
    )

    state = task_detection.resolve_semantic_task_state(
        user_entries=[(1, "Original ROOT-ONE"), (2, "Subtle switch ROOT-SUBTLE")],
        previous_current_task="Original ROOT-ONE",
        previous_task_ledger=["Original ROOT-ONE"],
        latest_user_request="Continue ROOT-LATEST",
        fallback_current_task="Original ROOT-ONE",
        fallback_task_ledger=["Original ROOT-ONE"],
    )

    assert state is not None
    assert state.current_task == "Semantic task ROOT-LLM"
    assert state.task_ledger == ["Original ROOT-ONE", "Semantic task ROOT-LLM"]


def test_semantic_task_detector_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(
        task_detection,
        "get_continuity_compaction_semantic_task_detection",
        lambda: True,
    )
    monkeypatch.setattr(
        task_detection,
        "run_summarization_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    state = task_detection.resolve_semantic_task_state(
        user_entries=[(1, "Original ROOT-ONE")],
        previous_current_task="",
        previous_task_ledger=[],
        latest_user_request="Original ROOT-ONE",
        fallback_current_task="Original ROOT-ONE",
        fallback_task_ledger=["Original ROOT-ONE"],
    )

    assert state is None


def test_emergency_trim_keeps_task_roots_without_pinning_stale_first_raw(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "load_continuity_compaction_settings",
        lambda context_window: ContinuityCompactionSettings(
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
    first_task = (
        "Initial task ROOT-TASK-ONE. "
        + "obsolete implementation detail " * 900
        + "RAW-FIRST-ONLY"
    )
    history = [
        _user_msg(first_task),
        _assistant_text("Initial task completed."),
        _user_msg("Switching tasks: build billing exporter ROOT-TASK-TWO."),
        _assistant_text("Billing exporter current error: failing validation."),
        _user_msg("Continue billing exporter ROOT-LATEST-REQUEST."),
    ]

    new_messages, _ = _compaction.compact(
        _FakeAgent(), history, model_max=10_000, context_overhead=0, force=True
    )

    rendered = _message_text(new_messages)
    assert "ROOT-TASK-ONE" in rendered
    assert "ROOT-TASK-TWO" in rendered
    assert "ROOT-LATEST-REQUEST" in rendered
    assert "RAW-FIRST-ONLY" not in rendered


def test_task_ledger_preserves_original_root_after_many_task_switches(
    monkeypatch, tmp_path: Path
):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    agent = _FakeAgent()
    history = [_user_msg("Initial task ROOT-ORIGINAL-TASK.")]
    for idx in range(1, 22):
        history.extend(
            [
                _assistant_text(f"Completed previous task {idx}."),
                _user_msg(f"New task: build feature ROOT-TASK-{idx:02d}."),
            ]
        )

    _compaction.compact(
        agent, history, model_max=10_000, context_overhead=0, force=True
    )

    with durable_state_path(agent).open(encoding="utf-8") as f:
        durable_state = json.load(f)
    ledger = durable_state["task_ledger"]
    assert len(ledger) == 16
    assert "ROOT-ORIGINAL-TASK" in ledger[0]
    assert "ROOT-TASK-21" in ledger[-1]
    assert "ROOT-TASK-21" in durable_state["current_task"]


def test_structured_fallback_summarizes_masked_band(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config
    import code_puppy.summarization_agent as summarization_agent

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        summarization_agent,
        "run_summarization_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no model")),
    )
    monkeypatch.setattr(
        engine,
        "load_continuity_compaction_settings",
        lambda context_window: ContinuityCompactionSettings(
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
    assert "Summarized 1 already-masked observation" in rendered


def test_emergency_trim_keeps_latest_user_request(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "load_continuity_compaction_settings",
        lambda context_window: ContinuityCompactionSettings(
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
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "load_continuity_compaction_settings",
        lambda context_window: ContinuityCompactionSettings(
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


def test_precision_probes_survive_ten_compaction_cycles(monkeypatch, tmp_path: Path):
    import code_puppy.config as cp_config

    monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
    _patch_continuity_strategy(monkeypatch)
    monkeypatch.setattr(
        engine,
        "load_continuity_compaction_settings",
        lambda context_window: ContinuityCompactionSettings(
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
        ContinuityCompactionSettings(
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
