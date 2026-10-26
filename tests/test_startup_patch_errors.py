"""Startup patch failures reach errors.log, reported after the last patch."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import textwrap
from collections import OrderedDict

import pytest

from code_puppy import error_logging, pydantic_patches

CONTEXT = (
    "code_puppy.pydantic_patches::apply_all_patches: "
    "startup/patches: apply the {name} patch"
)


def _ok() -> bool:
    return True


def _fails_loudly() -> bool:
    return pydantic_patches._patch_failed("_fails_loudly", ValueError("shape"), "x")


def _raises() -> bool:
    raise RuntimeError("patch bug")


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(path))
    monkeypatch.setattr(error_logging, "_fallback", OrderedDict())
    return path


def _entries(path) -> list[tuple[str, str]]:
    """(error type, context) per entry, in file order."""
    if not path.exists():
        return []
    types, contexts = [], []
    for line in path.read_text().splitlines():
        if line.startswith("Error Type: "):
            types.append(line.removeprefix("Error Type: "))
        elif line.startswith("Context: "):
            contexts.append(line.removeprefix("Context: "))
    return list(zip(types, contexts, strict=True))


def test_each_failed_patch_writes_one_entry_and_the_result_is_unchanged(
    log_file, monkeypatch, caplog
):
    monkeypatch.setattr(pydantic_patches, "_ALL_PATCHES", (_ok, _fails_loudly, _raises))

    with caplog.at_level(logging.ERROR, logger=pydantic_patches.logger.name):
        results = pydantic_patches.apply_all_patches()

    assert results == {"_ok": True, "_fails_loudly": False, "_raises": False}
    assert _entries(log_file) == [
        ("ValueError", CONTEXT.format(name="_fails_loudly")),
        ("RuntimeError", CONTEXT.format(name="_raises")),
    ]
    assert pydantic_patches._PENDING_REPORTS == []
    messages = [record.getMessage() for record in caplog.records]
    assert any("_fails_loudly FAILED to apply" in m for m in messages)
    assert any("_raises raised unexpectedly" in m for m in messages)
    assert any("2 patch(es) FAILED to apply" in m for m in messages)

    monkeypatch.setattr(pydantic_patches, "_ALL_PATCHES", (_ok,))
    pydantic_patches.apply_all_patches()  # earlier failures are not reported again
    assert len(_entries(log_file)) == 2


def test_a_real_patch_failure_is_recorded(log_file, monkeypatch):
    monkeypatch.delattr("pydantic_ai._agent_graph._clean_message_history")

    results = pydantic_patches.apply_all_patches()

    assert results["patch_message_history_cleaning"] is False
    assert _entries(log_file) == [
        (
            "AttributeError",
            CONTEXT.format(name="patch_message_history_cleaning"),
        )
    ]


def test_a_clean_run_writes_nothing(log_file, monkeypatch):
    monkeypatch.setattr(pydantic_patches, "_ALL_PATCHES", (_ok,))

    assert pydantic_patches.apply_all_patches() == {"_ok": True}

    assert not log_file.exists()
    assert pydantic_patches._PENDING_REPORTS == []


def test_a_failing_sink_does_not_change_the_result(log_file, monkeypatch):
    def sink_down(*_args, **_kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(error_logging, "log_error", sink_down)
    monkeypatch.setattr(pydantic_patches, "_ALL_PATCHES", (_ok, _raises))

    assert pydantic_patches.apply_all_patches() == {"_ok": True, "_raises": False}
    assert pydantic_patches._PENDING_REPORTS == []


ORDER_PROBE = textwrap.dedent(
    """
    import json, os, sys
    import code_puppy.pydantic_patches as pp

    def seen(label):
        return {
            "label": label,
            "pydantic_ai": "pydantic_ai" in sys.modules,
            "callbacks": "code_puppy.callbacks" in sys.modules,
            "log_written": any(
                "errors.log" in files
                for _, _, files in os.walk(os.environ["XDG_STATE_HOME"])
            ),
        }

    probes = []

    def failing():
        return pp._patch_failed("failing", ValueError("forced"), "x")

    def probe():
        probes.append(seen("last-patch"))
        return True

    pp._ALL_PATCHES = (failing, probe) if sys.argv[1] == "fail" else (probe,)
    pp.apply_all_patches()
    print(json.dumps({"probes": probes, "after": seen("after")}))
    """
)


def _run_probe(mode: str, state_home) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", ORDER_PROBE, mode],
        env={**os.environ, "XDG_STATE_HOME": str(state_home)},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_report_waits_for_the_last_patch_and_a_clean_boot_never_loads_the_sink(
    tmp_path,
):
    failed = _run_probe("fail", tmp_path / "failed")
    clean = _run_probe("clean", tmp_path / "clean")

    # Last patch runs after the failing one: nothing imported, nothing written yet.
    (last,) = failed["probes"]
    assert (last["pydantic_ai"], last["callbacks"], last["log_written"]) == (
        False,
        False,
        False,
    )
    # The tail report then writes the entry; its notify step imports callbacks.
    assert failed["after"]["log_written"] is True
    assert failed["after"]["callbacks"] is True
    # With no failure the report never runs.
    assert clean["after"]["log_written"] is False
    assert clean["after"]["callbacks"] is False
