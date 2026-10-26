"""Real-process boot under a fresh HOME: what reaches ``errors.log`` and what must not.

The in-process suites mock the runner; these runs use the real interpreter hook, the real
``code_puppy.main`` entry and a HOME with no ``~/.code_puppy``, so the logs directory has to be
created by the first write.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from code_puppy import error_hooks

BOOT_SCRIPT = textwrap.dedent(
    """
    import sys

    from code_puppy import cli_runner
    from code_puppy.main import main_entry

    mode = sys.argv[1]
    sys.argv = ["code-puppy"] + (["--version"] if mode == "version" else [])

    def fail():
        if mode == "config":
            raise OSError("config dir unwritable")
        raise KeyboardInterrupt

    if mode != "version":
        cli_runner.ensure_config_exists = fail
    main_entry()
    """
)

# mode -> (exit code, errors.log entries, text the previous hook must still print to stderr)
BOOTS = {
    "config": (1, 1, "OSError: config dir unwritable"),
    "interrupt": (0, 0, "KeyboardInterrupt"),
    "version": (0, 0, ""),
}


@pytest.mark.parametrize("mode", BOOTS)
def test_boot_failure_is_recorded_once_and_control_flow_is_not(mode, tmp_path):
    exit_code, entries, previous_hook_output = BOOTS[mode]
    home = tmp_path / "home"
    home.mkdir()
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("XDG_")
    }
    env.update(HOME=str(home), USERPROFILE=str(home), CODE_PUPPY_NO_SPLASH="1")

    result = subprocess.run(
        [sys.executable, "-c", BOOT_SCRIPT, mode],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    logs = home / ".code_puppy" / "logs"
    log = logs / "errors.log"
    assert result.returncode == exit_code, result.stderr
    assert previous_hook_output in result.stderr
    if not entries:
        assert not log.exists()
        return
    assert logs.is_dir()
    text = log.read_text()
    assert text.count("Error Type:") == entries
    assert f"Context: {error_hooks._MAIN_CONTEXT}\n" in text
    assert "Traceback (most recent call last)" in result.stderr
