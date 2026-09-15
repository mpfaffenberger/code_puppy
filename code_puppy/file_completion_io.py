"""Bounded streaming ingestion for the completion index."""

import os
import subprocess
import threading

MAX_OUTPUT_BYTES = 32 * 1024 * 1024


def read_paths(rg: str, root: str, limit: int, timeout: float):
    try:
        proc = subprocess.Popen(
            [rg, "--files", "--hidden", "--null", "--glob", "!.git"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    expired = threading.Event()

    def stop():
        expired.set()
        try:
            proc.kill()
        except OSError:
            pass  # child exited concurrently with the deadline

    timer = threading.Timer(timeout, stop)
    timer.daemon = True
    timer.start()
    paths = []
    pending = b""
    total = 0
    capped = False
    try:
        while len(paths) < limit and total < MAX_OUTPUT_BYTES:
            chunk = proc.stdout.read1(min(65536, MAX_OUTPUT_BYTES - total))
            if not chunk:
                break
            total += len(chunk)
            records = (pending + chunk).split(b"\0")
            pending = records.pop()
            for record in records:
                if record:
                    paths.append(os.fsdecode(record))
                if len(paths) == limit:
                    break
        capped = len(paths) >= limit or total >= MAX_OUTPUT_BYTES
        if capped:
            proc.kill()
        code = proc.wait()
        return paths if not expired.is_set() and (capped or code in (0, 1)) else None
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
