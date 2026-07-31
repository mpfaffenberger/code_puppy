"""Wire the cost tracker into agent runs and register the ``/cost`` command.

* ``agent_run_end`` -> fold each run's billed usage into the session meter.
  Fires for main-agent AND sub-agent runs; both cost real money and each
  reports its own ``result.usage()``, so summing every event matches actual
  API billing (see ``tracker`` module docstring).
* ``/cost`` -> print the session spend report.
* ``/cost reset`` -> zero the meter.

Everything is estimate-labeled: prices come from the bundled models.dev
database (no network), and provider billing has nuances (tiered pricing,
batch discounts, free tiers) this deliberately does not model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback

from .tracker import format_tokens, format_usd, get_tracker

COMMAND_NAME = "cost"


# ---------------------------------------------------------------------------
# agent_run_end -> record spend
# ---------------------------------------------------------------------------
async def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: Optional[str] = None,
    success: bool = True,
    error: Optional[Exception] = None,
    response_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Record the run's billed usage. Failed/cancelled runs still count -
    whatever the API billed before the failure was still spent."""
    get_tracker().record_run(model_name, metadata)


# ---------------------------------------------------------------------------
# /cost command
# ---------------------------------------------------------------------------
def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            COMMAND_NAME,
            "Show estimated dollar spend this session (per model); "
            "'/cost reset' zeroes the meter",
        )
    ]


def _render_report() -> str:
    snap = get_tracker().snapshot()
    if not snap.per_model:
        return (
            ":moneybag: [bold]Session cost[/bold]\n"
            "No completed agent runs yet - nothing spent."
        )

    lines: List[str] = []
    total = format_usd(snap.total_cost_usd) if snap.known_cost else "unknown"
    lines.append(f":moneybag: [bold]Session cost (estimated): {total}[/bold]")

    if snap.last_run_cost_usd is not None:
        lines.append(
            f"Last run: {format_usd(snap.last_run_cost_usd)} ({snap.last_run_model})"
        )

    lines.append("")
    for spend in snap.per_model:
        cost = format_usd(spend.cost_usd)
        token_bits = [
            f"in {format_tokens(spend.input_tokens)}",
            f"out {format_tokens(spend.output_tokens)}",
        ]
        if spend.cache_read_tokens:
            token_bits.append(f"cache-read {format_tokens(spend.cache_read_tokens)}")
        if spend.cache_write_tokens:
            token_bits.append(f"cache-write {format_tokens(spend.cache_write_tokens)}")
        source = ""
        if spend.pricing is not None:
            source = (
                f" [dim](priced as {spend.pricing.provider_id}/"
                f"{spend.pricing.model_id})[/dim]"
            )
        lines.append(
            f"  [cyan]{spend.model_name}[/cyan]: {cost} "
            f"({', '.join(token_bits)}; {spend.runs} run"
            f"{'s' if spend.runs != 1 else ''}){source}"
        )

    unknown = snap.unknown_models
    if unknown:
        lines.append("")
        lines.append(
            "[yellow]No pricing data for: "
            + ", ".join(m.model_name for m in unknown)
            + " - tokens tracked, cost excluded from the total.[/yellow]"
        )

    lines.append("")
    lines.append(
        "[dim]Estimates use bundled models.dev list prices; actual billing "
        "may differ (tiers, discounts, free quotas).[/dim]"
    )
    return "\n".join(lines)


def _handle_cost_command(command: str) -> bool:
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    tokens = command.strip().split()
    arg = tokens[1].lower() if len(tokens) > 1 else ""

    if arg in ("--help", "-h", "help"):
        emit_info(
            "Usage: /cost            Show estimated session spend\n"
            "       /cost reset      Zero the meter (pricing cache kept)"
        )
        return True
    if arg == "reset":
        get_tracker().reset()
        emit_success(":moneybag: Cost meter reset to $0.00")
        return True
    if arg:
        emit_warning(f"Unknown /cost subcommand: {arg} (try /cost --help)")
        return True

    emit_info(_render_report())
    return True


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != COMMAND_NAME:
        return None
    return _handle_cost_command(command)


register_callback("agent_run_end", _on_agent_run_end)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)


__all__ = [
    "COMMAND_NAME",
    "_custom_help",
    "_handle_custom_command",
    "_handle_cost_command",
    "_on_agent_run_end",
    "_render_report",
]
