"""Own command-hook processes until completion or cancellation cleanup."""

import asyncio
import os
import signal
import subprocess
from contextlib import suppress

from code_puppy.error_logging import log_error
from code_puppy.tools.win_shell_io import (
    IS_WINDOWS,
    attach_job,
    release_job,
    terminate_job,
)


async def _finish(task):
    # Repeated Ctrl+C must not abandon the reaper or an in-flight process spawn.
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def _stop(proc, windows_process):
    try:
        if IS_WINDOWS:
            terminate_job(windows_process)
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            # The shell is a session leader; its group can outlive the shell itself.
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
    finally:
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.kill()
        await asyncio.gather(proc.stdout.read(), proc.stderr.read(), proc.wait())


async def communicate_command(command, *, payload, timeout, cwd, env):
    """Run an isolated shell, reaping its tree before cancellation escapes."""
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if IS_WINDOWS
        else {"start_new_session": True}
    )
    proc = None
    windows_process = None

    async def spawn():
        nonlocal proc, windows_process
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            **options,
        )
        if IS_WINDOWS:
            # Reuse the shell runner's Job Object support with asyncio's Popen.
            windows_process = proc._transport.get_extra_info("subprocess")
            attach_job(windows_process)

    creation = asyncio.create_task(spawn())
    try:
        await asyncio.shield(creation)
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout
        )
        return stdout, stderr, proc.returncode
    except (asyncio.CancelledError, asyncio.TimeoutError):
        try:
            try:
                await _finish(creation)
            finally:
                if proc is not None:
                    await _finish(asyncio.create_task(_stop(proc, windows_process)))
        except Exception as exc:
            with suppress(Exception):
                log_error(exc, context="hook_engine._process: command cleanup failed")
        raise
    finally:
        if windows_process is not None:
            release_job(windows_process)
