"""Offline submission benchmark: real CLI preprocessing, no model/network call.

Run with ``uv run python scripts/profile_submission.py``. Imports are measured
separately; preprocessing samples stop at entry to a stub agent. A second
probe builds the configured agent with MCP autostart disabled. No model
request is sent. Hooks, live input, history processing, and provider latency
are not measured. Use --profile-build for cProfile (adds substantial overhead).
"""

import asyncio
import cProfile
import io
import pstats
import sys
import time


async def main():
    started = time.perf_counter()
    from code_puppy.cli_runner import run_prompt_with_attachments
    from code_puppy.command_line.attachments import parse_prompt_attachments

    print(f"Cold CLI import: {time.perf_counter() - started:.3f}s")

    class ProbeAgent:
        async def run_with_mcp(self, prompt, **kwargs):
            return time.perf_counter()

    profile = cProfile.Profile()
    profile.enable()
    for sample in range(5):
        started = time.perf_counter()
        prompt = "Explain the project structure without modifying files."
        parse_prompt_attachments(prompt)
        entered, _ = await run_prompt_with_attachments(
            ProbeAgent(), prompt, use_run_ui=False
        )
        print(f"Preprocessing sample {sample + 1}: {(entered - started) * 1000:.2f}ms")
    profile.disable()
    report = io.StringIO()
    pstats.Stats(profile, stream=report).strip_dirs().sort_stats(
        "cumulative"
    ).print_stats(25)
    print(report.getvalue())

    # Instantiate the configured agent without connector autostart or a request.
    from unittest.mock import patch

    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.agents._builder import build_pydantic_agent

    agent = get_current_agent()
    build_profile = cProfile.Profile()
    profiled = "--profile-build" in sys.argv
    with patch("code_puppy.agents._builder.load_mcp_servers", return_value=[]):
        for label in ("cold", "warm"):
            if profiled:
                build_profile.enable()
            started = time.perf_counter()
            build_pydantic_agent(agent)
            elapsed = time.perf_counter() - started
            build_profile.disable()
            print(f"Agent build ({label}, profiled={profiled}): {elapsed:.3f}s")
    if profiled:
        pstats.Stats(build_profile).strip_dirs().sort_stats("cumulative").print_stats(
            30
        )


if __name__ == "__main__":
    asyncio.run(main())
