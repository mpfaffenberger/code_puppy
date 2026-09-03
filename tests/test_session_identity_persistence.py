"""An agent's identity must survive a resume.

``BaseAgent.__init__`` mints ``self.id`` as a fresh uuid4, and
``get_identity()`` renders it into the system prompt via
``get_identity_prompt()``. Every process therefore introduces itself under a
different name, and any front door that runs one turn per process -- an
embedding runner, a headless ``-p`` loop -- changes identity
mid-conversation.

Two things break, and the second is the expensive one:

1. The prompt tells the agent to use that id "for claiming task ownership or
   coordination with other agents". An id that does not outlive the turn
   cannot own anything.
2. The identity line lives INSIDE the instructions block, which is the
   provider's cache prefix. A new id per turn rewrites the prefix, so a
   resumed conversation misses the prompt cache on every turn -- paying full
   uncached input for context that never changed.

``persist_named_session`` / ``restore_named_session`` are the one true path
for a session round trip, so identity travels with the session envelope: it
is state belonging to the conversation, not to the process that happens to
be serving it.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.session_lifecycle import persist_named_session, restore_named_session


class _Agent(BaseAgent):
    """Smallest concrete agent: identity lives on the base class."""

    @property
    def name(self) -> str:
        return "test-agent"

    @property
    def display_name(self) -> str:
        return "Test Agent"

    @property
    def description(self) -> str:
        return "fixture"

    def get_system_prompt(self) -> str:
        return "SYSTEM"

    def get_available_tools(self):
        return []

    def estimate_tokens_for_message(self, message) -> int:
        return 1


def _round_trip(tmp: Path) -> tuple[_Agent, _Agent]:
    """Save from one agent, restore onto a second: the resume, in miniature."""
    saved = _Agent()
    saved.set_message_history([{"role": "user", "content": "hello"}])
    persist_named_session(saved, "s1", base_dir=tmp)

    resumed = _Agent()
    restore_named_session(resumed, "s1", base_dir=tmp)
    return saved, resumed


def test_identity_survives_a_resume():
    with tempfile.TemporaryDirectory() as d:
        saved, resumed = _round_trip(Path(d))
        assert resumed.id == saved.id
        assert resumed.get_identity() == saved.get_identity()


def test_identity_prompt_is_byte_identical_after_a_resume():
    # The actual cache-prefix guarantee. Comparing the rendered line rather
    # than the raw id is deliberate: the id could match while the rendering
    # drifted, and it is the rendered bytes the provider hashes.
    with tempfile.TemporaryDirectory() as d:
        saved, resumed = _round_trip(Path(d))
        assert resumed.get_identity_prompt() == saved.get_identity_prompt()


def test_identity_is_written_into_the_metadata_sidecar():
    # Persisted with the SESSION, not a process-local cache: a resume in a
    # brand new process has nothing else to read. Named for the sidecar it
    # asserts on: the history envelope is a separate file, and a failure
    # here should point at the right one.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent = _Agent()
        agent.set_message_history([{"role": "user", "content": "hello"}])
        metadata = persist_named_session(agent, "s1", base_dir=tmp)

        on_disk = json.loads(Path(metadata.metadata_path).read_text())
        assert on_disk["agent_id"] == agent.id


def test_two_fresh_agents_still_differ():
    # The guard against over-correcting into a constant. Identity must be
    # stable ACROSS A RESUME, not shared by every agent ever constructed.
    assert _Agent().id != _Agent().id


def test_autosave_records_the_identity_too():
    # The path that MATTERS most, and the one a lifecycle-only fix misses.
    # `auto_save_session_if_enabled` calls `save_session` directly rather than
    # going through `persist_named_session`, and quick-resume reads what it
    # writes -- so identity has to ride on this path or the common resume
    # still loses it. Reported by Copilot on this PR.
    from unittest import mock

    import code_puppy.config as cp_config

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent = _Agent()
        agent.set_message_history([{"role": "user", "content": "hello"}])

        with (
            mock.patch.object(cp_config, "AUTOSAVE_DIR", str(tmp)),
            mock.patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            mock.patch.object(
                cp_config, "get_current_session_name", return_value="auto1"
            ),
            mock.patch.object(cp_config, "record_quick_resume_sessions"),
        ):
            assert cp_config.auto_save_session_if_enabled(force=True) is True

        resumed = _Agent()
        restore_named_session(resumed, "auto1", base_dir=tmp)
        assert resumed.id == agent.id


def test_an_unserialisable_id_does_not_break_the_save():
    # The metadata sidecar is JSON and is written AFTER the history. An id
    # that cannot be serialised must not turn a successful save into a
    # half-write: the user's conversation matters, the identity field does
    # not. Caught by a MagicMock agent in the headless save-back tests, where
    # `agent.id` is a Mock rather than a string.
    class _Odd(_Agent):
        def __init__(self) -> None:
            super().__init__()
            self.id = object()  # type: ignore[assignment]

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent = _Odd()
        agent.set_message_history([{"role": "user", "content": "hello"}])
        metadata = persist_named_session(agent, "s1", base_dir=tmp)

        on_disk = json.loads(Path(metadata.metadata_path).read_text())
        assert "agent_id" not in on_disk
        assert Path(metadata.json_path).exists()


def test_restoring_a_session_without_an_id_keeps_the_agents_own():
    # Sessions written before this existed have no agent_id. Restoring one
    # must leave the fresh uuid alone rather than blanking the identity.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        saved = _Agent()
        saved.set_message_history([{"role": "user", "content": "hello"}])
        metadata = persist_named_session(saved, "s1", base_dir=tmp)

        path = Path(metadata.metadata_path)
        stripped = json.loads(path.read_text())
        stripped.pop("agent_id", None)
        path.write_text(json.dumps(stripped))

        resumed = _Agent()
        before = resumed.id
        restore_named_session(resumed, "s1", base_dir=tmp)
        assert resumed.id == before
