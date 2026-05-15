"""Register the Wiggum looping slash commands and goal continuation policy."""

from __future__ import annotations

import asyncio
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import (
    emit_info,
    emit_success,
    emit_system_message,
    emit_warning,
)

from . import state
from .judge import GoalJudgement, judge_goal
from .judge_config import JudgeConfig, get_enabled_judges_or_default


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@register_command(
    name="wiggum",
    description="Loop mode: re-run the same prompt when agent finishes 🍩",
    usage="/wiggum <prompt>",
    category="plugin",
)
def handle_wiggum_command(command: str) -> str | bool:
    """Start Wiggum loop mode and execute the prompt immediately."""
    prompt = _extract_prompt(command)
    if not prompt:
        emit_warning("Usage: /wiggum <prompt>")
        emit_info("Example: /wiggum say hello world")
        emit_info("Press Ctrl+C or run /wiggum_stop to stop the loop.")
        return True

    state.start(prompt, mode="wiggum")
    emit_success("🍩 WIGGUM MODE ACTIVATED!")
    emit_info(f"Prompt: {prompt}")
    emit_info("The agent will re-loop this prompt after each completion.")
    emit_info("Press Ctrl+C or run /wiggum_stop to stop the loop.")
    return prompt


@register_command(
    name="goal",
    description="Retry a task until all LLM judges say it is complete 🎯",
    usage="/goal <prompt>",
    # /kibble and /chow are puppy-themed aliases for /goal — same behavior,
    # just more on-brand for a code puppy.
    aliases=["kibble", "chow"],
    category="plugin",
)
def handle_goal_command(command: str) -> str | bool:
    """Start goal mode and execute the prompt immediately."""
    prompt = _extract_prompt(command)
    if not prompt:
        emit_warning("Usage: /goal <prompt>  (aliases: /kibble, /chow)")
        emit_info("Example: /goal make tests pass for the auth flow")
        emit_info("Press Ctrl+C or run /goal_stop to stop the loop.")
        return True

    state.start(prompt, mode="goal")
    _display_banner_message("GOAL MODE", "🎯 ACTIVATED!", banner_name="llm_judge")
    emit_info(f"Goal: {prompt}")
    emit_info(
        "After each iteration, every enabled LLM judge will verify completion in parallel."
    )
    emit_info("Configure judges with /judges. (No judges configured = single default.)")
    return prompt


@register_command(
    name="wiggum_stop",
    description="Stop Wiggum/goal loop mode",
    usage="/wiggum_stop",
    aliases=["stopwiggum", "ws", "goal_stop"],
    category="plugin",
)
def handle_wiggum_stop_command(command: str) -> bool:
    """Stop Wiggum/goal loop mode."""
    del command
    if state.is_active():
        state.stop()
        emit_success("🍩 Wiggum/goal mode stopped!")
    else:
        emit_info("Wiggum/goal mode is not active.")
    return True


@register_command(
    name="judges",
    description="Configure goal-mode LLM judges (TUI) ⚖️",
    usage="/judges",
    category="plugin",
)
def handle_judges_command(command: str) -> bool:
    """Open the goal-judges TUI."""
    del command
    import concurrent.futures

    from code_puppy.command_line.judges_menu import interactive_judges_menu

    # The menu is async; run it in a fresh event loop on a worker thread so
    # we don't collide with whatever loop the CLI is using.
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(interactive_judges_menu()))
            future.result(timeout=600)
    except concurrent.futures.TimeoutError:
        emit_warning("Judges menu timed out.")
    except Exception as exc:
        emit_warning(f"Judges menu error: {exc}")

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_prompt(command: str) -> str:
    parts = command.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _response_text(result: Any) -> str | None:
    return str(getattr(result, "output", "")) if result is not None else None


def _display_banner_message(
    label: str,
    message: str,
    *,
    banner_name: str,
    details: str | None = None,
    final: bool = False,
) -> None:
    """Display an inline banner followed by a message."""
    import time

    from rich.console import Console
    from rich.text import Text

    from code_puppy.config import get_banner_color
    from code_puppy.messaging.spinner import pause_all_spinners, resume_all_spinners

    console = Console()
    pause_all_spinners()
    time.sleep(0.1)

    console.print(" " * 50, end="\r")
    console.print()
    color = get_banner_color(banner_name)
    banner = Text.from_markup(
        f"[bold white on {color}] {label} [/bold white on {color}] "
    )
    console.print(banner, end="")
    # markup=False so brackets in the message (e.g. "[joe-brown]") aren't
    # eaten by Rich's markup parser. Same for `details`.
    console.print(message, markup=False, highlight=False)

    if details:
        console.print(details, markup=False, highlight=False)
    if final:
        console.print()

    resume_all_spinners()


def _display_llm_judge(
    message: str, details: str | None = None, *, final: bool = False
) -> None:
    """Display goal-judge output with an inline banner."""
    _display_banner_message(
        "LLM JUDGE",
        message,
        banner_name="llm_judge",
        details=details,
        final=final,
    )


def _resolve_judges(implementor_agent: Any) -> list[JudgeConfig]:
    """Pick the judge set for this /goal iteration.

    If the user has configured judges via ``/judges`` we use those.
    Otherwise we fall back to a single ``default`` judge that uses the
    implementor agent's model and the standard goal-judge prompt.
    """
    fallback_model = getattr(
        implementor_agent.get_pydantic_agent().model
        if hasattr(implementor_agent, "get_pydantic_agent")
        else None,
        "model_name",
        None,
    )
    if not fallback_model:
        # The agent object exposes its model name via get_model_name() in most
        # places; fall back to that if the pydantic_agent shape differs.
        try:
            fallback_model = implementor_agent.get_model_name()
        except Exception:
            fallback_model = "code-puppy"

    return get_enabled_judges_or_default(str(fallback_model))


def _format_remediation_block(verdicts: list[GoalJudgement]) -> str:
    """Build the remediation-notes string that feeds the next iteration."""
    lines: list[str] = []
    for v in verdicts:
        if v.abstained:
            status = "⚠️  ABSTAIN"
        else:
            status = "✅ PASS" if v.complete else "❌ FAIL"
        lines.append(f"[{v.judge_name}] {status}")
        if v.notes:
            for note_line in v.notes.strip().splitlines():
                lines.append(f"  {note_line}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Judge orchestration (parallel)
# ---------------------------------------------------------------------------


async def _run_single_judge(
    judge_config: JudgeConfig,
    *,
    implementor_agent: Any,
    goal: str,
    response: str | None,
    error: BaseException | None,
    history: list[Any],
) -> GoalJudgement:
    """Run a single judge. No I/O — callers handle display before/after.

    We intentionally do NOT print here: ``_run_goal_judges`` runs many of
    these in parallel via ``asyncio.gather``, and concurrent calls into the
    rich Console (which does \\r line-clearing tricks) interleave and
    overwrite each other. Display is serialized at the orchestrator level.
    """
    try:
        return await judge_goal(
            judge_config=judge_config,
            implementor_agent=implementor_agent,
            goal=goal,
            response=response,
            error=error,
            history=history,
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except Exception as exc:
        # judge_goal() already catches model exceptions and returns an
        # abstain-verdict. Anything that escapes here is an unexpected bug
        # in OUR plumbing — still abstain so one bad judge can't block /goal.
        from code_puppy.error_logging import log_error

        log_error(exc, context=f"Goal judge failed ({judge_config.name})")
        return GoalJudgement(
            judge_name=judge_config.name,
            complete=False,
            notes=f"judge crashed: {type(exc).__name__}: {exc}",
            raw_response="",
            abstained=True,
        )


def _judge_roster_line(judges: list[JudgeConfig]) -> str:
    """e.g. 'judy (gpt-5.4), joe-brown (claude-sonnet-4.5)'."""
    return ", ".join(f"{j.name} ({j.model})" for j in judges)


async def _run_goal_judges(
    *,
    agent: Any,
    goal: str,
    result: Any,
    error: BaseException | None,
) -> tuple[bool, str, list[GoalJudgement]]:
    """Run every enabled judge in parallel.

    Returns ``(all_complete, formatted_notes, verdicts)``.

    ``all_complete`` is True when every judge reports ``complete=True``.
    The judge's own ``complete=True`` IS the "no remediation needed"
    signal — any rationale notes alongside it are just for visibility and
    don't block completion.
    """
    judges = _resolve_judges(agent)
    if not judges:
        return False, "No judge agents configured.", []

    history = list(agent.get_message_history())
    response_text = _response_text(result)

    # Announce up front so the user knows we're firing N judges in parallel.
    if len(judges) == 1:
        _display_llm_judge(
            f"Asking judge {_judge_roster_line(judges)} if the goal is complete..."
        )
    else:
        _display_llm_judge(
            f"Running {len(judges)} judges in parallel: {_judge_roster_line(judges)}"
        )

    try:
        verdicts: list[GoalJudgement] = await asyncio.gather(
            *(
                _run_single_judge(
                    judge,
                    implementor_agent=agent,
                    goal=goal,
                    response=response_text,
                    error=error,
                    history=history,
                )
                for judge in judges
            )
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        # Display the banner so the user sees WHY the panel bailed, then
        # re-raise. The caller (_on_interactive_turn_end) catches at the
        # plugin boundary so the REPL stays alive. Letting cancellation
        # propagate here is what stops the goal loop cleanly — if we
        # returned a sentinel tuple instead, the caller would treat it as
        # "goal incomplete" and request another retry.
        _display_llm_judge("⛔ Judges cancelled (Ctrl+C). Stopping goal loop.")
        raise

    # Now serialize the per-judge verdicts so all banners actually show up.
    for v in verdicts:
        if v.abstained:
            glyph = "⚠️  ABSTAIN"
        else:
            glyph = "✅ PASS" if v.complete else "❌ FAIL"
        summary = v.notes.strip().splitlines()[0] if v.notes.strip() else "(no notes)"
        _display_llm_judge(f"  [{v.judge_name}] {glyph} — {summary}")

    # Abstaining judges (endpoint errors, misconfigured models, etc.) are
    # excluded from the tally — they don't get a vote because they couldn't
    # actually render one. The goal completes when every NON-abstaining
    # judge says PASS. If every judge abstained, we can't decide — treat
    # that as incomplete with a clear warning.
    voting = [v for v in verdicts if not v.abstained]
    if not voting:
        all_complete = False
        if verdicts:
            _display_llm_judge("⚠️  All judges abstained — cannot determine completion.")
    else:
        all_complete = all(v.complete for v in voting)

    notes = _format_remediation_block(verdicts)
    return all_complete, notes, verdicts


# ---------------------------------------------------------------------------
# Turn-end hook (drives the /goal and /wiggum loops)
# ---------------------------------------------------------------------------


async def _on_interactive_turn_end(
    agent: Any,
    prompt: str,
    result: Any = None,
    *,
    success: bool = True,
    error: BaseException | None = None,
) -> dict[str, Any] | None:
    """Ask the CLI to continue while Wiggum/goal mode is active."""
    del prompt, success
    goal_prompt = state.get_prompt()
    if not goal_prompt:
        state.stop()
        return None

    loop_num = state.increment()
    if state.is_goal_mode():
        try:
            complete, notes, _verdicts = await _run_goal_judges(
                agent=agent,
                goal=goal_prompt,
                result=result,
                error=error,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            # Belt-and-suspenders: _run_goal_judges already swallows these
            # but we never want a stray Ctrl+C to escape the plugin and
            # take down the whole REPL.
            _display_llm_judge("⛔ Goal loop cancelled (Ctrl+C).")
            state.stop()
            return None
        if complete:
            # Per-judge verdicts were already shown by _run_goal_judges —
            # no need to re-dump the notes block here.
            _display_llm_judge("✅ GOAL COMPLETE!", final=True)
            state.stop()
            return None

        state.get_state().remediation_notes = notes
        _display_llm_judge(
            f"❌ GOAL INCOMPLETE — Retrying! (Loop #{loop_num})",
            final=True,
        )
        return {
            "prompt": f"{goal_prompt}\n\nJudge remediation notes:\n{notes}",
            "clear_context": True,
            "delay": 0.5,
            "reason": "goal",
        }

    if error is not None:
        emit_warning(f"\n🍩 WIGGUM RETRYING AFTER ERROR! (Loop #{loop_num})")
        emit_system_message(f"Previous run failed: {error}")
    else:
        emit_warning(f"\n🍩 WIGGUM RELOOPING! (Loop #{loop_num})")

    emit_system_message(f"Re-running prompt: {goal_prompt}")
    return {
        "prompt": goal_prompt,
        "clear_context": True,
        "delay": 0.5,
        "reason": "wiggum",
    }


def _on_interactive_turn_cancel(prompt: str, *, reason: str = "cancelled") -> None:
    del prompt
    if state.is_active():
        state.stop()
        emit_warning(f"🍩 Wiggum/goal loop stopped due to {reason}")


register_callback("interactive_turn_end", _on_interactive_turn_end)
register_callback("interactive_turn_cancel", _on_interactive_turn_cancel)
