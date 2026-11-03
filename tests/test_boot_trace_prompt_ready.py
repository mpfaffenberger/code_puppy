"""on_prompt_ready is the interactive ready point of the boot trace."""

from code_puppy import callbacks


def test_prompt_ready_callback_marks_the_boot_trace_before_observers(monkeypatch):
    order = []
    monkeypatch.setattr(
        callbacks.boot_trace, "mark", lambda phase, **_: order.append(phase)
    )

    def observer():
        order.append("observer")

    callbacks.register_callback("prompt_ready", observer)
    try:
        callbacks.on_prompt_ready()
    finally:
        callbacks.unregister_callback("prompt_ready", observer)

    assert order == ["cli.prompt_ready", "observer"]
