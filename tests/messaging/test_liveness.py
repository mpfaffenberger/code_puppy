import time
from unittest.mock import patch

from code_puppy.messaging.liveness import LivenessHeartbeat


class _FakeStdout:
    def __init__(self, tty: bool = True):
        self._tty = tty
        self.writes: list[str] = []

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        self.writes.append(s)
        return len(s)

    def flush(self) -> None:
        pass


def test_no_op_without_tty():
    hb = LivenessHeartbeat()
    fake = _FakeStdout(tty=False)
    with patch("code_puppy.messaging.liveness.sys.stdout", fake):
        hb.start()
        assert not hb.active
        hb.stop()
    assert fake.writes == []


def test_pulses_title_then_restores_on_stop():
    hb = LivenessHeartbeat()
    fake = _FakeStdout(tty=True)
    with patch("code_puppy.messaging.liveness.sys.stdout", fake):
        hb.start()
        assert hb.active
        time.sleep(0.05)  # let at least one frame write
        hb.stop()
    assert not hb.active
    joined = "".join(fake.writes)
    assert "Mist · working" in joined  # pulsed at least once
    assert joined.endswith("\033]2;Mist\007")  # restored idle title on stop


def test_ref_counted_nested_runs():
    hb = LivenessHeartbeat()
    fake = _FakeStdout(tty=True)
    with patch("code_puppy.messaging.liveness.sys.stdout", fake):
        hb.start()  # main run
        hb.start()  # nested subagent run
        assert hb.active
        hb.stop()  # subagent ends — still alive
        assert hb.active
        hb.stop()  # main ends — now idle
        assert not hb.active
