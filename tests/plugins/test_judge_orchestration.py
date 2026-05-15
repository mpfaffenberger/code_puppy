"""Tests for the parallel-judges orchestration in wiggum/register_callbacks."""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.wiggum import judge_config, register_callbacks
from code_puppy.plugins.wiggum.judge import GoalJudgement
from code_puppy.plugins.wiggum.judge_config import JudgeConfig


@pytest.fixture
def isolated_judges():
    """Force the judge registry to live in a tmp file for each test."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "judges.json")
        with patch.object(judge_config, "JUDGES_FILE", path):
            yield path


def _fake_agent(name: str = "code-puppy", history: list | None = None):
    agent = MagicMock()
    agent.name = name
    agent.get_message_history = MagicMock(return_value=history or [])
    agent.get_model_name = MagicMock(return_value="fallback-model")
    return agent


def _verdict(name: str, *, complete: bool, notes: str = "") -> GoalJudgement:
    return GoalJudgement(
        judge_name=name, complete=complete, notes=notes, raw_response=""
    )


@pytest.mark.asyncio
async def test_run_goal_judges_parallel_all_pass(isolated_judges):
    """Two judges both pass with no notes => goal complete."""
    judge_config.add_judge(JudgeConfig(name="alpha", model="m1"))
    judge_config.add_judge(JudgeConfig(name="beta", model="m2"))

    call_log: list[str] = []

    async def fake_judge_goal(*, judge_config, **_kwargs):
        call_log.append(judge_config.name)
        await asyncio.sleep(0.01)
        return _verdict(judge_config.name, complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, verdicts = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is True
    # Per-judge PASS headers always included for visibility in the success banner.
    assert "[alpha] ✅ PASS" in notes
    assert "[beta] ✅ PASS" in notes
    assert {v.judge_name for v in verdicts} == {"alpha", "beta"}
    assert set(call_log) == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_run_goal_judges_one_fails_means_incomplete(isolated_judges):
    judge_config.add_judge(JudgeConfig(name="alpha", model="m1"))
    judge_config.add_judge(JudgeConfig(name="beta", model="m2"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        if judge_config.name == "alpha":
            return _verdict("alpha", complete=True, notes="")
        return _verdict("beta", complete=False, notes="tests are failing")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, verdicts = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is False
    assert "[alpha] ✅ PASS" in notes
    assert "[beta] ❌ FAIL" in notes
    assert "tests are failing" in notes
    assert len(verdicts) == 2


@pytest.mark.asyncio
async def test_passing_judge_with_rationale_notes_still_completes(isolated_judges):
    """complete=True is the 'no remediation needed' signal.

    Notes alongside a passing verdict are rationale (e.g., "Yes, the response
    satisfies the goal because..."), not remediation. They must not block
    completion — otherwise a verbose judge keeps the loop going forever.
    """
    judge_config.add_judge(JudgeConfig(name="chatty", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        return _verdict(
            "chatty",
            complete=True,
            notes="Yes, the response 'Hello there!' satisfies 'say hi'.",
        )

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is True
    assert "satisfies" in notes  # rationale still appears in the display string


@pytest.mark.asyncio
async def test_judge_exception_becomes_abstaining_verdict(isolated_judges):
    """A crashed judge abstains — doesn't get a vote, doesn't block goal."""
    judge_config.add_judge(JudgeConfig(name="crashy", model="m"))

    async def fake_judge_goal(**_kwargs):
        raise RuntimeError("kaboom")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
        patch("code_puppy.error_logging.log_error"),
    ):
        all_complete, notes, verdicts = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    # Only judge abstained → no voters → can't decide → incomplete.
    assert all_complete is False
    assert verdicts[0].abstained is True
    assert "kaboom" in notes
    assert "ABSTAIN" in notes


@pytest.mark.asyncio
async def test_default_judge_used_when_none_configured(isolated_judges):
    """No judges configured => synthesize a 'default' judge w/ implementor's model."""
    seen_names: list[str] = []

    async def fake_judge_goal(*, judge_config, **_kwargs):
        seen_names.append(judge_config.name)
        return _verdict(judge_config.name, complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert seen_names == ["default"]
    assert all_complete is True


@pytest.mark.asyncio
async def test_judges_run_in_parallel_not_serial(isolated_judges):
    """Three slow judges should finish in ~one slow-judge interval, not three."""
    for n in ("a", "b", "c"):
        judge_config.add_judge(JudgeConfig(name=n, model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        await asyncio.sleep(0.2)
        return _verdict(judge_config.name, complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        all_complete, _, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )
        elapsed = loop.time() - t0

    assert all_complete is True
    # Serial would be ~0.6s; parallel should be ~0.2s. Allow generous slack.
    assert elapsed < 0.45, f"judges ran serially? elapsed={elapsed}"


@pytest.mark.asyncio
async def test_remediation_notes_format(isolated_judges):
    judge_config.add_judge(JudgeConfig(name="a", model="m"))
    judge_config.add_judge(JudgeConfig(name="b", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        if judge_config.name == "a":
            return _verdict("a", complete=False, notes="missing tests\nadd them")
        return _verdict("b", complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        _, notes, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert "[a] ❌ FAIL" in notes
    assert "  missing tests" in notes  # indented
    assert "  add them" in notes
    assert "[b] ✅ PASS" in notes


@pytest.mark.asyncio
async def test_turn_end_feeds_remediation_notes_to_next_iteration(isolated_judges):
    """When goal is incomplete, the next iteration's prompt must include the notes."""
    from code_puppy.plugins.wiggum import state

    state.start("fix the bug", mode="goal")

    judge_config.add_judge(JudgeConfig(name="checker", model="m"))

    async def fake_judge_goal(**_kwargs):
        return _verdict("checker", complete=False, notes="bug still present in foo.py")

    try:
        with (
            patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
            patch.object(register_callbacks, "_display_llm_judge"),
        ):
            next_request = await register_callbacks._on_interactive_turn_end(
                agent=_fake_agent(),
                prompt="fix the bug",
                result=MagicMock(output="I tried"),
            )
    finally:
        state.stop()

    assert next_request is not None
    assert next_request["reason"] == "goal"
    assert next_request["clear_context"] is True
    assert "fix the bug" in next_request["prompt"]
    assert "bug still present in foo.py" in next_request["prompt"]
    assert "Judge remediation notes" in next_request["prompt"]


@pytest.mark.asyncio
async def test_turn_end_stops_loop_on_full_success(isolated_judges):
    from code_puppy.plugins.wiggum import state

    state.start("ship it", mode="goal")

    judge_config.add_judge(JudgeConfig(name="checker", model="m"))

    async def fake_judge_goal(**_kwargs):
        return _verdict("checker", complete=True, notes="")

    try:
        with (
            patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
            patch.object(register_callbacks, "_display_llm_judge"),
        ):
            next_request = await register_callbacks._on_interactive_turn_end(
                agent=_fake_agent(),
                prompt="ship it",
                result=MagicMock(output="done"),
            )
    finally:
        # state should already be stopped by the success path
        if state.is_active():
            state.stop()

    assert next_request is None
    assert state.is_active() is False


@pytest.mark.asyncio
async def test_judges_running_in_parallel_dont_share_failure_state(isolated_judges):
    """One judge crashing must not prevent the other from returning a verdict.

    Crashed/erroring judges ABSTAIN — they're excluded from the tally and
    don't block goal completion (see the 'endpoint errors should abstain'
    bug fix). So crashy + ok=PASS means the goal completes.
    """
    judge_config.add_judge(JudgeConfig(name="ok", model="m"))
    judge_config.add_judge(JudgeConfig(name="crashy", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        if judge_config.name == "crashy":
            raise RuntimeError("boom")
        await asyncio.sleep(0.05)
        return _verdict("ok", complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
        patch("code_puppy.error_logging.log_error"),
    ):
        all_complete, _, verdicts = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    by_name = {v.judge_name: v for v in verdicts}
    assert by_name["ok"].complete is True
    assert by_name["crashy"].abstained is True  # crashed → abstain
    assert all_complete is True  # crashy excluded, ok passed → goal complete


@pytest.mark.asyncio
async def test_display_serialized_after_parallel_run(isolated_judges):
    """Every judge's per-verdict banner must be displayed exactly once.

    Regression test for the 'I only saw Judy's output' bug: when banners
    were emitted concurrently from inside _run_single_judge, their writes
    interleaved and one overwrote the other. Now we emit per-judge banners
    AFTER asyncio.gather() finishes, so each judge gets its own line.
    """
    judge_config.add_judge(JudgeConfig(name="judy", model="m1"))
    judge_config.add_judge(JudgeConfig(name="joe-brown", model="m2"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        await asyncio.sleep(0.01)
        return _verdict(judge_config.name, complete=True, notes="rationale")

    seen_messages: list[str] = []

    def capture_display(msg, *_, **__):
        seen_messages.append(msg)

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(
            register_callbacks, "_display_llm_judge", side_effect=capture_display
        ),
    ):
        await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    # 1 announcement + 1 per-judge verdict banner each = 3 total
    assert len(seen_messages) == 3
    # The announcement mentions both judges by name
    assert "judy" in seen_messages[0] and "joe-brown" in seen_messages[0]
    # Per-judge verdicts both appear in the post-gather output
    joined = "\n".join(seen_messages[1:])
    assert "[judy]" in joined
    assert "[joe-brown]" in joined
    assert joined.count("✅ PASS") == 2


@pytest.mark.asyncio
async def test_single_judge_uses_singular_phrasing(isolated_judges):
    """When there's only one judge, the announcement banner is more natural."""
    judge_config.add_judge(JudgeConfig(name="solo", model="m"))

    async def fake_judge_goal(**_kwargs):
        return _verdict("solo", complete=True, notes="")

    seen: list[str] = []

    def capture(msg, *_, **__):
        seen.append(msg)

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge", side_effect=capture),
    ):
        await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    # Singular phrasing: "Asking judge..." not "Running N judges..."
    assert seen[0].lower().startswith("asking judge")
    assert "solo" in seen[0]


@pytest.mark.asyncio
async def test_all_pass_with_rationale_completes(isolated_judges):
    """Two judges both pass with rationale notes — should still complete."""
    judge_config.add_judge(JudgeConfig(name="a", model="m"))
    judge_config.add_judge(JudgeConfig(name="b", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        return _verdict(
            judge_config.name,
            complete=True,
            notes=f"{judge_config.name} approves with light reasoning.",
        )

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, _, verdicts = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is True
    assert all(v.complete for v in verdicts)


@pytest.mark.asyncio
async def test_brackets_in_judge_name_are_preserved_in_display(isolated_judges):
    """Regression: Rich was eating [joe-brown] because brackets parse as markup.

    We rely on _display_banner_message passing markup=False on the message.
    Here we test the orchestrator's output strings to make sure the format
    string itself contains the [name] payload — that's what gets handed to
    the display helper.
    """
    judge_config.add_judge(JudgeConfig(name="joe-brown", model="m"))
    judge_config.add_judge(JudgeConfig(name="judy", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        return _verdict(judge_config.name, complete=True, notes="ok")

    captured: list[str] = []

    def capture(msg, *_, **__):
        captured.append(msg)

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge", side_effect=capture),
    ):
        await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    # Both judge names with brackets must appear in the per-judge display lines.
    per_judge = captured[1:]
    assert any("[joe-brown]" in m for m in per_judge), per_judge
    assert any("[judy]" in m for m in per_judge), per_judge


@pytest.mark.asyncio
async def test_final_complete_banner_omits_notes_body(isolated_judges):
    """When the goal completes, the final banner must NOT re-dump per-judge notes.

    Per-judge lines are already shown by _run_goal_judges; dumping the full
    notes block again into the final '✅ GOAL COMPLETE!' banner was the
    'output shown twice' bug.
    """
    from code_puppy.plugins.wiggum import state

    state.start("say hi", mode="goal")
    judge_config.add_judge(JudgeConfig(name="judy", model="m"))

    async def fake_judge_goal(**_kwargs):
        return _verdict("judy", complete=True, notes="some long rationale here")

    captured_args: list[tuple[tuple, dict]] = []

    def capture(*args, **kwargs):
        captured_args.append((args, kwargs))

    try:
        with (
            patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
            patch.object(register_callbacks, "_display_llm_judge", side_effect=capture),
        ):
            await register_callbacks._on_interactive_turn_end(
                agent=_fake_agent(),
                prompt="say hi",
                result=MagicMock(output="hi"),
            )
    finally:
        if state.is_active():
            state.stop()

    # Find the final "✅ GOAL COMPLETE!" call
    completion_calls = [
        (args, kwargs)
        for args, kwargs in captured_args
        if args and "GOAL COMPLETE" in args[0]
    ]
    assert len(completion_calls) == 1
    args, kwargs = completion_calls[0]
    # The "details" argument (positional[1] or kwargs['details']) must NOT
    # contain the per-judge notes block — that was the duplication bug.
    details = kwargs.get("details") if len(args) < 2 else args[1]
    assert details is None or "some long rationale here" not in str(details)


@pytest.mark.asyncio
async def test_judge_runs_inside_subagent_context(isolated_judges):
    """judge_goal must wrap judge_agent.run() in subagent_context.

    This is what suppresses the judge's tool-call banners and intermediate
    chatter (read_file, grep, agent reasoning, etc.) in the goal-loop UI.
    """
    from code_puppy.plugins.wiggum import judge as judge_module
    from code_puppy.tools.subagent_context import is_subagent

    judge_config.add_judge(JudgeConfig(name="checker", model="fake-model"))

    saw_subagent_flag: list[bool] = []

    async def fake_run(_user_prompt):
        # When the real judge_agent.run() executes, is_subagent() should be True.
        saw_subagent_flag.append(is_subagent())

        class _R:
            output = judge_module.GoalJudgeOutput(complete=True, notes="ok")

        return _R()

    # Stub everything heavy: model load, prompt prep, tool registration.
    with (
        patch.object(
            judge_module.ModelFactory, "load_config", return_value={"fake-model": {}}
        ),
        patch.object(judge_module.ModelFactory, "get_model", return_value=MagicMock()),
        patch.object(judge_module, "make_model_settings", return_value={}),
        patch.object(
            judge_module,
            "prepare_prompt_for_model",
            return_value=MagicMock(instructions="i", user_prompt="u"),
        ),
        patch.object(
            judge_module,
            "load_agent",
            return_value=MagicMock(get_available_tools=lambda: []),
        ),
        patch("code_puppy.tools.register_tools_for_agent"),
        patch.object(judge_module, "Agent") as mock_agent_cls,
    ):
        mock_agent = MagicMock()
        mock_agent.run = fake_run
        mock_agent_cls.return_value = mock_agent

        verdict = await judge_module.judge_goal(
            judge_config=JudgeConfig(name="checker", model="fake-model"),
            implementor_agent=_fake_agent(),
            goal="g",
            response="r",
            error=None,
            history=[],
        )

    assert saw_subagent_flag == [True], (
        "judge_agent.run() must execute inside subagent_context"
    )
    # After the context exits, we're back in main-agent context.
    assert is_subagent() is False
    assert verdict.complete is True


@pytest.mark.asyncio
async def test_abstaining_judge_excluded_from_tally(isolated_judges):
    """One abstaining + one PASS = goal complete (abstain excluded)."""
    judge_config.add_judge(JudgeConfig(name="passy", model="m"))
    judge_config.add_judge(JudgeConfig(name="busted", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        if judge_config.name == "busted":
            return GoalJudgement(
                judge_name="busted",
                complete=False,
                notes="endpoint error (NotFoundError): 404 model_not_found",
                raw_response="",
                abstained=True,
            )
        return _verdict("passy", complete=True, notes="all good")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is True
    assert "ABSTAIN" in notes
    assert "model_not_found" in notes


@pytest.mark.asyncio
async def test_abstaining_judge_with_failing_other_still_incomplete(isolated_judges):
    """Abstain + FAIL = incomplete (abstain ignored, FAIL still counts)."""
    judge_config.add_judge(JudgeConfig(name="busted", model="m"))
    judge_config.add_judge(JudgeConfig(name="strict", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        if judge_config.name == "busted":
            return GoalJudgement(
                judge_name="busted",
                complete=False,
                notes="endpoint error",
                raw_response="",
                abstained=True,
            )
        return _verdict("strict", complete=False, notes="tests still failing")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge"),
    ):
        all_complete, notes, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is False
    assert "tests still failing" in notes


@pytest.mark.asyncio
async def test_all_abstain_means_cannot_decide(isolated_judges):
    """When every judge abstains, we can't decide \u2192 incomplete with a warning."""
    judge_config.add_judge(JudgeConfig(name="a", model="m"))
    judge_config.add_judge(JudgeConfig(name="b", model="m"))

    async def fake_judge_goal(*, judge_config, **_kwargs):
        return GoalJudgement(
            judge_name=judge_config.name,
            complete=False,
            notes="endpoint error",
            raw_response="",
            abstained=True,
        )

    seen: list[str] = []

    def capture(msg, *_, **__):
        seen.append(msg)

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge", side_effect=capture),
    ):
        all_complete, _, _ = await register_callbacks._run_goal_judges(
            agent=_fake_agent(),
            goal="g",
            result=None,
            error=None,
        )

    assert all_complete is False
    # User-facing warning when nobody could vote
    assert any("All judges abstained" in m for m in seen), seen


@pytest.mark.asyncio
async def test_cancellation_during_gather_shows_banner_and_propagates(
    isolated_judges,
):
    """Ctrl+C inside _run_goal_judges: show a visible banner, then re-raise.

    Letting cancellation propagate out of _run_goal_judges is what stops the
    goal loop cleanly — if we swallowed it and returned 'incomplete', the
    caller would just request another retry. The OUTER plugin boundary
    (_on_interactive_turn_end) catches it so the REPL stays alive.
    """
    judge_config.add_judge(JudgeConfig(name="slow", model="m"))

    async def fake_judge_goal(**_kwargs):
        await asyncio.sleep(10)
        return _verdict("slow", complete=True, notes="")

    with (
        patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
        patch.object(register_callbacks, "_display_llm_judge") as mock_display,
    ):
        task = asyncio.create_task(
            register_callbacks._run_goal_judges(
                agent=_fake_agent(),
                goal="g",
                result=None,
                error=None,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    display_calls = [c.args[0] for c in mock_display.call_args_list]
    assert any("cancel" in m.lower() for m in display_calls), display_calls


@pytest.mark.asyncio
async def test_turn_end_swallows_cancellation_and_stops_goal_mode(isolated_judges):
    """Same regression at the higher level: _on_interactive_turn_end must
    catch cancellation, stop goal mode, and return None (no continuation).
    """
    from code_puppy.plugins.wiggum import state

    state.start("do a thing", mode="goal")
    judge_config.add_judge(JudgeConfig(name="slow", model="m"))

    async def fake_judge_goal(**_kwargs):
        await asyncio.sleep(10)
        return _verdict("slow", complete=True, notes="")

    try:
        with (
            patch.object(register_callbacks, "judge_goal", new=fake_judge_goal),
            patch.object(register_callbacks, "_display_llm_judge"),
        ):
            task = asyncio.create_task(
                register_callbacks._on_interactive_turn_end(
                    agent=_fake_agent(),
                    prompt="do a thing",
                    result=MagicMock(output="trying"),
                )
            )
            await asyncio.sleep(0.05)
            task.cancel()

            try:
                next_request = await task
            except asyncio.CancelledError:
                pytest.fail("Cancellation escaped _on_interactive_turn_end")
    finally:
        if state.is_active():
            state.stop()

    assert next_request is None
    # Goal mode was stopped as a side-effect.
    assert state.is_active() is False
