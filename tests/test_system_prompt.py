"""What the model is actually told, observed in a real session."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

SPY_PLUGIN = """
    import os
    from collections.abc import Sequence
    from typing import Any

    from pydantic_ai.capabilities import AgentCapability, Hooks
    from pydantic_clai2.plugins import Plugin


    class Spy(Plugin):
        '''Writes each model request's agent name and instructions to a file.'''

        def get_capabilities(self) -> Sequence[AgentCapability[Any]]:
            hooks = Hooks[Any]()

            @hooks.on.before_model_request
            async def record(ctx, request_context):
                last = request_context.messages[-1]
                with open(os.environ["PUP_SPY_LOG"], "a", encoding="utf-8") as file:
                    file.write("AGENT=" + str(ctx.agent.name if ctx.agent else None) + "\\n")
                    file.write((getattr(last, "instructions", None) or "") + "\\n=====\\n")
                return request_context

            return (hooks,)
"""


def pup(*args: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "code_puppy", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
        timeout=180,
        check=False,
    )


def test_the_stock_agent_is_code_puppy_and_never_hears_of_clai(
    home: Path, tmp_path: Path
) -> None:
    """A native drop-in plugin records the first request of a real stock-agent turn.

    ``coder`` is turned off so the turn reaches the model on every platform
    (the runtime has no local workspace on Windows). The test model then calls
    tools with made-up arguments and the turn fails; only the first request's
    instructions matter here.
    """
    plugins = home / ".code_puppy" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "spy.py").write_text(textwrap.dedent(SPY_PLUGIN), encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "spy.log"
    env = {
        **os.environ,
        "CODE_PUPPY_NO_SPLASH": "1",
        "PUP_SPY_LOG": str(log),
        "PYTHONIOENCODING": "utf-8",
    }

    disabled = pup("plugins", "disable", "coder", env=env, cwd=work)
    assert disabled.returncode == 0, disabled.stderr
    pup("-m", "test", "-p", "say hi", env=env, cwd=work)

    first = log.read_text(encoding="utf-8").split("=====")[0]
    agent, _, instructions = first.partition("\n")
    assert agent == "AGENT=code-puppy"
    # The personality plugin, with the 0.0.x default names and its dog.
    assert (
        "You are Puppy, the most loyal digital puppy, helping your owner Master"
        in instructions
    )
    assert "I am Puppy! \N{DOG FACE} A sassy" in instructions
    # clai2's docs capability is gone, and nothing else names the runtime to the model.
    assert "clai" not in instructions.lower()
