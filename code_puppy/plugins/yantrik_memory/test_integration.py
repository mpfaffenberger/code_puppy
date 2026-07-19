"""Standalone integration test for the yantrik_memory plugin.

Does NOT need the Code Puppy TUI. It points the plugin at a temp store, enables
it, drives the hook functions directly to simulate a conversation, and asserts:

1. A durable fact is learned from a natural turn.
2. A later "we rebranded" turn SUPERSEDES the old fact (current band shows the
   new value, NOT the old one).
3. Pure chatter adds nothing durable.

Run directly (``python test_integration.py``) or under pytest. Requires Ollama
running locally with the distiller model + yantrikdb_mcp[onnx] installed.
"""

from __future__ import annotations

import os
import sys
import tempfile


def _bootstrap_imports():
    """Import the plugin modules whether run as a script or via pytest.

    Sets a temp YANTRIK_MEMORY_ROOT BEFORE importing config-dependent modules so
    the test never touches the user's real store.
    """
    tmp_root = tempfile.mkdtemp(prefix="yantrik_mem_test_")
    os.environ["YANTRIK_MEMORY_ROOT"] = tmp_root

    # Make the package importable when run as a bare script from its own dir.
    here = os.path.dirname(os.path.abspath(__file__))
    pkg_parent = os.path.abspath(os.path.join(here, "..", "..", ".."))
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)

    from code_puppy.plugins.yantrik_memory import (  # noqa: E402
        recorder,
        retriever,
        state,
        substrate,
    )

    return tmp_root, recorder, retriever, state, substrate


def run() -> int:
    tmp_root, recorder, retriever, state, substrate = _bootstrap_imports()
    print(f"[test] temp store: {tmp_root}")

    if not substrate.MEMORY_AVAILABLE:
        print(f"[SKIP] YantrikDB not available: {substrate.IMPORT_ERROR!r}")
        return 0

    failures: list[str] = []

    # 1. Enable the plugin (opt-in default is OFF).
    state.set_enabled(True)
    assert state.is_enabled(), "plugin should be enabled after set_enabled(True)"
    print("[test] enabled OK")

    # 2. Simulate two user turns: an initial fact, then a rebrand that updates it.
    print("[test] turn 1: initial brand color...")
    recorder.distill_user_message(
        "Our brand color is blue #1F4E79, logo top-right.", session_id="sess-1"
    )
    print("[test] turn 2: rebrand to green (should supersede)...")
    recorder.distill_user_message(
        "We rebranded, brand color is now green #2E7D32.", session_id="sess-1"
    )

    # 3. Build the recall block and check supersession.
    block = retriever.build_recall_block("what is our brand color?")
    print("\n----- recall block -----")
    print(block)
    print("------------------------\n")

    if not block:
        failures.append("recall block was empty (expected current-band facts)")
    else:
        if "#2E7D32" not in block:
            failures.append("new color #2E7D32 missing from recall block")
        # The current band must NOT carry the superseded value. We check the
        # current section specifically (history/episodic may still hold it).
        current_section = block.split("## Relevant history")[0]
        if "#1F4E79" in current_section:
            failures.append(
                "superseded color #1F4E79 still present in CURRENT band "
                "(supersession failed)"
            )

    # 4. A pure-chatter turn must add nothing durable.
    print("[test] turn 3: pure chatter...")
    from code_puppy.plugins.yantrik_memory.config import DB_PATH

    ns = substrate.namespace_for_cwd()
    mem = substrate.Memory(str(DB_PATH), namespace=ns)
    before = len(mem.list_semantic(limit=10000))
    mem.close()

    recorder.distill_user_message(
        "Did you catch the game last night? Wild finish.", session_id="sess-1"
    )

    mem = substrate.Memory(str(DB_PATH), namespace=ns)
    after = len(mem.list_semantic(limit=10000))
    mem.close()
    print(f"[test] durable facts before chatter={before}, after={after}")
    if after != before:
        failures.append(
            f"chatter added durable fact(s): {before} -> {after} (expected no change)"
        )

    # Report.
    print()
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS")
    print("  - new color #2E7D32 present in current band")
    print("  - superseded #1F4E79 absent from current band")
    print(f"  - chatter added no durable facts ({before} == {after})")
    return 0


def test_yantrik_memory_supersession():
    """pytest entrypoint."""
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
