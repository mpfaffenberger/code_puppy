"""Universal Constructor tool runner using isolated subprocess workers.

Replaces thread-only timeout with a killable subprocess/multiprocessing
worker. Enforces wall-clock timeout, uses JSON-only serialization for
args and results, and caps stdout/stderr.
"""

import json
import logging
import multiprocessing
import os
import sys
import tempfile
import time
import traceback
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Cap output to prevent model context blowup
_MAX_STDOUT_LINES = 256
_MAX_STDERR_LINES = 128
_MAX_STDOUT_CHARS = 4096
_MAX_STDERR_CHARS = 2048


def _cap_output(text: str, max_chars: int, max_lines: int) -> str:
    """Cap output string to prevent unbounded growth."""
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    else:
        truncated = False
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True
    if truncated:
        result += "\n... [output truncated]"
    return result


def _run_in_subprocess(
    module_path: str,
    function_name: str,
    args_json: str,
    result_path: str,
    stdout_path: str,
    stderr_path: str,
) -> None:
    """Worker function executed in a subprocess.

    Loads the module, calls the function with deserialized JSON args,
    and writes the JSON result to result_path.
    """
    stdout_buf = []
    stderr_buf = []

    class _CapStream:
        def __init__(self, buf, max_lines):
            self.buf = buf
            self.max_lines = max_lines

        def write(self, text: str) -> None:
            self.buf.append(text)
            if len(self.buf) > self.max_lines * 2:
                self.buf = self.buf[-self.max_lines * 2 :]

        def flush(self) -> None:
            pass

    # Redirect stdout/stderr to capped buffers
    cap_stdout = _CapStream(stdout_buf, _MAX_STDOUT_LINES)
    cap_stderr = _CapStream(stderr_buf, _MAX_STDERR_LINES)
    sys.stdout = cap_stdout  # type: ignore[assignment]
    sys.stderr = cap_stderr  # type: ignore[assignment]

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("uc_worker_module", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        func = getattr(module, function_name, None)
        if func is None:
            raise NameError(f"Function '{function_name}' not found in module")
        if not callable(func):
            raise TypeError(f"'{function_name}' is not callable")

        args: Dict[str, Any] = json.loads(args_json) if args_json else {}
        if not isinstance(args, dict):
            raise TypeError("tool_args must deserialize to a dict")

        raw_result = func(**args)

        # JSON-only serialization: reject non-serializable results
        try:
            result_json = json.dumps({"success": True, "result": raw_result})
        except (TypeError, ValueError) as e:
            raise TypeError(f"Tool result is not JSON-serializable: {e}") from e

        with open(result_path, "w", encoding="utf-8") as f:
            f.write(result_json)

    except Exception as e:
        error_info = {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(error_info, f)

    finally:
        # Write captured stdout/stderr
        with open(stdout_path, "w", encoding="utf-8") as f:
            f.write("".join(stdout_buf))
        with open(stderr_path, "w", encoding="utf-8") as f:
            f.write("".join(stderr_buf))


def run_tool_subprocess(
    module_path: str,
    function_name: str,
    args: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Run a UC tool function in an isolated subprocess with a hard timeout.

    Args:
        module_path: Absolute path to the Python module file.
        function_name: Name of the callable function in the module.
        args: Dictionary of arguments to pass to the function.
        timeout: Maximum wall-clock seconds to allow.

    Returns:
        Dict with keys:
            - success: bool
            - result: the JSON-deserialized return value (if success)
            - error: error message string (if not success)
            - stdout: capped stdout from the tool
            - stderr: capped stderr from the tool
            - execution_time: float seconds
    """
    args = args or {}
    args_json = json.dumps(args)

    with (
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as result_file,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as stdout_file,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as stderr_file,
    ):
        result_path = result_file.name
        stdout_path = stdout_file.name
        stderr_path = stderr_file.name

    start_time = time.time()
    process: Optional[multiprocessing.Process] = None

    try:
        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(
            target=_run_in_subprocess,
            args=(
                str(module_path),
                function_name,
                args_json,
                result_path,
                stdout_path,
                stderr_path,
            ),
        )
        process.start()
        process.join(timeout=timeout)

        if process.is_alive():
            # Timeout: kill the worker
            process.terminate()
            process.join(timeout=2.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=1.0)
            return {
                "success": False,
                "error": f"Tool timed out after {timeout}s",
                "stdout": "",
                "stderr": "",
                "execution_time": time.time() - start_time,
            }

        # Read result
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return {
                "success": False,
                "error": f"Failed to read tool result: {e}",
                "stdout": "",
                "stderr": "",
                "execution_time": time.time() - start_time,
            }

        # Read and cap stdout/stderr
        try:
            with open(stdout_path, "r", encoding="utf-8") as f:
                stdout_text = _cap_output(
                    f.read(), _MAX_STDOUT_CHARS, _MAX_STDOUT_LINES
                )
        except OSError:
            stdout_text = ""

        try:
            with open(stderr_path, "r", encoding="utf-8") as f:
                stderr_text = _cap_output(
                    f.read(), _MAX_STDERR_CHARS, _MAX_STDERR_LINES
                )
        except OSError:
            stderr_text = ""

        execution_time = time.time() - start_time

        return {
            "success": result_data.get("success", False),
            "result": result_data.get("result") if result_data.get("success") else None,
            "error": result_data.get("error")
            if not result_data.get("success")
            else None,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "execution_time": execution_time,
        }

    finally:
        # Cleanup temp files
        for p in (result_path, stdout_path, stderr_path):
            try:
                os.unlink(p)
            except OSError:
                pass
        if process is not None and process.is_alive():
            try:
                process.kill()
                process.join(timeout=1.0)
            except Exception:
                pass


def run_tool_callable(
    func: Callable,
    args: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Run a callable in an isolated subprocess by writing a temp module.

    This is a fallback for when we only have a callable object (not a
    file path). The callable must be picklable or the caller should
    prefer run_tool_subprocess with a module_path.

    Args:
        func: The callable to execute.
        args: Dictionary of arguments.
        timeout: Maximum seconds.

    Returns:
        Dict with success/result/error/stdout/stderr/execution_time.
    """
    import inspect

    try:
        module = inspect.getmodule(func)
        if module is not None and hasattr(module, "__file__") and module.__file__:
            module_path = module.__file__
            function_name = func.__name__
            return run_tool_subprocess(module_path, function_name, args, timeout)
    except Exception:
        pass

    # Fallback: write a temporary wrapper module
    try:
        import cloudpickle

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pkl", delete=False) as f:
            cloudpickle.dump(func, f)
            pickle_path = f.name
    except ImportError:
        return {
            "success": False,
            "error": "Cannot serialize callable for subprocess execution (cloudpickle not available)",
            "stdout": "",
            "stderr": "",
            "execution_time": 0.0,
        }

    wrapper_code = f"""
import cloudpickle, json, sys, traceback

with open({repr(pickle_path)}, "rb") as f:
    func = cloudpickle.load(f)

args_json = sys.argv[1] if len(sys.argv) > 1 else "{{}}"
args = json.loads(args_json)

try:
    result = func(**args)
    print(json.dumps({{"success": True, "result": result}}))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e), "traceback": traceback.format_exc()}}))
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(wrapper_code)
        wrapper_path = f.name

    try:
        args_json = json.dumps(args or {})
        import subprocess

        result = subprocess.run(
            [sys.executable, wrapper_path, args_json],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        try:
            data = json.loads(result.stdout.splitlines()[-1] if result.stdout else "{}")
        except json.JSONDecodeError:
            data = {
                "success": False,
                "error": result.stdout or result.stderr or "Unknown error",
            }

        return {
            "success": data.get("success", False),
            "result": data.get("result") if data.get("success") else None,
            "error": data.get("error") if not data.get("success") else None,
            "stdout": _cap_output(result.stdout, _MAX_STDOUT_CHARS, _MAX_STDOUT_LINES),
            "stderr": _cap_output(result.stderr, _MAX_STDERR_CHARS, _MAX_STDERR_LINES),
            "execution_time": timeout,  # approximate
        }
    finally:
        for p in (pickle_path, wrapper_path):
            try:
                os.unlink(p)
            except OSError:
                pass
