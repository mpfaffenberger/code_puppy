"""subagent_panel -- live two-line status per sub-agent above the puppy.

Renders, inside the puppy spinner's own Rich Live region, a block per active
sub-agent::

      INVOKE AGENT <name>  <model>
       <spin> 00:19  calling read_file

    <bouncing puppy>

Line 1 is the INVOKE AGENT banner (core styling); line 2 is a single-char
animated spinner + mm:ss elapsed + a color-coded status (yellow=calling,
magenta=thinking, green=writing). Parallel sub-agents stack.

It reuses the puppy spinner's existing Rich ``Live`` (a monkeypatch of
``_generate_spinner_panel``) rather than a second ``Live`` -- two Live displays
on one console fight each other (which is why the built-in, fully-built but
never-wired ``SubAgentConsoleManager`` was dead code). Exact per-agent metadata
is captured by monkeypatching ``_render_subagent_invocation`` (which also
suppresses the now-redundant permanent banner). On completion, ``_do_render``
is wrapped to print a persistent frozen two-line record (banner + green check +
mm:ss completed) and suppress the redundant core completion line. Status text is
fed by the ``stream_event`` callback. See register_callbacks.py + state.py.
"""
